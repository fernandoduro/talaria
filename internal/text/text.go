// Package text implements Python's shared text helpers and proportional trim.
package text

import (
	"fmt"
	"strings"
	"time"
	"unicode"

	"github.com/dlclark/regexp2"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
)

const word = `[\p{L}\p{N}_]`
const space = `[\s\x1c-\x1f]`
const boundary = `(?:(?<![\p{L}\p{N}_])(?=[\p{L}\p{N}_])|(?<=[\p{L}\p{N}_])(?![\p{L}\p{N}_]))`

func compile(p string) *regexp2.Regexp {
	r := regexp2.MustCompile(p, 0)
	r.MatchTimeout = 2 * time.Second
	return r
}
func literalFold(s string) string {
	var b strings.Builder
	for _, c := range s {
		set := pycompat.IgnoreCaseSet(c)
		if len(set) == 1 {
			fmt.Fprintf(&b, `\x{%x}`, c)
		} else {
			b.WriteByte('[')
			for _, r := range set {
				fmt.Fprintf(&b, `\x{%x}`, r)
			}
			b.WriteByte(']')
		}
	}
	return b.String()
}
func replace(r *regexp2.Regexp, s, to string) (string, error) {
	return r.ReplaceFunc(s, func(regexp2.Match) string { return to }, -1, -1)
}

var sound = compile(`\[` + space + `*` + foldAlternatives("music|laughter|applause|noise|silence|inaudible|crosstalk") + space + `*\]`)

func foldAlternatives(s string) string {
	a := strings.Split(s, "|")
	for i := range a {
		a[i] = literalFold(a[i])
	}
	return "(?:" + strings.Join(a, "|") + ")"
}

var multipleSpace = compile(space + `{2,}`)

// StripMarkup removes only the explicit sound-tag list and three HTML entities.
func StripMarkup(s string) string {
	s = strings.NewReplacer("&gt;", "", "&lt;", "", "&amp;", "&").Replace(s)
	s, e := replace(sound, s, "")
	if e != nil {
		panic(e)
	}
	s, e = replace(multipleSpace, s, " ")
	if e != nil {
		panic(e)
	}
	return pycompat.Strip(s)
}

var repetition = compile(boundary + `(` + word + `{1,5})` + space + `+(?i:\1)` + boundary)
var filler = compile(`(?<!` + space + `)` + space + `+` + foldAlternatives("uh|um|er|ah|hmm") + boundary + space + `*,?` + space + `*`)
var mid = compile(`,` + space + `*` + foldAlternatives("you know|i mean|like") + space + `*,`)
var end = compile(`,` + space + `*` + foldAlternatives("you know|i mean|like") + space + `*(?=[.?!]|` + space + `*$)`)
var start = compile(`(?:(?<=^)|(?<=[.?!]))` + space + `*` + foldAlternatives("you know|i mean|like") + space + `*,` + space + `*`)
var punctuationSpace = compile(`(?<!` + space + `)` + space + `+([,.?!])`)
var contractions = []struct {
	r  *regexp2.Regexp
	to string
}{{compile(boundary + literalFold("gonna") + boundary), "going to"}, {compile(boundary + literalFold("wanna") + boundary), "want to"}, {compile(boundary + literalFold("gotta") + boundary), "got to"}, {compile(boundary + literalFold("kinda") + boundary), "kind of"}}

func CleanCaption(s string) (string, error) {
	t := " " + pycompat.Strip(s) + " "
	var e error
	for range 2 {
		t, e = repetition.ReplaceFunc(t, func(m regexp2.Match) string { return m.GroupByNumber(1).String() }, -1, -1)
		if e != nil {
			return "", e
		}
	}
	for _, x := range []struct {
		r  *regexp2.Regexp
		to string
	}{{filler, " "}, {mid, ", "}, {end, ""}, {start, " "}} {
		t, e = replace(x.r, t, x.to)
		if e != nil {
			return "", e
		}
	}
	for _, x := range contractions {
		t, e = x.r.ReplaceFunc(t, func(m regexp2.Match) string {
			r := []rune(m.String())
			if unicode.IsUpper(r[0]) {
				return pycompat.Capitalize(x.to)
			}
			return x.to
		}, -1, -1)
		if e != nil {
			return "", e
		}
	}
	t, e = replace(multipleSpace, t, " ")
	if e != nil {
		return "", e
	}
	t, e = punctuationSpace.ReplaceFunc(t, func(m regexp2.Match) string { return m.GroupByNumber(1).String() }, -1, -1)
	return pycompat.Strip(t), e
}

var phonetics = map[rune]string{'c': "ck", 'k': "ck", 'q': "ckq", 's': "sz", 'z': "sz", 'f': "f|ph", 'i': "iy", 'y': "iy"}

func phonetic(name string) string {
	var b strings.Builder
	for _, c := range pycompat.Lower(name) {
		if p, ok := phonetics[c]; ok {
			if strings.Contains(p, "|") {
				b.WriteString(foldAlternatives(p))
			} else {
				a := []string{}
				for _, r := range p {
					a = append(a, literalFold(string(r)))
				}
				b.WriteString("(?:" + strings.Join(a, "|") + ")")
			}
		} else {
			b.WriteString(literalFold(string(c)))
		}
	}
	return b.String()
}

