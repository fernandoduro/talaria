// Package curation implements iterative approval, burned spans and clip checks.
package curation

import (
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/transcript"
	"math"
	"os"
	"regexp"
	"sort"
	"strings"
)

type Span [2]float64

var Kinds = []string{"story", "thesis", "advice", "personal"}

const OverlapThreshold = 0.30

func NewState(target int) *pyjson.Object {
	return pyjson.NewObject("target", target, "approved", []*pyjson.Object{}, "rejected", []*pyjson.Object{}, "rounds", 0)
}
func Objects(o *pyjson.Object, k string) []*pyjson.Object {
	a, _ := transcript.Objects(text.Value(o, k))
	return a
}
func Overlaps(a, b Span, threshold ...float64) bool {
	th := OverlapThreshold
	if len(threshold) > 0 {
		th = threshold[0]
	}
	overlap := min(a[1], b[1]) - max(a[0], b[0])
	smaller := min(a[1]-a[0], b[1]-b[0])
	return overlap > 0 && smaller > 0 && overlap/smaller >= th
}
func BurnedSpans(state *pyjson.Object) []Span {
	out := []Span{}
	for _, k := range []string{"approved", "rejected"} {
		for _, o := range Objects(state, k) {
			if o.Has("start") && o.Has("end") {
				out = append(out, Span{text.Number(o, "start"), text.Number(o, "end")})
			}
		}
	}
	return out
}
func IsBurned(span Span, state *pyjson.Object) bool {
	for _, s := range BurnedSpans(state) {
		if Overlaps(span, s) {
			return true
		}
	}
	return false
}
func SlotsLeft(state *pyjson.Object) int {
	return max(0, int(text.Number(state, "target"))-len(Objects(state, "approved")))
}
func Load(pd string, target ...int) (*pyjson.Object, error) {
	n := 5
	if len(target) > 0 {
		n = target[0]
	}
	o, e := pyjson.ReadObject(layout.Curation(pd))
	if errors.Is(e, os.ErrNotExist) {
		return NewState(n), nil
	}
	return o, e
}
func saveAt(p string, v any) (string, error) {
	p, e := layout.EnsureDir(p)
	if e != nil {
		return "", e
	}
	return p, pyjson.WriteFile(p, v)
}
func Save(pd string, state *pyjson.Object) (string, error) { return saveAt(layout.Curation(pd), state) }

// Stdlib RE2 does not have Python's Unicode boundary or ignore-case sets.
// These patterns use a lowercased search buffer, expanded ASCII special-case
// letters, Unicode Nd, and explicit adjacent-character word checks.
var hedged = regexp.MustCompile(`(about|around|approximately|roughly|[sſ]ome|maybe|[iı] th[iı]n[kK]|[iı]f [iı] remember|more or le[sſ][sſ]|or [sſ]o|g[iı]ve or ta[kK]e)`)
var figure = regexp.MustCompile(`^[^.!?]{0,40}?\p{Nd}`)
var first = regexp.MustCompile(`(my company|our company|our team|our own|my co-?founder|our f[iı]r[sſ]t h[iı]re)`)

