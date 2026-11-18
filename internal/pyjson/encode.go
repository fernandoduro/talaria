package pyjson

import (
	"bytes"
	"fmt"
	"io"
	"math"
	"math/big"
	"os"
	"strconv"
	"unicode/utf8"

	"github.com/fernandoduro/talaria/internal/pycompat"
)

// Valuer lets a Go type describe itself as a pyjson value (typically an
// *Object built in the field order Python writes).
type Valuer interface {
	PyJSON() any
}

// Marshal returns the bytes Python's json.dumps(v, ensure_ascii=False,
// indent=2) produces:
//
//   - two-space indent; items end in "," + newline (no trailing space) and
//     keys are followed by ": ";
//   - empty containers print as [] and {};
//   - floats print as Python's repr (10.0, 1e-05, 1e+16), non-finite floats
//     as NaN, Infinity and -Infinity;
//   - strings escape only " \ and the C0 controls (\b \f \n \r \t short,
//     the rest as lowercase \u00XX); U+2028, U+2029, <, > and & stay raw;
//   - no trailing newline.
//
// Accepted inputs: nil, bool, int, int64, *big.Int, float64, string, []any,
// []string, []*Object, *Object and Valuer. Anything else, and strings that
// are not valid UTF-8 (no Python str can hold them), are errors.
func Marshal(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := encode(&buf, v, 0); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// Dump writes Marshal(v) to w, like json.dump(v, f, ensure_ascii=False,
// indent=2).
func Dump(w io.Writer, v any) error {
	b, err := Marshal(v)
	if err != nil {
		return err
	}
	_, err = w.Write(b)
	return err
}

// WriteFile writes Marshal(v) to path, truncating it, as Python's
// open(path, "w") + json.dump does. Use an atomic temp-and-rename where the
// Python code does (published.json).
func WriteFile(path string, v any) error {
	b, err := Marshal(v)
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o666)
}

func newline(buf *bytes.Buffer, depth int) {
	buf.WriteByte('\n')
	for range depth {
		buf.WriteString("  ")
	}
}

func encode(buf *bytes.Buffer, v any, depth int) error {
	switch x := v.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if x {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case int:
		buf.WriteString(strconv.Itoa(x))
	case int64:
		buf.WriteString(strconv.FormatInt(x, 10))
	case *big.Int:
		buf.WriteString(x.String())
	case float64:
		buf.WriteString(floatJSON(x))
	case string:
		return encodeString(buf, x)
	case []any:
		return encodeList(buf, len(x), depth, func(i int) any { return x[i] })
	case []string:
		return encodeList(buf, len(x), depth, func(i int) any { return x[i] })
	case []*Object:
		return encodeList(buf, len(x), depth, func(i int) any { return x[i] })
	case *Object:
		if x.Len() == 0 {
			buf.WriteString("{}")
			return nil
		}
		buf.WriteByte('{')
		i := 0
		for k, val := range x.All() {
			if i > 0 {
				buf.WriteByte(',')
			}
			i++
			newline(buf, depth+1)
			if err := encodeString(buf, k); err != nil {
				return err
			}
			buf.WriteString(": ")
			if err := encode(buf, val, depth+1); err != nil {
				return err
			}
		}
		newline(buf, depth)
		buf.WriteByte('}')
	case Valuer:
		return encode(buf, x.PyJSON(), depth)
	default:
		return fmt.Errorf("pyjson: cannot encode %T", v)
	}
	return nil
}

func encodeList(buf *bytes.Buffer, n, depth int, at func(int) any) error {
	if n == 0 {
		buf.WriteString("[]")
		return nil
	}
	buf.WriteByte('[')
	for i := range n {
		if i > 0 {
			buf.WriteByte(',')
		}
		newline(buf, depth+1)
		if err := encode(buf, at(i), depth+1); err != nil {
			return err
		}
	}
	newline(buf, depth)
	buf.WriteByte(']')
	return nil
}

// floatJSON is json's floatstr with allow_nan=True.
func floatJSON(x float64) string {
	switch {
	case math.IsNaN(x):
		return "NaN"
	case math.IsInf(x, 1):
		return "Infinity"
	case math.IsInf(x, -1):
		return "-Infinity"
	}
	return pycompat.FloatRepr(x)
}

const hexDigits = "0123456789abcdef"

// encodeString is json.encoder's (c_)encode_basestring, the ensure_ascii=False
// path.
func encodeString(buf *bytes.Buffer, s string) error {
	if !utf8.ValidString(s) {
		return fmt.Errorf("pyjson: string is not valid UTF-8: %q", s)
	}
	buf.WriteByte('"')
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch c {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		default:
			if c < 0x20 {
				buf.WriteString(`\u00`)
				buf.WriteByte(hexDigits[c>>4])
				buf.WriteByte(hexDigits[c&0xf])
			} else {
				buf.WriteByte(c) // multi-byte UTF-8 passes through byte by byte
			}
		}
	}
	buf.WriteByte('"')
	return nil
}