var common = strings.Fields("apple orange amazon oracle square stripe slack meta shell sun gap target chase visa delta arc bolt lime")

func FixProperNouns(s string, names []string) (string, error) {
	for _, name := range names {
		name = pycompat.Strip(name)
		if pycompat.RuneLen(name) < 4 {
			continue
		}
		r := compile(boundary + phonetic(name) + boundary)
		m, e := r.FindStringMatch(s)
		if e != nil {
			return "", e
		}
		found, all := m != nil, true
		for m != nil {
			if pycompat.Lower(m.String()) != pycompat.Lower(name) {
				all = false
			}
			m, e = r.FindNextMatch(m)
			if e != nil {
				return "", e
			}
		}
		if found && all {
			isCommon := false
			for _, c := range common {
				if c == pycompat.Lower(name) {
					isCommon = true
				}
			}
			if !isCommon {
				replacement, e := parseReplacement(name)
				if e != nil {
					return "", e
				}
				s, e = compile(boundary+literalFold(name)+boundary).ReplaceFunc(s, func(m regexp2.Match) string { return replacement.expand(m.String()) }, -1, -1)
				if e != nil {
					return "", e
				}
			}
			continue
		}
		s, e = r.ReplaceFunc(s, func(m regexp2.Match) string {
			if pycompat.Lower(m.String()) != pycompat.Lower(name) {
				return name
			}
			return m.String()
		}, -1, -1)
		if e != nil {
			return "", e
		}
	}
	return s, nil
}

// Segment preserves unknown fields and their order through regrouping and IO.
type Segment = *pyjson.Object

func SegmentOf(start, end float64, s string) Segment {
	return pyjson.NewObject("start", start, "end", end, "text", s)
}
func Value(o *pyjson.Object, k string) any      { v, _ := o.Get(k); return v }
func Number(o *pyjson.Object, k string) float64 { n, _ := pyjson.Float(Value(o, k)); return n }
func String(o *pyjson.Object, k string) string  { v, _ := Value(o, k).(string); return v }
func Ends(s string) bool {
	return strings.HasSuffix(s, ".") || strings.HasSuffix(s, "?") || strings.HasSuffix(s, "!")
}
func EndsSentence(s string) bool {
	return Ends(pycompat.Strip(s)) || strings.HasSuffix(pycompat.Strip(s), "…")
}

type Word struct {
	Time float64
	Text string
}

func GroupWordsIntoSegments(words []Word) []Segment {
	segs := []Segment{}
	cur := []Word{}
	emit := func() {
		parts := []string{}
		for _, w := range cur {
			parts = append(parts, w.Text)
		}
		segs = append(segs, SegmentOf(pycompat.Round(cur[0].Time, 3), pycompat.Round(cur[len(cur)-1].Time+config.SegEndPad, 3), strings.Join(parts, " ")))
	}
	for _, w := range words {
		w.Text = StripMarkup(w.Text)
		if w.Text == "" {
			continue
		}
		if len(cur) == 0 {
			cur = append(cur, w)
			continue
		}
		parts := []string{}
		for _, x := range cur {
			parts = append(parts, x.Text)
		}
		prev := cur[len(cur)-1]
		if w.Time-prev.Time > config.SegMaxGap || Ends(prev.Text) || w.Time-cur[0].Time > config.SegMaxDur || pycompat.RuneLen(strings.Join(parts, " ")) > config.SegMaxChars {
			emit()
			cur = []Word{w}
		} else {
			cur = append(cur, w)
		}
	}
	if len(cur) > 0 {
		emit()
	}
	return segs
}
func floorDiv(n, d int) (int, int) {
	q, r := n/d, n%d
	if r < 0 {
		q--
		r += d
	}
	return q, r
}
func SrtTS(seconds float64) string {
	ms := pycompat.RoundInt(seconds * 1000)
	h, ms := floorDiv(ms, 3600000)
	m, ms := floorDiv(ms, 60000)
	s, ms := floorDiv(ms, 1000)
	return fmt.Sprintf("%02d:%02d:%02d,%03d", h, m, s, ms)
}
func MMSS(seconds float64) string {
	m, s := floorDiv(int(seconds), 60)
	return fmt.Sprintf("%02d:%02d", m, s)
}
func SnapToPunctuation(words []string, b int) int {
	for d := 0; d <= 2; d++ {
		behind := b - 1 - d
		if behind >= 0 && EndsSentence(words[behind]) {
			return behind + 1
		}
		ahead := b - 1 + d
		if ahead < len(words) && EndsSentence(words[ahead]) {
			return ahead + 1
		}
	}
	return b
}
func TrimText(s string, start, end float64) string {
	if start <= 0 && end >= 1 {
		return s
	}
	words := pycompat.Fields(s)
	n := len(words)
	if n == 0 {
		return s
	}
	a := max(0, min(n, pycompat.RoundInt(start*float64(n))))
	b := max(a, min(n, pycompat.RoundInt(end*float64(n))))
	if b-a < 1 {
		b = min(n, a+1)
	}
	if b < n {
		b = SnapToPunctuation(words, b)
	}
	if a > b {
		return ""
	}
	return strings.Join(words[a:b], " ")
}