func markerMatches(r *regexp.Regexp, s string, after func(string) bool) bool {
	low := []rune{}
	for _, c := range s {
		low = append(low, pycompat.ReLower(c))
	}
	str := string(low)
	for _, ix := range r.FindAllStringIndex(str, -1) {
		before := []rune(str[:ix[0]])
		tail := []rune(str[ix[1]:])
		if len(before) > 0 && pycompat.IsWord(before[len(before)-1]) {
			continue
		}
		if len(tail) > 0 && pycompat.IsWord(tail[0]) {
			continue
		}
		if after == nil || after(string(tail)) {
			return true
		}
	}
	return false
}
func HasHedgedNumber(s string) bool {
	return markerMatches(hedged, s, func(t string) bool { return figure.MatchString(t) })
}
func HasFirstPerson(s string) bool { return markerMatches(first, s, nil) }
func ValidBoundary(t float64, segs []text.Segment) bool {
	for _, s := range segs {
		if math.Abs(text.Number(s, "start")-t) <= .5 || math.Abs(text.Number(s, "end")-t) <= .5 {
			return true
		}
	}
	return false
}
func EndsSentence(t float64, segs []text.Segment) bool {
	for _, s := range segs {
		if math.Abs(text.Number(s, "end")-t) <= .5 {
			return text.EndsSentence(text.String(s, "text"))
		}
	}
	return false
}
func SegmentsInClip(span Span, segs []text.Segment) []text.Segment {
	out := []text.Segment{}
	for _, s := range segs {
		if text.Number(s, "end") > span[0] && text.Number(s, "start") < span[1] {
			out = append(out, s)
		}
	}
	return out
}
func GuestSpeechFraction(span Span, segs []text.Segment) float64 {
	inside := SegmentsInClip(span, segs)
	if len(inside) == 0 {
		return 0
	}
	total, guest := 0.0, 0.0
	for _, s := range inside {
		if text.Value(s, "speaker") == nil {
			continue
		}
		dur := min(text.Number(s, "end"), span[1]) - max(text.Number(s, "start"), span[0])
		if dur <= 0 {
			continue
		}
		total += dur
		if text.String(s, "speaker") == "guest" {
			guest += dur
		}
	}
	if total == 0 {
		return 1
	}
	return guest / total
}

type SentenceEnd struct {
	Instant, Duration float64
	Context           string
}

