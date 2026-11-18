// Command ledger checks the Python-to-Go test ledger,
// docs/plans/go-rewrite/test-map.tsv.
//
// The ledger has one row per Python test, keyed by name (never file:line,
// which drifted three times in Phase 1):
//
//	python_test                       go_test                                   status
//	test_utils.TestStripMarkup.test_x  internal/text.TestStripMarkup/strips_tags  ported
//
// status is one of: unported, ported, strengthened, "dropped: <reason>".
// ported and strengthened rows name a Go test as <package dir>.<TestName>,
// optionally with /<subtest>; unported and dropped rows leave go_test empty.
//
// The check fails when:
//   - a tracked Python test has no row, or a row names a Python test that no
//     longer exists (Python tests come from `git ls-files`, not a glob);
//   - a row is malformed or duplicated;
//   - a ported or strengthened row names a Go test that does not exist or
//     does not pass (it runs `go test -json` on the packages named);
//   - a module given to -done still has unported rows.
//
// With -python it also cross-checks the parsed Python test names against
// unittest's own discovery, so the parser cannot silently miss a test.
//
//	go run ./tools/ledger                      # summary + every unported row
//	go run ./tools/ledger -summary             # counts only
//	go run ./tools/ledger -sync                # add missing Python tests as unported
//	go run ./tools/ledger -done test_utils,test_layout
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

const header = "python_test\tgo_test\tstatus"

func main() {
	ledgerPath := flag.String("ledger", "docs/plans/go-rewrite/test-map.tsv", "ledger file, relative to the repo root")
	sync := flag.Bool("sync", false, "add a row for every Python test missing from the ledger, as unported")
	summary := flag.Bool("summary", false, "print the counts only, not each unported row")
	done := flag.String("done", "", "comma-separated Python test modules (test_utils,...) that must have no unported rows")
	python := flag.String("python", "", "Python interpreter; when set, cross-check parsed test names against unittest discovery")
	flag.Parse()

	root, err := repoRoot()
	if err != nil {
		fatal(err)
	}
	r := &runner{root: root, out: os.Stdout}
	ok, err := r.run(options{
		ledger:  filepath.Join(root, *ledgerPath),
		sync:    *sync,
		summary: *summary,
		done:    splitList(*done),
		python:  *python,
	})
	if err != nil {
		fatal(err)
	}
	if !ok {
		os.Exit(1)
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "ledger:", err)
	os.Exit(2)
}

func splitList(s string) []string {
	var out []string
	for _, f := range strings.Split(s, ",") {
		if f = strings.TrimSpace(f); f != "" {
			out = append(out, f)
		}
	}
	return out
}

func repoRoot() (string, error) {
	out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output()
	if err != nil {
		return "", fmt.Errorf("git rev-parse: %w", err)
	}
	return strings.TrimSpace(string(out)), nil
}

type options struct {
	ledger  string
	sync    bool
	summary bool
	done    []string
	python  string
}

type runner struct {
	root string
	out  io.Writer
	// goTest runs `go test -json` on the packages and returns its stdout;
	// replaced in tests.
	goTest func(pkgs []string) ([]byte, error)
}

// row is one ledger line.
type row struct {
	Python, Go, Status string
	Line               int
}

func (r *runner) run(o options) (bool, error) {
	pyTests, err := r.pythonTests()
	if err != nil {
		return false, err
	}
	if o.python != "" {
		if err := r.crossCheckUnittest(o.python, pyTests); err != nil {
			return false, err
		}
		fmt.Fprintf(r.out, "parser agrees with unittest discovery: %d tests\n", len(pyTests))
	}

	rows, err := readLedger(o.ledger)
	if err != nil && !(o.sync && errors.Is(err, os.ErrNotExist)) {
		return false, err
	}
	if o.sync {
		rows = syncRows(rows, pyTests)
		if err := writeLedger(o.ledger, rows); err != nil {
			return false, err
		}
		if rows, err = readLedger(o.ledger); err != nil {
			return false, err
		}
	}

	problems := validateRows(rows)
	problems = append(problems, compareWithPython(rows, pyTests)...)
	goProblems, err := r.checkGoTests(rows)
	if err != nil {
		return false, err
	}
	problems = append(problems, goProblems...)
	problems = append(problems, checkDone(rows, o.done)...)

	r.report(rows, len(pyTests), o.summary)
	for _, p := range problems {
		fmt.Fprintln(r.out, "FAIL:", p)
	}
	if len(problems) > 0 {
		fmt.Fprintf(r.out, "ledger check failed: %d problem(s)\n", len(problems))
		return false, nil
	}
	fmt.Fprintln(r.out, "ledger check passed")
	return true, nil
}

