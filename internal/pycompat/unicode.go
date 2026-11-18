package pycompat

import (
	"slices"
	"strings"
	"sync"
	"unicode"
)

// Python's str methods and its re module classify characters with CPython's
// own Unicode tables. Go 1.26 and CPython 3.12 both ship Unicode 15.0.0, so
// the helpers below sit on Go's unicode package; testdata/golden/pycompat/
// unicode.json pins every one of them to CPython for every code point.

// IsSpace is Python's str.isspace() for one character, which is also what re
// matches with \s and what str.strip(), str.split() remove. It is Go's
// unicode.IsSpace plus U+001C..U+001F (the information separators, which
// CPython counts as whitespace because their bidi class is B or S).
func IsSpace(r rune) bool {
	return (r >= 0x1c && r <= 0x1f) || unicode.IsSpace(r)
}

// IsWord is what re's \w matches in a str pattern: str.isalnum() or "_".
// CPython's isalnum is the L and N categories exactly.
func IsWord(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

// IsDecimal is what re's \d matches in a str pattern: str.isdecimal(),
// category Nd. "\u0663" (ARABIC-INDIC DIGIT THREE) is a digit to Python.
func IsDecimal(r rune) bool { return unicode.Is(unicode.Nd, r) }

// DecimalValue is int(c) for a character IsDecimal accepts, and -1 otherwise.
// Unicode allocates every Nd digit in runs of ten, 0 through 9, so the value
// is the distance from the start of the run.
func DecimalValue(r rune) int {
	if !IsDecimal(r) {
		return -1
	}
	start := r
	for start > 0 && IsDecimal(start-1) {
		start--
	}
	return int(r-start) % 10
}

// Strip is Python's str.strip() with no argument.
func Strip(s string) string { return strings.TrimFunc(s, IsSpace) }

// Fields is Python's str.split() with no argument: runs of whitespace
// separate fields and no field is empty.
func Fields(s string) []string { return strings.FieldsFunc(s, IsSpace) }

// isLineBreak reports the characters str.splitlines() splits on, besides the
// two-character "\r\n".
func isLineBreak(r rune) bool {
	switch r {
	case '\n', '\r', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
		return true
	}
	return false
}

// SplitLines is Python's str.splitlines() (keepends=False): it breaks on
// \n, \r, \r\n, \v, \f, \x1c, \x1d, \x1e, \x85, U+2028 and U+2029, and a
// final line break does not produce an empty last line.
func SplitLines(s string) []string {
	var lines []string
	start := 0
	for i := 0; i < len(s); {
		r, size := rune(s[i]), 1
		if r >= 0x80 {
			r, size = decodeRune(s[i:])
		}
		if !isLineBreak(r) {
			i += size
			continue
		}
		lines = append(lines, s[start:i])
		i += size
		if r == '\r' && i < len(s) && s[i] == '\n' {
			i++
		}
		start = i
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

func decodeRune(s string) (rune, int) {
	for _, r := range s {
		return r, len(string(r))
	}
	return 0, 0
}

// Lower is Python's str.lower(): the full lowercase mapping, so "\u0130"
// (I WITH DOT ABOVE) becomes "i\u0307", and a capital sigma at the end of a
// word becomes the final form.
func Lower(s string) string {
	r := []rune(s)
	var b strings.Builder
	b.Grow(len(s))
	for i, c := range r {
		switch c {
		case 0x0130:
			b.WriteString("i\u0307")
		case 0x03A3:
			if finalSigma(r, i) {
				b.WriteRune(0x03C2)
			} else {
				b.WriteRune(0x03C3)
			}
		default:
			b.WriteRune(unicode.ToLower(c))
		}
	}
	return b.String()
}

// ReLower is the one-character lowercase the re module compares under
// IGNORECASE (_sre.unicode_tolower). It equals Go's unicode.ToLower for
// every code point; "\u0130" maps to "i".
func ReLower(r rune) rune { return unicode.ToLower(r) }

// upperOnlyInFull are the characters whose uppercase exists only as a
// multi-character special casing (ß -> SS, ŉ -> ʼN, ﬁ -> FI, ...). CPython's
// one-character upper() returns the first character of that mapping, so the
// re module counts them as cased; Go's simple mapping leaves them alone.
var upperOnlyInFull = []rune{
	0x00df, 0x0149, 0x01f0, 0x0390, 0x03b0, 0x0587, 0x1e96, 0x1e97, 0x1e98,
	0x1e99, 0x1e9a, 0x1f50, 0x1f52, 0x1f54, 0x1f56, 0x1fb2, 0x1fb4, 0x1fb6,
	0x1fb7, 0x1fc2, 0x1fc4, 0x1fc6, 0x1fc7, 0x1fd2, 0x1fd3, 0x1fd6, 0x1fd7,
	0x1fe2, 0x1fe3, 0x1fe4, 0x1fe6, 0x1fe7, 0x1ff2, 0x1ff4, 0x1ff6, 0x1ff7,
	0xfb00, 0xfb01, 0xfb02, 0xfb03, 0xfb04, 0xfb05, 0xfb06, 0xfb13, 0xfb14,
	0xfb15, 0xfb16, 0xfb17,
}

// ReCased is _sre.unicode_iscased: the character differs from its lowercase
// or from its (first-character) uppercase. Under IGNORECASE the re module
// matches an uncased pattern character only literally.
func ReCased(r rune) bool {
	if unicode.ToLower(r) != r || unicode.ToUpper(r) != r {
		return true
	}
	_, found := slices.BinarySearch(upperOnlyInFull, r)
	return found
}

// reExtraCases is re._casefix._EXTRA_CASES: characters IGNORECASE treats as
// equal although neither lowercases to the other (i and dotless ı, s and
// long ſ, µ and μ, the Greek symbol variants, ...). Keyed by lowercase.
var reExtraCases = map[rune][]rune{
	0x69: {0x131}, 0x73: {0x17f}, 0xb5: {0x3bc}, 0x131: {0x69}, 0x17f: {0x73},
	0x345: {0x3b9, 0x1fbe}, 0x390: {0x1fd3}, 0x3b0: {0x1fe3}, 0x3b2: {0x3d0},
	0x3b5: {0x3f5}, 0x3b8: {0x3d1}, 0x3b9: {0x345, 0x1fbe}, 0x3ba: {0x3f0},
	0x3bc: {0xb5}, 0x3c0: {0x3d6}, 0x3c1: {0x3f1}, 0x3c2: {0x3c3}, 0x3c3: {0x3c2},
	0x3c6: {0x3d5}, 0x3d0: {0x3b2}, 0x3d1: {0x3b8}, 0x3d5: {0x3c6}, 0x3d6: {0x3c0},
	0x3f0: {0x3ba}, 0x3f1: {0x3c1}, 0x3f5: {0x3b5}, 0x432: {0x1c80}, 0x434: {0x1c81},
	0x43e: {0x1c82}, 0x441: {0x1c83}, 0x442: {0x1c84, 0x1c85}, 0x44a: {0x1c86},
	0x463: {0x1c87}, 0x1c80: {0x432}, 0x1c81: {0x434}, 0x1c82: {0x43e},
	0x1c83: {0x441}, 0x1c84: {0x442, 0x1c85}, 0x1c85: {0x442, 0x1c84},
	0x1c86: {0x44a}, 0x1c87: {0x463}, 0x1c88: {0xa64b}, 0x1e61: {0x1e9b},
	0x1e9b: {0x1e61}, 0x1fbe: {0x345, 0x3b9}, 0x1fd3: {0x390}, 0x1fe3: {0x3b0},
	0xa64b: {0x1c88}, 0xfb05: {0xfb06}, 0xfb06: {0xfb05},
}

// lowerPreimage maps a lowercase character to every character that
// lowercases to it (itself excluded), built once from Go's case tables.
var lowerPreimage = sync.OnceValue(func() map[rune][]rune {
	m := map[rune][]rune{}
	for _, cr := range unicode.CaseRanges {
		for r := rune(cr.Lo); r <= rune(cr.Hi); r++ {
			if lo := unicode.ToLower(r); lo != r {
				m[lo] = append(m[lo], r)
			}
		}
	}
	return m
})

// IgnoreCaseSet lists, in ascending order, every character that the pattern
// character p matches under re.IGNORECASE in a str pattern:
//
//   - an uncased p matches only itself;
//   - a cased p matches every c whose ReLower(c) is ReLower(p) or one of the
//     extra cases of ReLower(p).
//
// So "s" matches s, S and ſ; "k" matches k, K and the Kelvin sign; "i"
// matches i, I, İ and ı. Building a regexp2 pattern from these sets avoids
// relying on regexp2's own IgnoreCase, which lowercases differently.
func IgnoreCaseSet(p rune) []rune {
	if !ReCased(p) {
		return []rune{p}
	}
	lo := unicode.ToLower(p)
	keys := append([]rune{lo}, reExtraCases[lo]...)
	pre := lowerPreimage()
	var out []rune
	for _, k := range keys {
		if unicode.ToLower(k) == k || slices.Contains(keys, unicode.ToLower(k)) {
			out = append(out, k)
		}
		out = append(out, pre[k]...)
	}
	slices.Sort(out)
	return slices.Compact(out)
}

// MatchFold reports whether input character c matches pattern character p
// under re.IGNORECASE.
func MatchFold(p, c rune) bool {
	if p == c {
		return true
	}
	if !ReCased(p) {
		return false
	}
	lc := unicode.ToLower(c)
	lp := unicode.ToLower(p)
	return lc == lp || slices.Contains(reExtraCases[lp], lc)
}
