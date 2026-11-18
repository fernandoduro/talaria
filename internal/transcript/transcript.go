// Package transcript parses YouTube text/rolling VTT and reads/writes transcripts.
package transcript

import (
	"fmt"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"io"
	"os"
	"regexp"
	"strings"
)

type Segment = text.Segment

const (
	Host  = "host"
	Guest = "guest"
)

var tsLine = regexp.MustCompile(`^(\p{Nd}{1,2}):(\p{Nd}{2})(?::(\p{Nd}{2}))?$`)

func digits(s string) int {
	n := 0
	for _, r := range s {
		n = n*10 + pycompat.DecimalValue(r)
	}
	return n
}
func ParseTxt(path string, totalDuration *float64) ([]Segment, error) {
	b, e := os.ReadFile(path)
	if e != nil {
		return nil, e
	}
	return ParseTxtString(string(b), totalDuration), nil
}
func ParseTxtString(s string, totalDuration *float64) []Segment {
	type block struct {
		start float64
		lines []string
	}
	blocks := []block{}
	var cur *block
	for _, line := range pycompat.SplitLines(s) {
		line = pycompat.Strip(line)
		m := tsLine.FindStringSubmatch(line)
		if m != nil {
			if cur != nil {
				blocks = append(blocks, *cur)
			}
			t := digits(m[1])*60 + digits(m[2])
			if m[3] != "" {
				t = digits(m[1])*3600 + digits(m[2])*60 + digits(m[3])
			}
			cur = &block{start: float64(t)}
		} else if line != "" && cur != nil {
			cur.lines = append(cur.lines, line)
		}
	}
	if cur != nil {
		blocks = append(blocks, *cur)
	}
	raw := []Segment{}
	for i, b := range blocks {
		txt := pycompat.Strip(strings.Join(b.lines, " "))
		if txt == "" {
			continue
		}
		turn := strings.HasPrefix(txt, ">>")
		txt = text.StripMarkup(pycompat.Strip(strings.TrimLeft(txt, "> ")))
		if txt == "" {
			continue
		}
		end := b.start + max(1, float64(len(pycompat.Fields(txt)))/145*60)
		if i+1 < len(blocks) {
			end = blocks[i+1].start
		} else if totalDuration != nil && *totalDuration != 0 {
			end = *totalDuration
		}
		o := text.SegmentOf(b.start, pycompat.Round(end, 3), txt)
		o.Set("turn", turn)
		raw = append(raw, o)
	}
	return ResolveSpeakers(RegroupIntoSentences(raw))
}
func RegroupIntoSentences(blocks []Segment) []Segment {
	segs := []Segment{}
	var cur Segment
	for _, b := range blocks {
		if cur == nil {
			cur = b.Clone()
			continue
		}
		if text.Ends(pycompat.Strip(text.String(cur, "text"))) || pyjson.Truthy(text.Value(b, "turn")) || text.Number(b, "end")-text.Number(cur, "start") > config.SegMaxDur*2 || pycompat.RuneLen(text.String(cur, "text")) > config.SegMaxChars*2 {
			segs = append(segs, cur)
			cur = b.Clone()
		} else {
			cur.Set("text", pycompat.Strip(text.String(cur, "text")+" "+text.String(b, "text")))
			cur.Set("end", text.Value(b, "end"))
		}
	}
	if cur != nil {
		segs = append(segs, cur)
	}
	return segs
}
func ResolveSpeakers(segs []Segment) []Segment {
	current := Host
	for i, s := range segs {
		if i > 0 && pyjson.Truthy(text.Value(s, "turn")) {
			if current == Host {
				current = Guest
			} else {
				current = Host
			}
		}
		s.Set("speaker", current)
	}
	return segs
}

var cue = regexp.MustCompile(`^(\p{Nd}{2}:\p{Nd}{2}:\p{Nd}{2}\.\p{Nd}{3}) --> (\p{Nd}{2}:\p{Nd}{2}:\p{Nd}{2}\.\p{Nd}{3})`)
var inline = regexp.MustCompile(`<(\p{Nd}{2}:\p{Nd}{2}:\p{Nd}{2}\.\p{Nd}{3})><c>(.*?)</c>`)
var tags = regexp.MustCompile(`<[^>]+>`)

