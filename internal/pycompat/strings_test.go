package pycompat

import (
	"bufio"
	"bytes"
	"math"
	"strconv"
	"strings"
	"testing"
	"unicode"

	"github.com/fernandoduro/talaria/internal/golden"
)

func TestRuneLen(t *testing.T) {
	cases := []struct {
		in   string
		want int
	}{
		{"", 0},
		{"abc", 3},
		{"\u00e3", 1}, // one character, two UTF-8 bytes
		{"Ribeir\u00e3o A\u00e7a\u00ed — 😀", 17},
		{"e\u0301", 2}, // combining mark: two code points, as in Python
	}
	for _, c := range cases {
		if got := RuneLen(c.in); got != c.want {
			t.Errorf("RuneLen(%q) = %d, want %d", c.in, got, c.want)
		}
	}
}

func TestRuneSlice(t *testing.T) {
	const s = "a\u00e7a\u00ed—ok" // 7 characters
	cases := []struct {
		start, stop int
		want        string
	}{
		{0, 3, "a\u00e7a"},             // s[:3]
		{0, 60, s},                     // s[:60] on a shorter string: whole string
		{2, math.MaxInt, "a\u00ed—ok"}, // s[2:]
		{-2, math.MaxInt, "ok"},        // s[-2:]
		{0, -3, "a\u00e7a\u00ed"},      // s[:-3]
		{-100, 2, "a\u00e7"},           // clamped
		{5, 3, ""},                     // empty when start >= stop
		{7, 9, ""},
	}
	for _, c := range cases {
		if got := RuneSlice(s, c.start, c.stop); got != c.want {
			t.Errorf("RuneSlice(%q, %d, %d) = %q, want %q", s, c.start, c.stop, got, c.want)
		}
	}
}

func TestStrReprMatchesPythonGolden(t *testing.T) {
	var rows [][3]string // s, repr(s), json.dumps(s, ensure_ascii=False)
	golden.ReadJSON(t, "pycompat/str_repr.json", &rows)
	for _, r := range rows {
		if got := StrRepr(r[0]); got != r[1] {
			t.Errorf("StrRepr(%q) = %s, Python repr = %s", r[0], got, r[1])
		}
	}
}

// TestPrintableMatchesPython checks isPrintable against str.isprintable() for
// every code point, so StrRepr escapes exactly what Python escapes.
func TestPrintableMatchesPython(t *testing.T) {
	var g struct {
		UnicodeVersion  string    `json:"unicode_version"`
		PrintableRanges [][2]rune `json:"printable_ranges"`
	}
	golden.ReadJSON(t, "pycompat/printable.json", &g)
	if g.UnicodeVersion != unicode.Version {
		t.Fatalf("Python's Unicode %s vs Go's %s: the tables disagree by construction", g.UnicodeVersion, unicode.Version)
	}
	want := make(map[rune]bool)
	for _, rg := range g.PrintableRanges {
		for r := rg[0]; r <= rg[1]; r++ {
			want[r] = true
		}
	}
	bad := 0
	for r := rune(0); r <= unicode.MaxRune; r++ {
		if r >= 0xD800 && r < 0xE000 {
			continue
		}
		if isPrintable(r) != want[r] {
			if bad++; bad <= 10 {
				t.Errorf("isPrintable(U+%04X) = %v, Python %v", r, isPrintable(r), want[r])
			}
		}
	}
	if bad > 10 {
		t.Errorf("... %d code points disagree in total", bad)
	}
}

