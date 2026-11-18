// Package parity_test replays the Python unittest oracle without running Python.
// Each original test is a named Go subtest; every observed API call is checked
// for its result, argument mutations, warning bytes and full filesystem effects.
package parity_test

import (
	"bytes"
	"fmt"
	"github.com/fernandoduro/talaria/internal/brief"
	"github.com/fernandoduro/talaria/internal/caption"
	"github.com/fernandoduro/talaria/internal/curation"
	"github.com/fernandoduro/talaria/internal/dotenv"
	"github.com/fernandoduro/talaria/internal/episode"
	"github.com/fernandoduro/talaria/internal/golden"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/posts"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/schedule"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/texts"
	"github.com/fernandoduro/talaria/internal/transcript"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

func val(o *pyjson.Object, k string) any { return text.Value(o, k) }
func obj(v any) *pyjson.Object           { o, _ := v.(*pyjson.Object); return o }
func list(v any) []any                   { a, _ := v.([]any); return a }
func str(v any) string                   { s, _ := v.(string); return s }
func number(v any) float64               { f, _ := pyjson.Float(v); return f }
func objects(v any) []*pyjson.Object {
	a, e := transcript.Objects(v)
	if e != nil {
		panic(e)
	}
	return a
}
func strs(v any) []string {
	if v == nil {
		return nil
	}
	out := []string{}
	for _, s := range list(v) {
		out = append(out, str(s))
	}
	return out
}
func rewrite(v any, r *strings.Replacer) any {
	switch x := v.(type) {
	case string:
		return r.Replace(x)
	case []any:
		a := make([]any, len(x))
		for i, v := range x {
			a[i] = rewrite(v, r)
		}
		return a
	case *pyjson.Object:
		o := pyjson.NewObject()
		for k, v := range x.All() {
			o.Set(r.Replace(k), rewrite(v, r))
		}
		return o
	}
	return v
}
func canonical(v any) []byte {
	b, e := pyjson.Marshal(v)
	if e != nil {
		panic(e)
	}
	return b
}
func equal(t *testing.T, label string, got, want any) {
	t.Helper()
	g, w := canonical(got), canonical(want)
	if !bytes.Equal(g, w) {
		t.Fatalf("%s\ngot:  %s\nwant: %s", label, g, w)
	}
}
func restore(t *testing.T, trees *pyjson.Object, r *strings.Replacer) {
	t.Helper()
	if trees == nil {
		return
	}
	for root, v := range trees.All() {
		p := r.Replace(root)
		if e := os.RemoveAll(p); e != nil {
			t.Fatal(e)
		}
		if e := os.MkdirAll(p, 0755); e != nil {
			t.Fatal(e)
		}
		for rel, content := range obj(v).All() {
			path := filepath.Join(p, rel)
			if content == nil {
				if e := os.MkdirAll(path, 0755); e != nil {
					t.Fatal(e)
				}
			} else {
				if e := os.MkdirAll(filepath.Dir(path), 0755); e != nil {
					t.Fatal(e)
				}
				if e := os.WriteFile(path, []byte(r.Replace(str(content))), 0644); e != nil {
					t.Fatal(e)
				}
			}
		}
	}
}
func snapshot(t *testing.T, trees *pyjson.Object, expand, normalize *strings.Replacer) any {
	t.Helper()
	out := pyjson.NewObject()
	if trees == nil {
		return nil
	}
	for root := range trees.All() {
		tree := pyjson.NewObject()
		p := expand.Replace(root)
		paths := []string{}
		err := filepath.WalkDir(p, func(path string, d fs.DirEntry, e error) error {
			if e != nil {
				return e
			}
			if path != p {
				paths = append(paths, path)
			}
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
		sort.Strings(paths)
		for _, path := range paths {
			rel, _ := filepath.Rel(p, path)
			st, e := os.Stat(path)
			if e != nil {
				t.Fatal(e)
			}
			if st.IsDir() {
				tree.Set(rel, nil)
			} else {
				b, e := os.ReadFile(path)
				if e != nil {
					t.Fatal(e)
				}
				tree.Set(rel, normalize.Replace(string(b)))
			}
		}
		out.Set(root, tree)
	}
	return out
}
func TestExtra(t *testing.T)  { runReplay(t, "g1/extra.json", 0) }
func TestReplay(t *testing.T) { runReplay(t, "g1/replay.json", 245) }
func runReplay(t *testing.T, file string, count int) {
	v, e := pyjson.Unmarshal(golden.Read(t, file))
	if e != nil {
		t.Fatal(e)
	}
	rows := objects(v)
	if count > 0 && len(rows) != count {
		t.Fatalf("%d original tests, want 245", len(rows))
	}
	root := filepath.Dir(filepath.Dir(golden.Dir(t)))
	for _, row := range rows {
		t.Run(str(val(row, "name")), func(t *testing.T) {
			base := t.TempDir()
			expandKV := []string{"<ROOT>", root}
			normalizeKV := []string{root, "<ROOT>"}
			for i := 0; i < 30; i++ {
				tag := fmt.Sprintf("<TMP%d>", i)
				path := filepath.Join(base, fmt.Sprintf("tmp%d", i))
				expandKV = append(expandKV, tag, path)
				normalizeKV = append(normalizeKV, path, tag)
			}
			expand, normalize := strings.NewReplacer(expandKV...), strings.NewReplacer(normalizeKV...)
			t.Setenv("TALARIA_ROOT", root)
			for index, c := range objects(val(row, "calls")) {
				op := str(val(c, "op"))
				t.Run(fmt.Sprintf("%03d_%s", index, op), func(t *testing.T) {
					restore(t, obj(val(c, "before")), expand)
					env := obj(val(c, "env_before"))
					if env != nil {
						for k, v := range env.All() {
							old, set := os.LookupEnv(k)
							t.Cleanup(func() {
								if set {
									os.Setenv(k, old)
								} else {
									os.Unsetenv(k)
								}
							})
							if v == nil {
								os.Unsetenv(k)
							} else {
								os.Setenv(k, str(v))
							}
						}
					}
					input := rewrite(val(c, "input"), expand)
					args := list(input)
					var a []any
					kw := pyjson.NewObject()
					if len(args) > 0 {
						a = list(args[0])
						kw = obj(args[1])
					}
					var stdout bytes.Buffer
					got, err := invoke(op, a, kw, &stdout, val(c, "error") != nil && str(list(val(c, "error"))[0]) == "KeyboardInterrupt")
					if expected := list(val(c, "error")); expected != nil {
						if err == nil {
							t.Fatalf("%s: expected %s, got success %s", op, str(expected[1]), canonical(got))
						}
						message := normalize.Replace(err.Error())
						if message != str(expected[1]) {
							t.Fatalf("error got %q, want %q", message, str(expected[1]))
						}
					} else {
						if err != nil {
							t.Fatalf("%s: %v", op, err)
						}
						equal(t, "result", rewrite(got, normalize), val(c, "result"))
					}
					if c.Has("args_after") {
						equal(t, "mutated arguments", rewrite(input, normalize), val(c, "args_after"))
					}
					if c.Has("stdout") {
						equal(t, "stdout", normalize.Replace(stdout.String()), val(c, "stdout"))
					}
					if after := obj(val(c, "after")); after != nil {
						actual := snapshot(t, after, expand, normalize)
						if !pyjson.Equal(actual, after) {
							equal(t, "filesystem bytes", actual, after)
						}
					}
					if envAfter := obj(val(c, "env_after")); envAfter != nil {
						got := pyjson.NewObject()
						for k := range envAfter.All() {
							if v, set := os.LookupEnv(k); set {
								got.Set(k, v)
							} else {
								got.Set(k, nil)
							}
						}
						equal(t, "environment", got, envAfter)
					}
				})
			}
		})
	}
}
func invoke(op string, a []any, kw *pyjson.Object, out *bytes.Buffer, interrupt bool) (any, error) {
	get := func(i int, key string, def any) any {
		if i < len(a) {
			return a[i]
		}
		if kw != nil && kw.Has(key) {
			return val(kw, key)
		}
		return def
	}
	s := func(i int) string { return str(a[i]) }
	o := func(i int) *pyjson.Object { return obj(a[i]) }
	n := func(i int) float64 { return number(a[i]) }
	span := func(i int) curation.Span { p := list(a[i]); return curation.Span{number(p[0]), number(p[1])} }
	switch op {
	case "utils.group_words_into_segments":
		words := []text.Word{}
		for _, v := range list(a[0]) {
			p := list(v)
			words = append(words, text.Word{Time: number(p[0]), Text: str(p[1])})
		}
		return text.GroupWordsIntoSegments(words), nil
	case "render._trim_text":
		return text.TrimText(s(0), n(1), n(2)), nil
	case "vtt_parse.parse_vtt":
		return transcript.ParseVTT(s(0))
	case "transcribe._write_outputs":
		return nil, transcript.WriteOutputs(objects(a[0]), s(1), out)
	case "curation.save":
		return curation.Save(s(0), o(1))
	case "curation.save_moments":
		return curation.SaveMoments(s(0), o(1))
	case "brief.build":
		return brief.Build(s(0), s(1))
	case "utils.mmss":
		return text.MMSS(n(0)), nil
	case "utils.srt_ts":
		return text.SrtTS(n(0)), nil
	case "utils.strip_markup":
		return text.StripMarkup(s(0)), nil
	case "utils.clean_caption":
		return text.CleanCaption(s(0))
	case "utils.fix_proper_nouns":
		return text.FixProperNouns(s(0), strs(a[1]))
	case "txt_parse.parse_txt":
		var d *float64
		if v := get(1, "total_duration", nil); v != nil {
			x := number(v)
			d = &x
		}
		return transcript.ParseTxt(s(0), d)
	case "txt_parse.regroup_into_sentences":
		return transcript.RegroupIntoSentences(objects(a[0])), nil
	case "txt_parse.resolve_speakers":
		return transcript.ResolveSpeakers(objects(a[0])), nil
	case "episode.template":
		return episode.Template(), nil
	case "episode.required_fields":
		return episode.RequiredFields, nil
	case "episode.load":
		return episode.Load(s(0))
	case "episode.save":
		return episode.Save(s(0), o(1))
	case "episode.code":
		return episode.Code(o(0)), nil
	case "episode.youtube_url":
		return episode.YouTubeURL(s(0)), nil
	case "layout.ensure_dir":
		return layout.EnsureDir(s(0))
	case "layout.episode":
		return layout.Episode(s(0)), nil
	case "layout.video":
		return layout.Video(s(0)), nil
	case "layout.transcript":
		return layout.Transcript(s(0)), nil
	case "layout.transcript_txt":
		return layout.TranscriptTxt(s(0)), nil
	case "layout.source_dir":
		return layout.SourceDir(s(0)), nil
	case "layout.curation":
		return layout.Curation(s(0)), nil
	case "layout.moments":
		return layout.Moments(s(0)), nil
	case "layout.texts":
		return layout.Texts(s(0)), nil
	case "layout.posts":
		return layout.Posts(s(0)), nil
	case "layout.schedule":
		return layout.Schedule(s(0)), nil
	case "layout.published":
		return layout.Published(s(0)), nil
	case "layout.brief":
		return layout.Brief(s(0), s(1)), nil
	case "layout.thumbnail":
		return layout.Thumbnail(s(0)), nil
	case "layout.end_card_mp4":
		return layout.EndCardMP4(s(0)), nil
	case "layout.episode_txt":
		return layout.EpisodeTxt(s(0)), nil
	case "layout.platform":
		return layout.Platform(s(0), s(1)), nil
	case "layout.posts_png":
		return layout.PostsPNG(s(0)), nil
	case "layout.migrate":
		var moves []layout.Move
		var err error
		if interrupt {
			count := 0
			moves, err = layout.MigrateWithMove(s(0), func(a, b string) error {
				count++
				if count == 3 {
					return fmt.Errorf("simulates ctrl-c partway")
				}
				return os.Rename(a, b)
			})
		} else {
			moves, err = layout.Migrate(s(0))
		}
		x := []any{}
		for _, m := range moves {
			x = append(x, []string{m[0], m[1]})
		}
		return x, err
	case "curation.new_state":
		return curation.NewState(int(number(get(0, "target", int64(5))))), nil
	case "curation.overlaps":
		return curation.Overlaps(span(0), span(1), number(get(2, "threshold", .30))), nil
	case "curation.burned_spans":
		x := []any{}
		for _, p := range curation.BurnedSpans(o(0)) {
			x = append(x, []any{p[0], p[1]})
		}
		return x, nil
	case "curation.is_burned":
		return curation.IsBurned(span(0), o(1)), nil
	case "curation.slots_left":
		return curation.SlotsLeft(o(0)), nil
	case "curation.has_hedged_number":
		return curation.HasHedgedNumber(s(0)), nil
	case "curation.has_first_person":
		return curation.HasFirstPerson(s(0)), nil
	case "curation.guest_speech_fraction":
		return curation.GuestSpeechFraction(span(0), objects(a[1])), nil
	case "curation.host_opening":
		return curation.HostOpening(span(0), objects(a[1])), nil
	case "curation.clip_warnings":
		return curation.ClipWarnings(span(0), objects(a[1])), nil
	case "curation.attribution_trustworthy":
		return curation.AttributionTrustworthy(objects(a[0])), nil
	case "curation.sentence_ends":
		x := []any{}
		for _, p := range curation.SentenceEnds(objects(a[0]), n(1), n(2), n(3)) {
			x = append(x, []any{p.Instant, p.Duration, p.Context})
		}
		return x, nil
	case "curation.validate_clip":
		ok, msgs := curation.ValidateClip(span(0), objects(a[1]), o(2))
		return []any{ok, msgs}, nil
	case "curation.approve":
		e := curation.Approve(o(0), o(1))
		return o(0), e
	case "curation.reject":
		curation.Reject(o(0), o(1), s(2))
		return o(0), nil
	case "curation.composition":
		return curation.Composition(o(0)), nil
	case "curation.missing_kinds":
		return curation.MissingKinds(o(0)), nil
	case "curation.reasons":
		return curation.Reasons(o(0)), nil
	case "curation.is_closed":
		return curation.IsClosed(o(0)), nil
	case "curation.to_moments":
		return curation.ToMoments(o(0))
	case "schedule.load":
		return schedule.Load(s(0))
	case "schedule.pending":
		opt := schedule.PendingOptions{}
		if v := get(1, "day", nil); v != nil {
			opt.Day, _ = time.Parse("2006-01-02", str(v))
		}
		opt.Only = strs(get(2, "only", nil))
		opt.Platforms = strs(get(3, "platforms", nil))
		pairs, e := schedule.Pending(s(0), opt)
		x := []any{}
		for _, p := range pairs {
			x = append(x, []any{p.Item, p.Platform})
		}
		return x, e
	case "published.load":
		return schedule.LoadPublished(s(0))
	case "published.record":
		loc, _ := time.LoadLocation("America/Sao_Paulo")
		return schedule.RecordAt(s(0), s(1), s(2), s(3), s(4), time.Date(2026, 11, 18, 12, 34, 56, 0, loc))
	case "published.is_published":
		return schedule.IsPublished(o(0), s(1), s(2)), nil
	case "hashtags.slug":
		return texts.Slug(s(0)), nil
	case "hashtags.build":
		return texts.Hashtags(str(get(0, "city", "")), str(get(1, "company", "")), str(get(2, "fallback_topic", ""))), nil
	case "hashtags.format_line":
		return texts.FormatLine(str(get(0, "city", "")), str(get(1, "company", "")), str(get(2, "fallback_topic", ""))), nil
	case "texts.load":
		return texts.Load(s(0))
	case "texts.save":
		return texts.Save(s(0), o(1))
	case "texts.thumb_args":
		return texts.ThumbArgs(s(0))
	case "texts.build_kwargs":
		return texts.BuildKwargs(s(0))
	case "caption.compose":
		return caption.Compose(get(0, "description", nil), get(1, "hashtags", nil), get(2, "episode_url", nil)), nil
	case "caption.compose_episode":
		return caption.ComposeEpisode(a[0], a[1], a[2]), nil
	case "caption.validate":
		return nil, caption.Validate(s(0), a[1], s(2), out)
	case "caption.write":
		return caption.Write(s(0), s(1))
	case "brief.readable_transcript":
		return brief.ReadableTranscript(s(0))
	case "brief.readable_metadata":
		return brief.ReadableMetadata(s(0))
	case "brief.fill_template":
		return brief.FillTemplate(s(0), str(get(1, "transcript", "")), str(get(2, "metadata", "")), str(get(3, "curation", "")), str(get(4, "clips", ""))), nil
	case "brief.readable_curation":
		return brief.ReadableCuration(o(0)), nil
	case "brief.build_posts":
		return brief.BuildPosts(s(0), objects(a[1]))
	case "brief.clip_speech":
		return brief.ClipSpeech(s(0), o(1))
	case "environment.load":
		return dotenv.Load(str(get(0, "path", "")))
	case "post_instagram.file_slug":
		return posts.FileSlug(s(0))
	case "post_instagram.load":
		return posts.Load(s(0))
	}
	return nil, fmt.Errorf("unimplemented replay op %s", op)
}