func VttTSToSec(s string) float64 {
	p := strings.FieldsFunc(s, func(r rune) bool { return r == ':' || r == '.' })
	if len(p) != 4 {
		return 0
	}
	return float64(digits(p[0])*3600+digits(p[1])*60+digits(p[2])) + float64(digits(p[3]))/1000
}
func ParseVTT(path string) ([]Segment, error) {
	b, e := os.ReadFile(path)
	if e != nil {
		return nil, e
	}
	lines := pycompat.SplitLines(string(b))
	words := []text.Word{}
	for i := 0; i < len(lines); {
		m := cue.FindStringSubmatch(lines[i])
		if m == nil {
			i++
			continue
		}
		t := VttTSToSec(m[1])
		i++
		buf := []string{}
		for i < len(lines) && pycompat.Strip(lines[i]) != "" && !cue.MatchString(lines[i]) {
			buf = append(buf, lines[i])
			i++
		}
		newline := ""
		found := false
		for _, l := range buf {
			if strings.Contains(l, "<c>") {
				newline = l
				found = true
				break
			}
		}
		if !found {
			continue
		}
		matches := inline.FindAllStringSubmatchIndex(newline, -1)
		head := newline
		if len(matches) > 0 {
			head = newline[:matches[0][0]]
		}
		for _, w := range pycompat.Fields(tags.ReplaceAllString(head, "")) {
			words = append(words, text.Word{Time: t, Text: w})
		}
		for _, m := range matches {
			t = VttTSToSec(newline[m[2]:m[3]])
			for _, w := range pycompat.Fields(tags.ReplaceAllString(newline[m[4]:m[5]], "")) {
				words = append(words, text.Word{Time: t, Text: w})
			}
		}
	}
	return text.GroupWordsIntoSegments(words), nil
}
func Read(pd string) ([]Segment, error) {
	o, e := pyjson.ReadObject(layout.Transcript(pd))
	if e != nil {
		return nil, e
	}
	return Objects(text.Value(o, "segments"))
}
func Objects(v any) ([]*pyjson.Object, error) {
	out := []*pyjson.Object{}
	switch a := v.(type) {
	case nil:
		return out, nil
	case []*pyjson.Object:
		return a, nil
	case []any:
		for _, v := range a {
			o, ok := v.(*pyjson.Object)
			if !ok {
				return nil, fmt.Errorf("expected object, got %s", pyjson.TypeName(v))
			}
			out = append(out, o)
		}
		return out, nil
	}
	return nil, fmt.Errorf("expected list, got %s", pyjson.TypeName(v))
}
func WriteOutputs(segs []Segment, pd string, out io.Writer) error {
	path, e := layout.EnsureDir(layout.Transcript(pd))
	if e != nil {
		return e
	}
	if e = pyjson.WriteFile(path, pyjson.NewObject("segments", segs)); e != nil {
		return e
	}
	var b strings.Builder
	cur := []string{}
	start := 0.0
	blocks := 0
	for _, s := range segs {
		if len(cur) == 0 {
			start = text.Number(s, "start")
		}
		cur = append(cur, text.String(s, "text"))
		if text.Number(s, "end")-start >= 25 {
			fmt.Fprintf(&b, "[%s-%s] %s\n\n", text.MMSS(start), text.MMSS(text.Number(s, "end")), strings.Join(cur, " "))
			cur = nil
			blocks++
		}
	}
	if len(cur) > 0 {
		fmt.Fprintf(&b, "[%s-%s] %s\n\n", text.MMSS(start), text.MMSS(text.Number(segs[len(segs)-1], "end")), strings.Join(cur, " "))
		blocks++
	}
	path, e = layout.EnsureDir(layout.TranscriptTxt(pd))
	if e != nil {
		return e
	}
	if e = os.WriteFile(path, []byte(b.String()), 0644); e != nil {
		return e
	}
	dur := "00:00"
	if len(segs) > 0 {
		dur = text.MMSS(text.Number(segs[len(segs)-1], "end"))
	}
	if out != nil {
		fmt.Fprintf(out, "[transcribe] %d segments, %d blocks, duration %s\n", len(segs), blocks, dur)
	}
	return nil
}