func TestCapitalize(t *testing.T) {
	cases := []struct{ in, want string }{
		{"", ""},
		{"going to", "Going to"}, // _expand_contractions: the real call site
		{"gONNA", "Gonna"},       // the rest is lowercased, not kept
		{"\u00c1GUA viva", "\u00c1gua viva"},
		{"\u00dftra\u00dfe", "Sstra\u00dfe"}, // full title mapping of sharp s
		{"ﬁsh", "Fish"},                      // ligature
		{"aİb", "Ai\u0307b"},                 // İ lowercases to two code points
		{"ΟΔΥΣΣΕΥΣ", "Οδυσσευς"},             // final sigma only at the end
		{"ǆemal", "ǅemal"},                   // title case, not upper case
		{"123 ABC", "123 abc"},
	}
	for _, c := range cases {
		if got := Capitalize(c.in); got != c.want {
			t.Errorf("Capitalize(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// TestCapitalizeMatchesPythonForEveryCodePoint compares, for every code
// point, the first-position (title) and later-position (lower) mapping with
// CPython's str.capitalize().
func TestCapitalizeMatchesPythonForEveryCodePoint(t *testing.T) {
	type pair struct{ first, rest string }
	want := map[rune]pair{}
	sc := bufio.NewScanner(bytes.NewReader(golden.Read(t, "pycompat/capitalize.tsv")))
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		f := strings.Split(line, "\t")
		cp, _ := strconv.ParseInt(f[0], 16, 32)
		want[rune(cp)] = pair{hexRunes(t, f[1]), hexRunes(t, f[2])}
	}
	if len(want) < 2000 {
		t.Fatalf("only %d golden rows", len(want))
	}
	bad := 0
	for r := rune(0); r <= unicode.MaxRune; r++ {
		if r >= 0xD800 && r < 0xE000 {
			continue
		}
		w, ok := want[r]
		if !ok {
			w = pair{string(r), string(r)}
		}
		first := Capitalize(string(r))
		rest := strings.TrimPrefix(Capitalize("A"+string(r)), "A")
		if first != w.first || rest != w.rest {
			if bad++; bad <= 10 {
				t.Errorf("U+%04X: Capitalize first %q rest %q, Python %q %q", r, first, rest, w.first, w.rest)
			}
		}
	}
	if bad > 10 {
		t.Errorf("... %d code points disagree in total", bad)
	}
}

func hexRunes(t *testing.T, s string) string {
	t.Helper()
	var b strings.Builder
	for _, h := range strings.Fields(s) {
		cp, err := strconv.ParseInt(h, 16, 32)
		if err != nil {
			t.Fatalf("bad hex %q", h)
		}
		b.WriteRune(rune(cp))
	}
	return b.String()
}

// TestFinalSigmaMatchesPython checks the final-sigma context against CPython
// for every possible neighbour of the sigma, before and after.
func TestFinalSigmaMatchesPython(t *testing.T) {
	var g struct {
		Before  [][2]rune   `json:"before"`
		After   [][2]rune   `json:"after"`
		Samples [][2]string `json:"samples"`
	}
	golden.ReadJSON(t, "pycompat/sigma.json", &g)
	for _, s := range g.Samples {
		if got := Capitalize(s[0]); got != s[1] {
			t.Errorf("Capitalize(%q) = %q, Python %q", s[0], got, s[1])
		}
	}
	in := func(ranges [][2]rune, r rune) bool {
		for _, rg := range ranges {
			if r >= rg[0] && r <= rg[1] {
				return true
			}
		}
		return false
	}
	bad := 0
	for r := rune(0); r <= unicode.MaxRune; r++ {
		if r >= 0xD800 && r < 0xE000 {
			continue
		}
		before := []rune(Capitalize("A" + string(r) + "Σ"))
		gotBefore := before[len(before)-1] == 'ς'
		after := []rune(Capitalize("AΣ" + string(r)))
		gotAfter := after[1] == 'ς'
		if gotBefore != in(g.Before, r) || gotAfter != in(g.After, r) {
			if bad++; bad <= 10 {
				t.Errorf("U+%04X next to Σ: final before=%v after=%v, Python before=%v after=%v",
					r, gotBefore, gotAfter, in(g.Before, r), in(g.After, r))
			}
		}
	}
	if bad > 10 {
		t.Errorf("... %d code points disagree in total", bad)
	}
}
