//go:build pyoracle

package text

import (
	"github.com/fernandoduro/talaria/internal/pyoracle"
	"testing"
	"unicode/utf8"
)

func FuzzCleanCaption(f *testing.F) {
	for _, s := range []string{"we we shipped", "a a a", "Uh, Gonna ship it, you know.", "like, tools, like Slack, work", "ſ ſ", "\u0130 i", "e\u0301 e\u0301", "\x1c uh, gonna\u00a0go", "² ²", "i ı", "σ ς"} {
		f.Add(s)
	}
	oracle := pyoracle.Start(f)
	f.Fuzz(func(t *testing.T, s string) {
		if !utf8.ValidString(s) || len(s) > 4096 {
			t.Skip()
		}
		want, we, e := oracle.Query("clean_caption", s, nil)
		if e != nil {
			t.Fatal(e)
		}
		got, ge := CleanCaption(s)
		err := ""
		if ge != nil {
			err = ge.Error()
		}
		if got != want || err != we {
			t.Fatalf("input=%q\nGo=(%q,%q)\nPython=(%q,%q)", s, got, err, want, we)
		}
	})
}
func FuzzFixProperNouns(f *testing.F) {
	for _, p := range [][2]string{{"Cestril Kestryl Keztril", "Kestril"}, {"zarvic", "Zarvik"}, {"a shell company", "Shell"}, {"ribeirãoaçaí", "RibeirãoAçaí"}, {"İKEA ıkea", "Ikea"}, {"e\u0301mark", "E\u0301mark"}, {"fiŉŉ", "Finn"}, {"a\\name", "A\\name"}, {"x\\g<0>", "X\\g<0>"}} {
		f.Add(p[0], p[1])
	}
	oracle := pyoracle.Start(f)
	f.Fuzz(func(t *testing.T, s, name string) {
		if !utf8.ValidString(s) || !utf8.ValidString(name) || len(s) > 4096 || len(name) > 512 {
			t.Skip()
		}
		want, we, e := oracle.Query("fix_proper_nouns", s, []string{name})
		if e != nil {
			t.Fatal(e)
		}
		got, ge := FixProperNouns(s, []string{name})
		err := ""
		if ge != nil {
			err = ge.Error()
		}
		if got != want || err != we {
			t.Fatalf("input=%q name=%q\nGo=(%q,%q)\nPython=(%q,%q)", s, name, got, err, want, we)
		}
	})
}
