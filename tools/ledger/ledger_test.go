package main

import (
	"bytes"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

const pySource = `"""Docstring."""
import unittest

from talaria import utils


def helper():
    pass


class TestA(unittest.TestCase):
    def setUp(self):
        pass

    def test_one(self):
        def test_nested_is_not_collected():
            pass

    async def test_async(self):
        pass

    def testNoUnderscore(self):
        pass

# a column-0 comment does not end the class
    def test_after_comment(self):
        pass


SOME_CONSTANT = 1


class TestB(Base):
    def test_two(self):
        pass


def test_module_level_is_not_collected():
    pass
`

func TestParsePythonTests(t *testing.T) {
	got := parsePythonTests("test_x", []byte(pySource))
	want := []string{
		"test_x.TestA.test_one",
		"test_x.TestA.test_async",
		"test_x.TestA.testNoUnderscore",
		"test_x.TestA.test_after_comment",
		"test_x.TestB.test_two",
	}
	if !slices.Equal(got, want) {
		t.Errorf("parsePythonTests:\n got %v\nwant %v", got, want)
	}
}

func TestValidateRows(t *testing.T) {
	rows := []row{
		{Python: "test_a.TestA.test_ok", Status: "unported", Line: 2},
		{Python: "test_a.TestA.test_ported", Go: "internal/text.TestClean/strips_tags", Status: "ported", Line: 3},
		{Python: "test_a.TestA.test_strong", Go: "internal/media/audio.TestClipsMidWord", Status: "strengthened", Line: 4},
		{Python: "test_a.TestA.test_dropped", Status: "dropped: re-implemented the logic instead of calling it", Line: 5},
		{Python: "test_a.TestA.test_ok", Status: "unported", Line: 6},         // duplicate
		{Python: "test_a.TestA.test_bad_status", Status: "done", Line: 7},     // bad status
		{Python: "test_a.TestA.test_no_reason", Status: "dropped: ", Line: 8}, // empty reason
		{Python: "test_a.TestA.test_no_go", Status: "ported", Line: 9},        // missing go_test
		{Python: "test_a.TestA.test_go_on_unported", Go: "internal/x.TestX", Status: "unported", Line: 10},
		{Python: "TestA.test_no_module", Status: "unported", Line: 11},                // malformed key
		{Python: "test_a.TestA.test_bad_go", Go: "TestX", Status: "ported", Line: 12}, // no package
	}
	problems := validateRows(rows)
	wantLines := []string{"line 6", "line 7", "line 8", "line 9", "line 10", "line 11", "line 12"}
	if len(problems) != len(wantLines) {
		t.Fatalf("got %d problems, want %d:\n%s", len(problems), len(wantLines), strings.Join(problems, "\n"))
	}
	for i, w := range wantLines {
		if !strings.HasPrefix(problems[i], w+" ") {
			t.Errorf("problem %d = %q, want it about %s", i, problems[i], w)
		}
	}
}

func TestCompareWithPython(t *testing.T) {
	rows := []row{{Python: "test_a.T.test_1", Line: 2}, {Python: "test_a.T.test_gone", Line: 3}}
	problems := compareWithPython(rows, []string{"test_a.T.test_1", "test_a.T.test_new"})
	if len(problems) != 2 || !strings.Contains(problems[0], "test_new") || !strings.Contains(problems[1], "test_gone") {
		t.Errorf("problems = %q", problems)
	}
	if p := compareWithPython(rows, nil); p != nil {
		t.Errorf("with no Python tests the ledger is frozen; got %q", p)
	}
}

func TestSyncRowsKeepsDecisionsAndSourceOrder(t *testing.T) {
	rows := []row{
		{Python: "test_a.T.test_2", Go: "internal/a.TestTwo", Status: "ported"},
		{Python: "test_a.T.test_gone", Status: "unported"},
	}
	got := syncRows(rows, []string{"test_a.T.test_1", "test_a.T.test_2"})
	want := []row{
		{Python: "test_a.T.test_1", Status: "unported"},
		{Python: "test_a.T.test_2", Go: "internal/a.TestTwo", Status: "ported"},
		{Python: "test_a.T.test_gone", Status: "unported"},
	}
	if !slices.Equal(got, want) {
		t.Errorf("syncRows = %+v", got)
	}
}

func TestCheckDone(t *testing.T) {
	rows := []row{
		{Python: "test_a.T.test_1", Status: "ported"},
		{Python: "test_b.T.test_1", Status: "unported"},
	}
	if p := checkDone(rows, []string{"test_a"}); p != nil {
		t.Errorf("test_a is done; got %q", p)
	}
	if p := checkDone(rows, []string{"test_b", "test_zzz"}); len(p) != 2 {
		t.Errorf("want 2 problems, got %q", p)
	}
}

func TestCheckGoTestsReadsTestJSON(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "go.mod"), []byte("module example.com/m\n\ngo 1.26\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	events := `{"Action":"run","Package":"example.com/m/internal/text","Test":"TestClean"}
{"Action":"pass","Package":"example.com/m/internal/text","Test":"TestClean/strips_the_tags"}
{"Action":"fail","Package":"example.com/m/internal/text","Test":"TestClean/broken"}
{"Action":"pass","Package":"example.com/m/internal/text","Test":"TestClean"}
`
	var asked []string
	r := &runner{root: root, out: &bytes.Buffer{}, goTest: func(pkgs []string) ([]byte, error) {
		asked = pkgs
		return []byte(events), nil
	}}
	rows := []row{
		{Python: "test_a.T.test_1", Go: "internal/text.TestClean/strips the tags", Status: "ported", Line: 2},
		{Python: "test_a.T.test_2", Go: "internal/text.TestClean/broken", Status: "ported", Line: 3},
		{Python: "test_a.T.test_3", Go: "internal/text.TestMissing", Status: "strengthened", Line: 4},
		{Python: "test_a.T.test_4", Status: "unported", Line: 5},
	}
	problems, err := r.checkGoTests(rows)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(asked, []string{"internal/text"}) {
		t.Errorf("ran go test on %v", asked)
	}
	if len(problems) != 2 || !strings.Contains(problems[0], "broken: fail") || !strings.Contains(problems[1], "TestMissing did not run") {
		t.Errorf("problems = %q", problems)
	}
}

func TestRunEndToEndOnThisRepo(t *testing.T) {
	root, err := repoRoot()
	if err != nil {
		t.Skip("not in a git checkout:", err)
	}
	var out bytes.Buffer
	r := &runner{root: root, out: &out}
	ok, err := r.run(options{ledger: filepath.Join(root, "docs/plans/go-rewrite/test-map.tsv"), summary: true})
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Errorf("ledger check failed on the committed ledger:\n%s", out.String())
	}
}
