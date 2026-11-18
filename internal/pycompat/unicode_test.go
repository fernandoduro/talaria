package pycompat

import (
	"slices"
	"testing"
	"unicode"

	"github.com/fernandoduro/talaria/internal/golden"
	"golang.org/x/text/unicode/norm"
)

type unicodeGolden struct {
	Version    string    `json:"unicode_version"`
	Space      [][2]rune `json:"space"`
	IsSpace    [][2]rune `json:"isspace"`
	Word       [][2]rune `json:"word"`
	Decimal    [][2]rune `json:"decimal"`
	SreLower   [][2]rune `json:"sre_lower"`
	SreCased   [][2]rune `json:"sre_cased"`
	LowerFull  [][]any   `json:"lower_full"`
	ExtraCases [][]any   `json:"extra_cases"`
	LineBreaks []rune    `json:"line_breaks"`
	Mn         [][2]rune `json:"mn"`
	NFD        [][]any   `json:"nfd"`
}

func readUnicodeGolden(t *testing.T) unicodeGolden {
	t.Helper()
	var u unicodeGolden
	golden.ReadJSON(t, "pycompat/unicode.json", &u)
	if u.Version != unicode.Version {
		t.Fatalf("CPython has Unicode %s, Go has %s: the tables below no longer line up", u.Version, unicode.Version)
	}
	return u
}

func inRanges(rs [][2]rune, r rune) bool {
	for _, x := range rs {
		if r >= x[0] && r <= x[1] {
			return true
		}
	}
	return false
}

func everyCodePoint(f func(r rune)) {
	for r := rune(0); r < 0x110000; r++ {
		if r >= 0xd800 && r < 0xe000 {
			continue
		}
		f(r)
	}
}

// TestUnicodePropertiesMatchCPython checks every code point against CPython.
func TestUnicodePropertiesMatchCPython(t *testing.T) {
	u := readUnicodeGolden(t)
	if !slices.Equal(u.Space, u.IsSpace) {
		t.Fatal("re's \\s and str.isspace() disagree in CPython; IsSpace serves both")
	}
	lower := map[rune]rune{}
	for _, p := range u.SreLower {
		lower[p[0]] = p[1]
	}
	decimal := map[rune]int{}
	for _, p := range u.Decimal {
		decimal[p[0]] = int(p[1])
	}
	lowerFull := map[rune]string{}
	for _, row := range u.LowerFull {
		lowerFull[rune(row[0].(float64))] = row[1].(string)
	}
	nfd := map[rune]string{}
	for _, row := range u.NFD {
		nfd[rune(row[0].(float64))] = row[1].(string)
	}
	breaks := map[rune]bool{}
	for _, r := range u.LineBreaks {
		breaks[r] = true
	}
	fails := 0
	fail := func(format string, args ...any) {
		if fails++; fails <= 20 {
			t.Errorf(format, args...)
		}
	}
	everyCodePoint(func(r rune) {
		if IsSpace(r) != inRanges(u.Space, r) {
			fail("IsSpace(%U) = %v", r, IsSpace(r))
		}
		if IsWord(r) != inRanges(u.Word, r) {
			fail("IsWord(%U) = %v", r, IsWord(r))
		}
		want, isDec := decimal[r]
		if !isDec {
			want = -1
		}
		if IsDecimal(r) != isDec || DecimalValue(r) != want {
			fail("DecimalValue(%U) = %d, want %d", r, DecimalValue(r), want)
		}
		lo, ok := lower[r]
		if !ok {
			lo = r
		}
		if ReLower(r) != lo {
			fail("ReLower(%U) = %U, want %U", r, ReLower(r), lo)
		}
		if ReCased(r) != inRanges(u.SreCased, r) {
			fail("ReCased(%U) = %v", r, ReCased(r))
		}
		wantLower, ok := lowerFull[r]
		if !ok {
			wantLower = string(lo)
		}
		if got := Lower(string(r)); got != wantLower {
			fail("Lower(%q) = %q, want %q", string(r), got, wantLower)
		}
		if isLineBreak(r) != breaks[r] {
			fail("isLineBreak(%U) = %v", r, isLineBreak(r))
		}
		if unicode.Is(unicode.Mn, r) != inRanges(u.Mn, r) {
			fail("unicode.Mn disagrees with CPython on %U", r)
		}
		wantNFD, ok := nfd[r]
		if !ok {
			wantNFD = string(r)
		}
		if got := norm.NFD.String(string(r)); got != wantNFD {
			fail("NFD(%U) = %+q, want %+q", r, got, wantNFD)
		}
	})
	extra := map[rune][]rune{}
	for _, row := range u.ExtraCases {
		var vs []rune
		for _, v := range row[1].([]any) {
			vs = append(vs, rune(v.(float64)))
		}
		extra[rune(row[0].(float64))] = vs
	}
	if len(extra) != len(reExtraCases) {
		t.Errorf("reExtraCases has %d keys, CPython %d", len(reExtraCases), len(extra))
	}
	for k, v := range extra {
		if !slices.Equal(reExtraCases[k], v) {
			t.Errorf("reExtraCases[%U] = %U, CPython %U", k, reExtraCases[k], v)
		}
	}
}

