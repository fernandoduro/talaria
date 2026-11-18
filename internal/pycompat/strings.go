package pycompat

import (
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// RuneLen is Python's len(s) for a str: it counts characters (code points),
// not bytes. Go's len(s) counts UTF-8 bytes, so "\u00e3" is 1 here and 2 there.
func RuneLen(s string) int { return utf8.RuneCountInString(s) }

// RuneSlice is Python's s[start:stop] on a str, indexing by character.
// Negative indices count from the end and out-of-range bounds are clamped,
// exactly as Python slicing does; use math.MaxInt for an open stop (s[i:]).
func RuneSlice(s string, start, stop int) string {
	r := []rune(s)
	n := len(r)
	start, stop = clampIndex(start, n), clampIndex(stop, n)
	if start >= stop {
		return ""
	}
	return string(r[start:stop])
}

func clampIndex(i, n int) int {
	if i < 0 {
		i += n
		if i < 0 {
			return 0
		}
	}
	if i > n {
		return n
	}
	return i
}

// StrRepr is Python's repr(s) for a str, as used by f"{value!r}" in error
// messages: single quotes unless the text holds a ' and no ", backslash
// escapes for the quote, backslash, \t \n \r, \xHH for other control
// characters, and \xHH / \uHHHH / \UHHHHHHHH for non-printable non-ASCII.
// Printable non-ASCII text (accents, em dash, emoji) is kept as is.
func StrRepr(s string) string {
	quote := '\''
	if strings.ContainsRune(s, '\'') && !strings.ContainsRune(s, '"') {
		quote = '"'
	}
	var b strings.Builder
	b.WriteRune(quote)
	for _, r := range s {
		switch {
		case r == quote || r == '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r < ' ' || r == 0x7f:
			writeHex(&b, `\x`, r, 2)
		case r < 0x7f:
			b.WriteRune(r)
		case isPrintable(r):
			b.WriteRune(r)
		case r <= 0xff:
			writeHex(&b, `\x`, r, 2)
		case r <= 0xffff:
			writeHex(&b, `\u`, r, 4)
		default:
			writeHex(&b, `\U`, r, 8)
		}
	}
	b.WriteRune(quote)
	return b.String()
}

func writeHex(b *strings.Builder, prefix string, r rune, width int) {
	h := strconv.FormatInt(int64(r), 16)
	b.WriteString(prefix)
	b.WriteString(strings.Repeat("0", width-len(h)))
	b.WriteString(h)
}

// isPrintable is CPython's Py_UNICODE_ISPRINTABLE: everything except the
// categories Cc, Cf, Cs, Co, Cn, Zl, Zp and Zs (space itself excepted).
// unicode.IsPrint draws the same line: L, M, N, P, S plus U+0020.
func isPrintable(r rune) bool { return unicode.IsPrint(r) }

// Capitalize is Python's str.capitalize(): the first character goes to title
// case (full mapping, so "\u00df" becomes "Ss") and every other character goes to
// lower case, including the Greek final-sigma rule. Note it lowercases the
// rest: "gONNA" becomes "Gonna", not "GONNA".
func Capitalize(s string) string {
	if s == "" {
		return s
	}
	r := []rune(s)
	var b strings.Builder
	b.Grow(len(s))
	if t, ok := titleFull[r[0]]; ok {
		b.WriteString(t)
	} else {
		b.WriteRune(unicode.ToTitle(r[0]))
	}
	for i := 1; i < len(r); i++ {
		switch c := r[i]; c {
		case 0x0130: // LATIN CAPITAL LETTER I WITH DOT ABOVE -> i + COMBINING DOT ABOVE
			b.WriteString("i\u0307")
		case 0x03A3: // GREEK CAPITAL LETTER SIGMA
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

// finalSigma mirrors CPython's handle_capital_sigma: U+03A3 lowercases to the
// final form when preceded by a cased letter (skipping case-ignorables) and
// not followed by one (again skipping case-ignorables).
func finalSigma(r []rune, i int) bool {
	j := i - 1
	for j >= 0 && isCaseIgnorable(r[j]) {
		j--
	}
	if j < 0 || !isCased(r[j]) {
		return false
	}
	j = i + 1
	for j < len(r) && isCaseIgnorable(r[j]) {
		j++
	}
	return j == len(r) || !isCased(r[j])
}

// isCased is the Unicode Cased property: Lu, Ll, Lt, Other_Lowercase and
// Other_Uppercase.
func isCased(r rune) bool {
	return unicode.In(r, unicode.Lu, unicode.Ll, unicode.Lt, unicode.Other_Lowercase, unicode.Other_Uppercase)
}

// isCaseIgnorable is the Unicode Case_Ignorable property: Mn, Me, Cf, Lm, Sk,
// plus Word_Break MidLetter, MidNumLet and Single_Quote, which Go's unicode
// package does not expose, hence the explicit list.
func isCaseIgnorable(r rune) bool {
	switch r {
	case 0x0027, 0x002E, 0x003A, 0x00B7, 0x0387, 0x055F, 0x05F4,
		0x2018, 0x2019, 0x2024, 0x2027, 0xFE13, 0xFE52, 0xFE55,
		0xFF07, 0xFF0E, 0xFF1A:
		return true
	}
	return unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Lm, unicode.Sk)
}

// titleFull holds the SpecialCasing.txt title mappings that expand to more
// than one character (Unicode 15.0, the version both Go 1.26 and CPython 3.12
// ship). Single-character mappings come from unicode.ToTitle.
var titleFull = map[rune]string{
	0x00DF: "Ss", 0x0149: "\u02BCN", 0x01F0: "J\u030C", 0x0390: "\u0399\u0308\u0301",
	0x03B0: "\u03A5\u0308\u0301", 0x0587: "\u0535\u0582",
	0x1E96: "H\u0331", 0x1E97: "T\u0308", 0x1E98: "W\u030A", 0x1E99: "Y\u030A", 0x1E9A: "A\u02BE",
	0x1F50: "\u03A5\u0313", 0x1F52: "\u03A5\u0313\u0300", 0x1F54: "\u03A5\u0313\u0301", 0x1F56: "\u03A5\u0313\u0342",
	0x1FB2: "\u1FBA\u0345", 0x1FB4: "\u0386\u0345", 0x1FB6: "\u0391\u0342", 0x1FB7: "\u0391\u0342\u0345",
	0x1FC2: "\u1FCA\u0345", 0x1FC4: "\u0389\u0345", 0x1FC6: "\u0397\u0342", 0x1FC7: "\u0397\u0342\u0345",
	0x1FD2: "\u0399\u0308\u0300", 0x1FD3: "\u0399\u0308\u0301", 0x1FD6: "\u0399\u0342", 0x1FD7: "\u0399\u0308\u0342",
	0x1FE2: "\u03A5\u0308\u0300", 0x1FE3: "\u03A5\u0308\u0301", 0x1FE4: "\u03A1\u0313", 0x1FE6: "\u03A5\u0342",
	0x1FE7: "\u03A5\u0308\u0342", 0x1FF2: "\u1FFA\u0345", 0x1FF4: "\u038F\u0345", 0x1FF6: "\u03A9\u0342",
	0x1FF7: "\u03A9\u0342\u0345",
	0xFB00: "Ff", 0xFB01: "Fi", 0xFB02: "Fl", 0xFB03: "Ffi", 0xFB04: "Ffl", 0xFB05: "St", 0xFB06: "St",
	0xFB13: "\u0544\u0576", 0xFB14: "\u0544\u0565", 0xFB15: "\u0544\u056B", 0xFB16: "\u054E\u0576", 0xFB17: "\u0544\u056D",
}
