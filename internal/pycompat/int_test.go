package pycompat

import (
	"errors"
	"math/big"
	"strconv"
	"strings"
	"testing"

	"github.com/fernandoduro/talaria/internal/golden"
)

// intDivergences are the inputs where PyInt deliberately differs from
// CPython's int(): Python's answer is in the golden, ours is an error.
var intDivergences = map[string]error{
	`str:2_0`:                    ErrValue,    // Python: 20 (underscore separators)
	"str:\u0663":                 ErrValue,    // Python: 3 (ARABIC-INDIC DIGIT THREE)
	`int:1180591620717411303424`: ErrOverflow, // Python: unbounded ints
	`float:4415af1d78b58c40`:     ErrOverflow, // int(1e20): beyond int64
	`str:9223372036854775808`:    ErrOverflow, // MaxInt64 + 1
}

func TestPyIntMatchesPythonGolden(t *testing.T) {
	var rows [][2][]any // [typed input, [outcome, value-or-message]]
	golden.ReadJSON(t, "pycompat/int.json", &rows)
	seen := 0
	for _, r := range rows {
		in, key := typedInput(t, r[0])
		outcome, detail := r[1][0].(string), r[1][1].(string)
		got, err := PyInt(in)

		if wantErr, ok := intDivergences[key]; ok {
			seen++
			if !errors.Is(err, wantErr) {
				t.Errorf("PyInt(%s): got (%d, %v), want deliberate %v (Python: %s %s)", key, got, err, wantErr, outcome, detail)
			}
			continue
		}
		switch outcome {
		case "ok":
			want, _ := strconv.ParseInt(detail, 10, 64)
			if err != nil || got != want {
				t.Errorf("PyInt(%s) = (%d, %v), Python = %s", key, got, err, detail)
			}
		default:
			if err == nil {
				t.Errorf("PyInt(%s) = %d, Python raised %s: %s", key, got, outcome, detail)
				continue
			}
			if !strings.HasPrefix(err.Error(), outcome+": ") {
				t.Errorf("PyInt(%s) error %q, Python raised %s", key, err, outcome)
			}
			if msg := strings.TrimPrefix(err.Error(), outcome+": "); msg != detail {
				t.Errorf("PyInt(%s) message %q, Python %q", key, msg, detail)
			}
		}
	}
	if seen != len(intDivergences) {
		t.Errorf("golden exercised %d of %d documented divergences", seen, len(intDivergences))
	}
}

// typedInput rebuilds the Python value dump.py tagged, in the Go types
// pyjson decodes to.
func typedInput(t *testing.T, tag []any) (any, string) {
	t.Helper()
	kind := tag[0].(string)
	switch kind {
	case "none":
		return nil, "none"
	case "bool":
		return tag[1].(bool), "bool:" + strconv.FormatBool(tag[1].(bool))
	case "int":
		s := tag[1].(string)
		if n, err := strconv.ParseInt(s, 10, 64); err == nil {
			return n, "int:" + s
		}
		b, _ := new(big.Int).SetString(s, 10)
		return b, "int:" + s
	case "float":
		return fromBits(t, tag[1].(string)), "float:" + tag[1].(string)
	case "str":
		return tag[1].(string), "str:" + tag[1].(string)
	case "list":
		return []any{}, "list"
	case "dict":
		return map[string]any{}, "dict" // stands in for *pyjson.Object
	}
	t.Fatalf("unknown tag %v", tag)
	return nil, ""
}

func TestPyIntTable(t *testing.T) {
	cases := []struct {
		in   any
		want int64
		err  error
	}{
		{2.7, 2, nil}, // episode.load: int(2.7) == 2, truncation not rounding
		{-2.7, -2, nil},
		{"2", 2, nil},
		{true, 1, nil},
		{false, 0, nil},
		{int64(5), 5, nil},
		{5, 5, nil},
		{"2.0", 0, ErrValue},
		{"", 0, ErrValue},
		{nil, 0, ErrType},
		{[]any{1}, 0, ErrType},
		{"2_0", 0, ErrValue}, // plan: Python's 20 is a quirk not worth copying
	}
	for _, c := range cases {
		got, err := PyInt(c.in)
		if c.err != nil {
			if !errors.Is(err, c.err) {
				t.Errorf("PyInt(%#v) error = %v, want %v", c.in, err, c.err)
			}
			continue
		}
		if err != nil || got != c.want {
			t.Errorf("PyInt(%#v) = (%d, %v), want %d", c.in, got, err, c.want)
		}
	}
}
