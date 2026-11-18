package pyjson

import (
	"fmt"
	"math/big"
	"strconv"
	"strings"

	"github.com/fernandoduro/talaria/internal/pycompat"
)

// Repr is Python's repr() of a value json.load produced, for error messages
// written as f"... got {value!r}": None, True, 2.5, 'text', ['a', 1],
// {'k': 'v'}.
func Repr(v any) string {
	var b strings.Builder
	writeRepr(&b, v)
	return b.String()
}

func writeRepr(b *strings.Builder, v any) {
	switch x := v.(type) {
	case nil:
		b.WriteString("None")
	case bool:
		if x {
			b.WriteString("True")
		} else {
			b.WriteString("False")
		}
	case int:
		b.WriteString(strconv.Itoa(x))
	case int64:
		b.WriteString(strconv.FormatInt(x, 10))
	case *big.Int:
		b.WriteString(x.String())
	case float64:
		b.WriteString(pycompat.FloatRepr(x))
	case string:
		b.WriteString(pycompat.StrRepr(x))
	case []any:
		writeSeq(b, len(x), func(i int) any { return x[i] })
	case []string:
		writeSeq(b, len(x), func(i int) any { return x[i] })
	case []*Object:
		writeSeq(b, len(x), func(i int) any { return x[i] })
	case *Object:
		b.WriteByte('{')
		i := 0
		for k, val := range x.All() {
			if i > 0 {
				b.WriteString(", ")
			}
			i++
			b.WriteString(pycompat.StrRepr(k))
			b.WriteString(": ")
			writeRepr(b, val)
		}
		b.WriteByte('}')
	case Valuer:
		writeRepr(b, x.PyJSON())
	default:
		fmt.Fprintf(b, "<%T>", v)
	}
}

func writeSeq(b *strings.Builder, n int, at func(int) any) {
	b.WriteByte('[')
	for i := range n {
		if i > 0 {
			b.WriteString(", ")
		}
		writeRepr(b, at(i))
	}
	b.WriteByte(']')
}