// --- Python side -----------------------------------------------------------

var (
	reClass  = regexp.MustCompile(`^class\s+(\w+)\s*[(:]`)
	reMethod = regexp.MustCompile(`^    (?:async\s+)?def\s+(test\w*)\s*\(`)
	reTopLvl = regexp.MustCompile(`^[A-Za-z_@]`)
)

// pythonTests lists module.Class.test_name for every tracked tests/test_*.py,
// in source order.
func (r *runner) pythonTests() ([]string, error) {
	cmd := exec.Command("git", "ls-files", "--", "tests/test_*.py")
	cmd.Dir = r.root
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("git ls-files: %w", err)
	}
	var names []string
	for _, f := range strings.Fields(string(out)) {
		src, err := os.ReadFile(filepath.Join(r.root, f))
		if err != nil {
			return nil, err
		}
		module := strings.TrimSuffix(filepath.Base(f), ".py")
		names = append(names, parsePythonTests(module, src)...)
	}
	return names, nil
}

// parsePythonTests finds test methods defined directly in top-level classes.
// unittest only collects methods whose name starts with "test".
func parsePythonTests(module string, src []byte) []string {
	var names []string
	class := ""
	sc := bufio.NewScanner(bytes.NewReader(src))
	sc.Buffer(make([]byte, 1024*1024), 1024*1024)
	for sc.Scan() {
		line := sc.Text()
		if m := reClass.FindStringSubmatch(line); m != nil {
			class = m[1]
			continue
		}
		if reTopLvl.MatchString(line) {
			class = "" // a top-level def, import or assignment ends the class
			continue
		}
		if m := reMethod.FindStringSubmatch(line); m != nil && class != "" {
			names = append(names, module+"."+class+"."+m[1])
		}
	}
	return names
}

const unittestList = `import sys, unittest
def walk(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            yield from walk(t)
        else:
            yield t
suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
for t in walk(suite):
    print(t.id())
`

func (r *runner) crossCheckUnittest(python string, parsed []string) error {
	cmd := exec.Command(python, "-c", unittestList)
	cmd.Dir = r.root
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("unittest discovery with %s: %w\n%s", python, err, stderr.String())
	}
	var discovered []string
	for _, id := range strings.Fields(string(out)) {
		if strings.HasPrefix(id, "unittest.loader._FailedTest") {
			return fmt.Errorf("unittest discovery failed to import a test module: %s", id)
		}
		discovered = append(discovered, strings.TrimPrefix(id, "tests."))
	}
	a, b := slices.Sorted(slices.Values(parsed)), slices.Sorted(slices.Values(discovered))
	if !slices.Equal(a, b) {
		onlyParsed, onlyDiscovered := diff(a, b), diff(b, a)
		return fmt.Errorf("parsed %d Python tests, unittest discovered %d\nonly parsed: %v\nonly discovered: %v",
			len(a), len(b), onlyParsed, onlyDiscovered)
	}
	return nil
}

func diff(a, b []string) []string {
	var out []string
	for _, x := range a {
		if !slices.Contains(b, x) {
			out = append(out, x)
		}
	}
	return out
}

// --- ledger file -----------------------------------------------------------

func readLedger(path string) ([]row, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimSuffix(string(data), "\n"), "\n")
	if len(lines) == 0 || lines[0] != header {
		return nil, fmt.Errorf("%s: first line must be the header %q", path, header)
	}
	var rows []row
	for i, line := range lines[1:] {
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		f := strings.Split(line, "\t")
		if len(f) != 3 {
			return nil, fmt.Errorf("%s:%d: want 3 tab-separated fields, got %d", path, i+2, len(f))
		}
		rows = append(rows, row{Python: f[0], Go: f[1], Status: f[2], Line: i + 2})
	}
	return rows, nil
}

