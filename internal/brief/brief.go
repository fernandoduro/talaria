// Package brief builds reading packets from prompts, metadata and transcript.
package brief

import (
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/curation"
	"github.com/fernandoduro/talaria/internal/episode"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/transcript"
	"os"
	"path/filepath"
	"strings"
)

func ReadableTranscript(pd string) (string, error) {
	segs, e := transcript.Read(pd)
	if e != nil {
		return "", e
	}
	a := []string{}
	for _, s := range segs {
		marker := ""
		if pyjson.Truthy(text.Value(s, "turn")) {
			marker = ">> "
		}
		a = append(a, fmt.Sprintf("[%s] %s%s", text.MMSS(text.Number(s, "start")), marker, text.String(s, "text")))
	}
	return strings.Join(a, "\n"), nil
}
func ReadableMetadata(pd string) (string, error) {
	ep, e := episode.Load(pd)
	if e != nil {
		return "", e
	}
	names, links, topics := []string{}, []string{}, []string{}
	for _, g := range curation.Objects(ep, "guests") {
		if pyjson.Truthy(text.Value(g, "name")) {
			names = append(names, text.String(g, "name")+" ("+text.String(g, "role")+")")
		}
		if pyjson.Truthy(text.Value(g, "linkedin")) {
			links = append(links, text.String(g, "linkedin"))
		}
	}
	if a, ok := text.Value(ep, "topics").([]any); ok {
		for _, s := range a {
			topics = append(topics, pyjson.Str(s))
		}
	}
	return fmt.Sprintf("- Season: %s\n- Episode number: %02d\n- Code: %s\n- Guest(s) and role: %s\n- Company or institution: %s\n- Recording city/state: %s/%s\n- Guest(s) LinkedIn: %s\n- Conversation topics: %s\n", pyjson.Str(text.Value(ep, "season")), int(text.Number(ep, "episode")), episode.Code(ep), strings.Join(names, "; "), text.String(ep, "company"), text.String(ep, "city"), text.String(ep, "uf"), strings.Join(links, "; "), strings.Join(topics, ", ")), nil
}
func FillTemplate(tpl, tr, meta, cur, clips string) string {
	for _, p := range [][2]string{{"{{TRANSCRIPT}}", tr}, {"{{METADATA}}", meta}, {"{{CURATION}}", cur}, {"{{CLIPS}}", clips}} {
		tpl = strings.ReplaceAll(tpl, p[0], p[1])
	}
	return tpl
}
func fallback(o *pyjson.Object, k, alt string) string {
	if o.Has(k) {
		return pyjson.Str(text.Value(o, k))
	}
	if o.Has(alt) {
		return pyjson.Str(text.Value(o, alt))
	}
	return ""
}
func ReadableCuration(state *pyjson.Object) string {
	approved, rejected := curation.Objects(state, "approved"), curation.Objects(state, "rejected")
	if len(approved) == 0 && len(rejected) == 0 {
		return "FIRST ROUND — no clip judged yet.\nPropose 10 stretches, ordered strongest to weakest."
	}
	rounds := text.Value(state, "rounds")
	if !state.Has("rounds") {
		rounds = 0
	}
	lines := []string{fmt.Sprintf("Round: %s", pyjson.Str(rounds)), fmt.Sprintf("Target: %s clips", pyjson.Str(text.Value(state, "target"))), fmt.Sprintf("Approved: %d", len(approved)), fmt.Sprintf("SLOTS LEFT: %d — propose exactly this many.", curation.SlotsLeft(state)), "", "COMPOSITION BY KIND:"}
	comp := curation.Composition(state)
	for k, v := range comp.All() {
		lines = append(lines, fmt.Sprintf("  %s: %s", k, pyjson.Str(v)))
	}
	if missing := curation.MissingKinds(state); len(missing) > 0 {
		lines = append(lines, "  MISSING KINDS (prioritise): "+strings.Join(missing, ", "))
	}
	lines = append(lines, "", "BURNED SPANS — propose nothing that overlaps them:")
	for _, c := range approved {
		lines = append(lines, fmt.Sprintf("  [%s-%s] APPROVED: %s", text.MMSS(text.Number(c, "start")), text.MMSS(text.Number(c, "end")), fallback(c, "screen_text", "slug")))
	}
	for _, r := range rejected {
		lines = append(lines, fmt.Sprintf("  [%s-%s] REJECTED (%s): %s", text.MMSS(text.Number(r, "start")), text.MMSS(text.Number(r, "end")), text.String(r, "reason"), text.String(r, "summary")))
	}
	if reasons := curation.Reasons(state); len(reasons) > 0 {
		lines = append(lines, "", "ACCUMULATED REJECTION REASONS — apply them as a filter:")
		for _, r := range reasons {
			lines = append(lines, "  - "+r)
		}
	}
	return strings.Join(lines, "\n")
}
func readPrompt(name string) (string, error) {
	root, e := config.Root()
	if e != nil {
		return "", e
	}
	p := filepath.Join(root, "prompts", name)
	b, e := os.ReadFile(p)
	if errors.Is(e, os.ErrNotExist) {
		return "", fmt.Errorf("prompt not found: %s", p)
	}
	return string(b), e
}
func write(pd, kind, s string) (string, error) {
	p, e := layout.EnsureDir(layout.Brief(pd, kind))
	if e != nil {
		return "", e
	}
	return p, os.WriteFile(p, []byte(s), 0644)
}
func Build(pd, kind string) (string, error) {
	if kind != "materials" && kind != "clips" {
		return "", fmt.Errorf("kind must be 'materials' or 'clips'")
	}
	tpl, e := readPrompt(kind + ".md")
	if e != nil {
		return "", e
	}
	cur := ""
	if kind == "clips" {
		s, e := curation.Load(pd)
		if e != nil {
			return "", e
		}
		cur = ReadableCuration(s)
	}
	tr, e := ReadableTranscript(pd)
	if e != nil {
		return "", e
	}
	meta, e := ReadableMetadata(pd)
	if e != nil {
		return "", e
	}
	return write(pd, kind, FillTemplate(tpl, tr, meta, cur, ""))
}
func ClipSpeech(pd string, clip *pyjson.Object) (string, error) {
	segs, e := transcript.Read(pd)
	if e != nil {
		return "", e
	}
	parts := []string{}
	a, b := text.Number(clip, "start"), text.Number(clip, "end")
	for _, s := range segs {
		start, end := text.Number(s, "start"), text.Number(s, "end")
		if end <= a || start >= b {
			continue
		}
		txt := pycompat.Strip(text.String(s, "text"))
		if txt == "" {
			continue
		}
		if (start < a || end > b) && end-start > 0 {
			txt = text.TrimText(txt, (max(start, a)-start)/(end-start), (min(end, b)-start)/(end-start))
		}
		if txt != "" {
			parts = append(parts, txt)
		}
	}
	return pycompat.Strip(strings.Join(parts, " ")), nil
}
func ReadableClips(pd string, clips []*pyjson.Object) (string, error) {
	parts := []string{}
	for _, c := range clips {
		speech, e := ClipSpeech(pd, c)
		if e != nil {
			return "", e
		}
		parts = append(parts, fmt.Sprintf("### %s  [%s–%s]\n\n- Kind: %s\n- Video screen text: %s\n\nLiteral speech:\n\n%s\n", text.String(c, "slug"), text.MMSS(text.Number(c, "start")), text.MMSS(text.Number(c, "end")), text.String(c, "kind"), text.String(c, "screen_text"), speech))
	}
	return strings.Join(parts, "\n"), nil
}
func BuildPosts(pd string, clips []*pyjson.Object) (string, error) {
	tpl, e := readPrompt("posts.md")
	if e != nil {
		return "", e
	}
	meta, e := ReadableMetadata(pd)
	if e != nil {
		return "", e
	}
	cl, e := ReadableClips(pd, clips)
	if e != nil {
		return "", e
	}
	limit := fmt.Sprintf("At most %d lines per card, about 100 characters. The reference quote has 97.\n", config.PostQuoteMaxLines)
	return write(pd, "posts", FillTemplate(tpl, "", meta+"\n"+limit, "", cl))
}
