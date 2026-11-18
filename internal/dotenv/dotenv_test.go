package dotenv

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDefaultRootAndEmptyShellWins(t *testing.T) {
	pd := t.TempDir()
	t.Setenv("TALARIA_ROOT", pd)
	t.Setenv("G1_DOTENV_SET", "")
	key := "G1_DOTENV_NEW"
	os.Unsetenv(key)
	t.Cleanup(func() { os.Unsetenv(key) })
	p := filepath.Join(pd, ".env")
	os.WriteFile(p, []byte("G1_DOTENV_SET=file\r\nG1_DOTENV_NEW='"+strings.Repeat("x", 70000)+"'\r"), 0644)
	n, e := Load("")
	if e != nil || n != 1 {
		t.Fatalf("%d %v", n, e)
	}
	if os.Getenv("G1_DOTENV_SET") != "" || len(os.Getenv(key)) != 70000 {
		t.Fatal("shell/long-line semantics differ")
	}
}
func TestParserDoesNotInterpolateOrStripInsideQuotes(t *testing.T) {
	for _, c := range []struct{ in, want string }{{` " x " `, " x "}, {`"${TOKEN}"`, "${TOKEN}"}, {`'"abc"'`, `"abc"`}, {`"unmatched`, `"unmatched`}, {"\x1cabc\x1f", "abc"}} {
		if got := cleanValue(c.in); got != c.want {
			t.Errorf("cleanValue(%q)=%q", c.in, got)
		}
	}
}
func TestLoadReadErrors(t *testing.T) {
	p := filepath.Join(t.TempDir(), "bad.env")
	os.WriteFile(p, []byte{0xff}, 0644)
	if _, e := Load(p); e == nil {
		t.Fatal("invalid UTF-8 accepted")
	}
	if _, e := Load(filepath.Dir(p)); e == nil {
		t.Fatal("directory accepted")
	}
}
