package text

import (
	"fmt"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"strconv"
	"strings"
	"unicode"
)

// replacement is CPython re._parser.parse_template for a pattern without
// capture groups (the recasing branch of fix_proper_nouns). A nil part is
// group 0; string parts are literals. In particular, \n is interpreted here
// but is literal in the phonetic callback branch.
type replacement []any

func (p replacement) expand(match string) string {
	var b strings.Builder
	for _, v := range p {
		if v == nil {
			b.WriteString(match)
		} else {
			b.WriteString(v.(string))
		}
	}
	return b.String()
}

type templateTokens struct {
	source []rune
	index  int
	next   string
	err    error
}

func (t *templateTokens) advance() {
	i := t.index
	if i >= len(t.source) {
		t.next = ""
		return
	}
	c := string(t.source[i])
	i++
	if c == `\` {
		if i >= len(t.source) {
			t.err = t.errorAt("bad escape (end of pattern)", len(t.source)-1)
			t.next = ""
			return
		}
		c += string(t.source[i])
		i++
	}
	t.index = i
	t.next = c
}
func (t *templateTokens) get() string { s := t.next; t.advance(); return s }
func (t *templateTokens) pos() int    { return t.index - len([]rune(t.next)) }
func (t *templateTokens) errorAt(msg string, pos int) error {
	out := fmt.Sprintf("%s at position %d", msg, pos)
	all := string(t.source)
	if strings.Contains(all, "\n") {
		prefix := string(t.source[:max(0, min(len(t.source), pos))])
		line := strings.Count(prefix, "\n") + 1
		col := pos
		for i := len([]rune(prefix)) - 1; i >= 0; i-- {
			if t.source[i] == '\n' {
				col = pos - i - 1
				break
			}
		}
		out += fmt.Sprintf(" (line %d, column %d)", line, col+1)
	}
	return fmt.Errorf("%s", out)
}
func (t *templateTokens) error(msg string, offset int) error { return t.errorAt(msg, t.pos()-offset) }
func parseReplacement(s string) (replacement, error) {
	t := templateTokens{source: []rune(s)}
	t.advance()
	out := replacement{}
	digit := func(c string) bool { return len(c) == 1 && c[0] >= '0' && c[0] <= '9' }
	oct := func(c string) bool { return len(c) == 1 && c[0] >= '0' && c[0] <= '7' }
	esc := map[string]string{`\a`: "\a", `\b`: "\b", `\f`: "\f", `\n`: "\n", `\r`: "\r", `\t`: "\t", `\v`: "\v", `\\`: `\`}
	for t.next != "" && t.err == nil {
		this := t.get()
		if t.err != nil {
			return nil, t.err
		}
		if !strings.HasPrefix(this, `\`) {
			out = append(out, this)
			continue
		}
		c := this[1:]
		switch {
		case c == "g":
			if t.next != "<" {
				return nil, t.error("missing <", 0)
			}
			t.get()
			if t.err != nil {
				return nil, t.err
			}
			name := ""
			for {
				ch := t.get()
				if t.err != nil {
					return nil, t.err
				}
				if ch == "" {
					if name == "" {
						return nil, t.error("missing group name", 0)
					}
					return nil, t.error("missing >, unterminated name", len([]rune(name)))
				}
				if ch == ">" {
					if name == "" {
						return nil, t.error("missing group name", 1)
					}
					break
				}
				name += ch
			}
			asciiDigits := true
			for _, r := range name {
				if r < '0' || r > '9' {
					asciiDigits = false
				}
			}
			if asciiDigits {
				n, e := strconv.ParseUint(name, 10, 64)
				if e != nil || n > 0 {
					return nil, t.error("invalid group reference "+strings.TrimLeft(name, "0"), len([]rune(name))+1)
				}
				out = append(out, nil)
			} else {
				valid := true
				for i, r := range name {
					if i == 0 {
						valid = r == '_' || unicode.IsLetter(r) || unicode.Is(unicode.Nl, r)
					} else {
						valid = valid && (r == '_' || unicode.IsLetter(r) || unicode.IsDigit(r) || unicode.In(r, unicode.Mn, unicode.Mc, unicode.Pc, unicode.Nl))
					}
				}
				if !valid {
					return nil, t.error("bad character in group name "+pycompat.StrRepr(name), len([]rune(name))+1)
				}
				return nil, fmt.Errorf("unknown group name %s", pycompat.StrRepr(name))
			}
		case c == "0":
			for i := 0; i < 2 && oct(t.next); i++ {
				this += t.get()
			}
			if t.err != nil {
				return nil, t.err
			}
			n, _ := strconv.ParseInt(this[1:], 8, 32)
			out = append(out, string(rune(n&255)))
		case digit(c):
			isoctal := false
			if digit(t.next) {
				this += t.get()
				if t.err != nil {
					return nil, t.err
				}
				if oct(c) && oct(this[2:]) && oct(t.next) {
					this += t.get()
					if t.err != nil {
						return nil, t.err
					}
					isoctal = true
					n, _ := strconv.ParseInt(this[1:], 8, 32)
					if n > 255 {
						return nil, t.error("octal escape value "+this+" outside of range 0-0o377", len([]rune(this)))
					}
					out = append(out, string(rune(n)))
				}
			}
			if !isoctal {
				n, _ := strconv.Atoi(this[1:])
				return nil, t.error(fmt.Sprintf("invalid group reference %d", n), len(this)-1)
			}
		default:
			if v, ok := esc[this]; ok {
				out = append(out, v)
			} else {
				if len(c) == 1 && (c[0] >= 'a' && c[0] <= 'z' || c[0] >= 'A' && c[0] <= 'Z') {
					return nil, t.error("bad escape "+this, len([]rune(this)))
				}
				out = append(out, this)
			}
		}
	}
	if t.err != nil {
		return nil, t.err
	}
	return out, nil
}
