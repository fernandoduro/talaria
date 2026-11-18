//go:build pyoracle

package posts

import (
	"github.com/fernandoduro/talaria/internal/pyoracle"
	"testing"
	"unicode/utf8"
)

func FuzzFileSlug(f *testing.F) {
	for _, s := range []string{"../outside/clip", "..", "  Ribeirão-Açaí.v2  ", "e\u0301mark", "²_٣", "--post--", "\x1c x \x1f", "a\u203fb"} {
		f.Add(s)
	}
	oracle := pyoracle.Start(f)
	f.Fuzz(func(t *testing.T, s string) {
		if !utf8.ValidString(s) || len(s) > 4096 {
			t.Skip()
		}
		want, we, e := oracle.Query("file_slug", s, nil)
		if e != nil {
			t.Fatal(e)
		}
		got, ge := FileSlug(s)
		err := ""
		if ge != nil {
			err = ge.Error()
		}
		if got != want || err != we {
			t.Fatalf("input=%q\nGo=(%q,%q)\nPython=(%q,%q)", s, got, err, want, we)
		}
	})
}