func writeLedger(path string, rows []row) error {
	var b strings.Builder
	b.WriteString(header + "\n")
	for _, r := range rows {
		fmt.Fprintf(&b, "%s\t%s\t%s\n", r.Python, r.Go, r.Status)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(b.String()), 0o644)
}

// syncRows orders rows by Python source order, adding missing tests as
// unported; rows for tests that no longer exist stay at the end, where the
// check reports them.
func syncRows(rows []row, pyTests []string) []row {
	byName := make(map[string]row, len(rows))
	for _, r := range rows {
		byName[r.Python] = r
	}
	out := make([]row, 0, len(pyTests))
	for _, name := range pyTests {
		if r, ok := byName[name]; ok {
			out = append(out, r)
			delete(byName, name)
		} else {
			out = append(out, row{Python: name, Status: "unported"})
		}
	}
	for _, r := range rows {
		if _, stale := byName[r.Python]; stale {
			out = append(out, r)
		}
	}
	return out
}

// --- validation ------------------------------------------------------------

var (
	rePyName = regexp.MustCompile(`^test_\w+\.\w+\.test\w*$`)
	reGoName = regexp.MustCompile(`^[a-z0-9_]+(?:/[a-z0-9_]+)*\.(Test\w*)(?:/\S+)?$`)
)

func statusKind(s string) string {
	if reason, ok := strings.CutPrefix(s, "dropped:"); ok {
		if strings.TrimSpace(reason) == "" {
			return "invalid"
		}
		return "dropped"
	}
	switch s {
	case "unported", "ported", "strengthened":
		return s
	}
	return "invalid"
}

func validateRows(rows []row) []string {
	var problems []string
	seen := map[string]int{}
	for _, r := range rows {
		where := fmt.Sprintf("line %d (%s)", r.Line, r.Python)
		if prev, dup := seen[r.Python]; dup {
			problems = append(problems, fmt.Sprintf("%s: duplicate of line %d", where, prev))
		}
		seen[r.Python] = r.Line
		if !rePyName.MatchString(r.Python) {
			problems = append(problems, fmt.Sprintf("%s: python_test is not module.Class.test_name", where))
		}
		switch statusKind(r.Status) {
		case "invalid":
			problems = append(problems, fmt.Sprintf("%s: status %q is not unported, ported, strengthened or \"dropped: <reason>\"", where, r.Status))
		case "ported", "strengthened":
			if !reGoName.MatchString(r.Go) {
				problems = append(problems, fmt.Sprintf("%s: go_test %q is not <package dir>.TestName[/subtest]", where, r.Go))
			}
		default: // unported, dropped
			if r.Go != "" {
				problems = append(problems, fmt.Sprintf("%s: go_test must be empty for status %q", where, r.Status))
			}
		}
	}
	return problems
}

func compareWithPython(rows []row, pyTests []string) []string {
	if len(pyTests) == 0 {
		return nil // after G5 the ledger is the frozen record
	}
	inLedger := map[string]bool{}
	for _, r := range rows {
		inLedger[r.Python] = true
	}
	tracked := map[string]bool{}
	var problems []string
	for _, name := range pyTests {
		tracked[name] = true
		if !inLedger[name] {
			problems = append(problems, fmt.Sprintf("%s: Python test has no ledger row (run with -sync)", name))
		}
	}
	for _, r := range rows {
		if !tracked[r.Python] {
			problems = append(problems, fmt.Sprintf("line %d: %s names no tracked Python test", r.Line, r.Python))
		}
	}
	return problems
}

func checkDone(rows []row, modules []string) []string {
	var problems []string
	for _, m := range modules {
		n, open := 0, 0
		for _, r := range rows {
			if strings.HasPrefix(r.Python, m+".") {
				n++
				if r.Status == "unported" {
					open++
				}
			}
		}
		switch {
		case n == 0:
			problems = append(problems, fmt.Sprintf("-done %s: no ledger rows for that module", m))
		case open > 0:
			problems = append(problems, fmt.Sprintf("-done %s: %d of %d rows still unported", m, open, n))
		}
	}
	return problems
}

// --- Go side ---------------------------------------------------------------

// goEvent is the subset of test2json output the check reads.
type goEvent struct {
	Action  string
	Package string
	Test    string
}