// TestIgnoreCaseSetMatchesCPython compares, for every cased character, the
// characters re.IGNORECASE lets it match.
func TestIgnoreCaseSetMatchesCPython(t *testing.T) {
	var rows []struct {
		P       rune
		Matches []rune
	}
	var raw [][]any
	golden.ReadJSON(t, "pycompat/re_ignorecase.json", &raw)
	for _, r := range raw {
		var m []rune
		for _, v := range r[1].([]any) {
			m = append(m, rune(v.(float64)))
		}
		rows = append(rows, struct {
			P       rune
			Matches []rune
		}{rune(r[0].(float64)), m})
	}
	if len(rows) < 2900 {
		t.Fatalf("only %d rows", len(rows))
	}
	for _, row := range rows {
		if got := IgnoreCaseSet(row.P); !slices.Equal(got, row.Matches) {
			t.Errorf("IgnoreCaseSet(%U) = %U, CPython %U", row.P, got, row.Matches)
		}
		for _, c := range row.Matches {
			if !MatchFold(row.P, c) {
				t.Errorf("MatchFold(%U, %U) = false", row.P, c)
			}
		}
	}
	// Uncased pattern characters match only themselves.
	for _, p := range []rune{'1', ' ', '-', 0x2014, 0x00e3 + 0x1000} {
		if !ReCased(p) && !slices.Equal(IgnoreCaseSet(p), []rune{p}) {
			t.Errorf("IgnoreCaseSet(%U) = %U", p, IgnoreCaseSet(p))
		}
	}
}

func TestStringMethodsMatchCPython(t *testing.T) {
	var rows [][6]any // s, strip(), split(), splitlines(), lower(), strip(". ")
	golden.ReadJSON(t, "pycompat/strings.json", &rows)
	strs := func(v any) []string {
		var out []string
		for _, x := range v.([]any) {
			out = append(out, x.(string))
		}
		return out
	}
	for _, r := range rows {
		s := r[0].(string)
		if got := Strip(s); got != r[1].(string) {
			t.Errorf("Strip(%q) = %q, want %q", s, got, r[1])
		}
		if got := Fields(s); !slices.Equal(got, strs(r[2])) {
			t.Errorf("Fields(%q) = %q, want %q", s, got, strs(r[2]))
		}
		if got := SplitLines(s); !slices.Equal(got, strs(r[3])) {
			t.Errorf("SplitLines(%q) = %q, want %q", s, got, strs(r[3]))
		}
		if got := Lower(s); got != r[4].(string) {
			t.Errorf("Lower(%q) = %q, want %q", s, got, r[4])
		}
	}
}

func TestDateFromISOFormatMatchesCPython(t *testing.T) {
	var rows [][2]any // input, isoformat() or null
	golden.ReadJSON(t, "pycompat/isodate.json", &rows)
	for _, r := range rows {
		s := r[0].(string)
		got, err := DateFromISOFormat(s)
		switch want := r[1].(type) {
		case nil:
			if err == nil {
				t.Errorf("DateFromISOFormat(%q) = %s, CPython raises ValueError", s, got.Format("2006-01-02"))
			}
		case string:
			if err != nil {
				t.Errorf("DateFromISOFormat(%q): %v, CPython gives %s", s, err, want)
			} else if g := got.Format("2006-01-02"); g != want {
				t.Errorf("DateFromISOFormat(%q) = %s, CPython %s", s, g, want)
			}
		}
	}
}