func SentenceEnds(segs []text.Segment, start, lo, hi float64) []SentenceEnd {
	out := []SentenceEnd{}
	for _, s := range segs {
		a, b := text.Number(s, "start"), text.Number(s, "end")
		if b < lo || a > hi {
			continue
		}
		txt := []rune(text.String(s, "text"))
		for i, c := range txt {
			if !strings.ContainsRune(".!?…", c) {
				continue
			}
			inst := a + (b-a)*(float64(i+1)/float64(len(txt)))
			d := inst - start
			if inst >= lo && inst <= hi && d >= 60 && d <= 90 {
				out = append(out, SentenceEnd{pycompat.Round(inst, 2), pycompat.Round(d, 1), pycompat.Strip(string(txt[max(0, i+1-50) : i+1]))})
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Instant != b.Instant {
			return a.Instant < b.Instant
		}
		if a.Duration != b.Duration {
			return a.Duration < b.Duration
		}
		return a.Context < b.Context
	})
	return out
}
func ValidateClip(span Span, segs []text.Segment, state *pyjson.Object) (bool, []string) {
	msgs := []string{}
	dur := span[1] - span[0]
	if dur < 60 {
		msgs = append(msgs, fmt.Sprintf("duration %.0fs below the minimum of 60s", dur))
	} else if dur > 90 {
		msgs = append(msgs, fmt.Sprintf("duration %.0fs above the maximum of 90s", dur))
	}
	if len(segs) > 0 && !ValidBoundary(span[0], segs) {
		msgs = append(msgs, fmt.Sprintf("start %.1fs does not land on a sentence boundary", span[0]))
	}
	if len(segs) > 0 && ValidBoundary(span[1], segs) && !EndsSentence(span[1], segs) {
		msgs = append(msgs, fmt.Sprintf("end %.1fs does not close a sentence (it cuts the speech mid-way)", span[1]))
	}
	if state != nil && state.Len() > 0 && IsBurned(span, state) {
		msgs = append(msgs, "overlaps a burned span (approved or rejected)")
	}
	return len(msgs) == 0, msgs
}
func AttributionTrustworthy(segs []text.Segment) bool {
	total, firstPerson := 0.0, 0.0
	for _, s := range segs {
		if text.String(s, "speaker") != "host" {
			continue
		}
		dur := text.Number(s, "end") - text.Number(s, "start")
		total += dur
		if HasFirstPerson(text.String(s, "text")) {
			firstPerson += dur
		}
	}
	return total <= 0 || firstPerson/total < .30
}
func HostOpening(span Span, segs []text.Segment) float64 {
	total := 0.0
	for _, s := range SegmentsInClip(span, segs) {
		if text.Value(s, "speaker") == nil {
			return 0
		}
		if text.String(s, "speaker") != "host" {
			break
		}
		total += min(text.Number(s, "end"), span[1]) - max(text.Number(s, "start"), span[0])
	}
	return total
}
func ClipWarnings(span Span, segs []text.Segment) []string {
	alerts := []string{}
	for _, s := range SegmentsInClip(span, segs) {
		txt := text.String(s, "text")
		if HasHedgedNumber(txt) {
			alerts = append(alerts, fmt.Sprintf("hedged figure at %.0fs: \"%s\"", text.Number(s, "start"), pycompat.RuneSlice(txt, 0, 60)))
		}
	}
	if !AttributionTrustworthy(segs) {
		return alerts
	}
	frac := GuestSpeechFraction(span, segs)
	if frac < .5 {
		alerts = append(alerts, fmt.Sprintf("guest speaks only %.0f%% of the clip", frac*100))
	}
	host := HostOpening(span, segs)
	if host >= 8 {
		alerts = append(alerts, fmt.Sprintf("clip opens with %.0fs of host speech — the cold viewer leaves before the guest talks", host))
	}
	return alerts
}
func Approve(state, clip *pyjson.Object) error {
	a := Objects(state, "approved")
	span := Span{text.Number(clip, "start"), text.Number(clip, "end")}
	for i, c := range a {
		if pyjson.Equal(text.Value(c, "slug"), text.Value(clip, "slug")) {
			a[i] = clip
			state.Set("approved", a)
			return nil
		}
		if Overlaps(span, Span{text.Number(c, "start"), text.Number(c, "end")}, 0) {
			return fmt.Errorf("clip %s overlaps approved clip %s (%.0f-%.0fs)", pyjson.Str(text.Value(clip, "slug")), pyjson.Str(text.Value(c, "slug")), text.Number(c, "start"), text.Number(c, "end"))
		}
	}
	if len(a) >= int(text.Number(state, "target")) {
		return fmt.Errorf("target of %s clips already met", pyjson.Str(text.Value(state, "target")))
	}
	state.Set("approved", append(a, clip))
	return nil
}
func Reject(state, clip *pyjson.Object, reason string) {
	summary := text.Value(clip, "summary")
	if !clip.Has("summary") {
		summary = text.Value(clip, "screen_text")
		if !clip.Has("screen_text") {
			summary = ""
		}
	}
	r := pyjson.NewObject("start", text.Number(clip, "start"), "end", text.Number(clip, "end"), "summary", summary, "reason", reason)
	state.Set("rejected", append(Objects(state, "rejected"), r))
}
func Composition(state *pyjson.Object) *pyjson.Object {
	o := pyjson.NewObject()
	for _, k := range Kinds {
		o.Set(k, 0)
	}
	for _, c := range Objects(state, "approved") {
		k := text.String(c, "kind")
		if o.Has(k) {
			o.Set(k, int(text.Number(o, k))+1)
		}
	}
	return o
}
func MissingKinds(state *pyjson.Object) []string {
	a := []string{}
	c := Composition(state)
	for _, k := range Kinds {
		if text.Number(c, k) == 0 {
			a = append(a, k)
		}
	}
	return a
}
func Reasons(state *pyjson.Object) []string {
	out := []string{}
	seen := map[string]bool{}
	for _, r := range Objects(state, "rejected") {
		s := pycompat.Strip(text.String(r, "reason"))
		if s != "" && !seen[s] {
			out = append(out, s)
			seen[s] = true
		}
	}
	return out
}
func IsClosed(state *pyjson.Object) bool {
	return len(Objects(state, "approved")) >= int(text.Number(state, "target"))
}
func ToMoments(state *pyjson.Object) ([]*pyjson.Object, error) {
	a := Objects(state, "approved")
	if len(a) == 0 {
		return nil, fmt.Errorf("no approved clip — nothing to export")
	}
	out := make([]*pyjson.Object, len(a))
	for i, c := range a {
		out[i] = c.Clone()
	}
	return out, nil
}
func SaveMoments(pd string, state *pyjson.Object) (string, error) {
	a, e := ToMoments(state)
	if e != nil {
		return "", e
	}
	return saveAt(layout.Moments(pd), a)
}