func (r *runner) checkGoTests(rows []row) ([]string, error) {
	var pkgs []string
	for _, rw := range rows {
		if k := statusKind(rw.Status); (k == "ported" || k == "strengthened") && reGoName.MatchString(rw.Go) {
			pkg, _, _ := strings.Cut(rw.Go, ".")
			if !slices.Contains(pkgs, pkg) {
				pkgs = append(pkgs, pkg)
			}
		}
	}
	if len(pkgs) == 0 {
		return nil, nil
	}
	run := r.goTest
	if run == nil {
		run = r.runGoTest
	}
	out, err := run(pkgs)
	if err != nil && len(out) == 0 {
		return nil, err
	}
	module, err := r.modulePath()
	if err != nil {
		return nil, err
	}
	result := map[string]string{} // "<pkg dir>.<Test/sub>" -> last action
	dec := json.NewDecoder(bytes.NewReader(out))
	for {
		var ev goEvent
		if err := dec.Decode(&ev); err == io.EOF {
			break
		} else if err != nil {
			return nil, fmt.Errorf("reading go test -json output: %w", err)
		}
		if ev.Test == "" || (ev.Action != "pass" && ev.Action != "fail" && ev.Action != "skip") {
			continue
		}
		dir := strings.TrimPrefix(strings.TrimPrefix(ev.Package, module), "/")
		result[dir+"."+ev.Test] = ev.Action
	}
	var problems []string
	for _, rw := range rows {
		if k := statusKind(rw.Status); k != "ported" && k != "strengthened" {
			continue
		}
		// go test -json reports subtests with spaces turned into underscores.
		key := strings.ReplaceAll(rw.Go, " ", "_")
		switch result[key] {
		case "pass":
		case "":
			problems = append(problems, fmt.Sprintf("line %d (%s): Go test %s did not run", rw.Line, rw.Python, rw.Go))
		default:
			problems = append(problems, fmt.Sprintf("line %d (%s): Go test %s: %s", rw.Line, rw.Python, rw.Go, result[key]))
		}
	}
	return problems, nil
}

func (r *runner) runGoTest(pkgs []string) ([]byte, error) {
	args := []string{"test", "-json", "-count=1"}
	for _, p := range pkgs {
		args = append(args, "./"+p)
	}
	cmd := exec.Command("go", args...)
	cmd.Dir = r.root
	cmd.Stderr = os.Stderr
	return cmd.Output() // a failing test exits 1 but still yields the events
}

func (r *runner) modulePath() (string, error) {
	data, err := os.ReadFile(filepath.Join(r.root, "go.mod"))
	if err != nil {
		return "", err
	}
	for _, line := range strings.Split(string(data), "\n") {
		if m, ok := strings.CutPrefix(strings.TrimSpace(line), "module "); ok {
			return strings.TrimSpace(m), nil
		}
	}
	return "", errors.New("go.mod has no module line")
}

// --- report ----------------------------------------------------------------

func (r *runner) report(rows []row, pyCount int, summaryOnly bool) {
	type tally struct{ total, unported, ported, strengthened, dropped int }
	var modules []string
	per := map[string]*tally{}
	all := &tally{}
	for _, rw := range rows {
		m, _, _ := strings.Cut(rw.Python, ".")
		if per[m] == nil {
			per[m] = &tally{}
			modules = append(modules, m)
		}
		for _, t := range []*tally{per[m], all} {
			t.total++
			switch statusKind(rw.Status) {
			case "unported":
				t.unported++
			case "ported":
				t.ported++
			case "strengthened":
				t.strengthened++
			case "dropped":
				t.dropped++
			}
		}
	}
	if !summaryOnly {
		for _, rw := range rows {
			if rw.Status == "unported" {
				fmt.Fprintln(r.out, "unported\t"+rw.Python)
			}
		}
		fmt.Fprintln(r.out)
	}
	for _, m := range modules {
		t := per[m]
		fmt.Fprintf(r.out, "%-28s %4d rows: %3d ported, %3d strengthened, %3d dropped, %3d unported\n",
			m, t.total, t.ported, t.strengthened, t.dropped, t.unported)
	}
	fmt.Fprintf(r.out, "%-28s %4d rows: %3d ported, %3d strengthened, %3d dropped, %3d unported (%d tracked Python tests)\n",
		"TOTAL", all.total, all.ported, all.strengthened, all.dropped, all.unported, pyCount)
}
