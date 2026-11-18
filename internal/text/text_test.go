package text

import (
	"strings"
	"testing"
)

// Regression from differential fuzz: repeated information separators previously
// caused quadratic failed searches and hit the regexp2 match timeout.
func TestWhitespaceRunsStayLinear(t *testing.T) {
	for _, tail := range []string{"0", "uh, next", "."} {
		s := "0赥" + strings.Repeat("\x1d", 4000) + tail
		got, e := CleanCaption(s)
		want := "0赥 " + tail
		if tail == "uh, next" {
			want = "0赥 next"
		}
		if tail == "." {
			want = "0赥."
		}
		if e != nil || got != want {
			t.Fatalf("tail %q: got %q, %v; want %q", tail, got, e, want)
		}
	}
}
func TestLiteralControlRuneDoesNotPanic(t *testing.T) {
	got, e := FixProperNouns("0", []string{"ո\u0605A0"})
	if e != nil || got != "0" {
		t.Fatalf("%q %v", got, e)
	}
}
func TestReplacementTemplate(t *testing.T) {
	for _, c := range []struct{ in, want string }{{`a\nb`, "a\nb"}, {`a\g<0>b`, "aMATCHb"}, {`\101`, "A"}, {`\000`, "\x00"}, {`\&`, `\&`}, {`\\`, `\`}} {
		p, e := parseReplacement(c.in)
		if e != nil || p.expand("MATCH") != c.want {
			t.Errorf("%q => %q, %v", c.in, p.expand("MATCH"), e)
		}
	}
	for _, s := range []string{`X\g<`, `X\g<>`, `X\g<foo>`, `X\g<-1>`, `X\8`, `X\q`, `X\777`, `X\`} {
		if _, e := parseReplacement(s); e == nil {
			t.Errorf("invalid template %q accepted", s)
		}
	}
}
