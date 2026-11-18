package pyjson

import (
	"errors"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"math"
	"testing"
)

func TestPythonValues(t *testing.T) {
	for _, c := range []struct {
		v        any
		truth    bool
		typ, str string
	}{{nil, false, "NoneType", "None"}, {false, false, "bool", "False"}, {true, true, "bool", "True"}, {int64(0), false, "int", "0"}, {2.0, true, "float", "2.0"}, {"", false, "str", ""}, {[]any{}, false, "list", "[]"}, {NewObject(), false, "dict", "{}"}} {
		if Truthy(c.v) != c.truth || TypeName(c.v) != c.typ || Str(c.v) != c.str {
			t.Errorf("Python semantics for %#v", c.v)
		}
	}
	for _, p := range [][2]any{{true, 1.0}, {false, int64(0)}, {[]any{true}, []any{int64(1)}}, {NewObject("b", 2, "a", 1), NewObject("a", 1.0, "b", int64(2))}} {
		if !Equal(p[0], p[1]) {
			t.Errorf("Equal(%v,%v)=false", p[0], p[1])
		}
	}
	if Equal(math.NaN(), math.NaN()) || Equal(1, "1") || Equal(NewObject(), []any{}) {
		t.Error("unequal values compare equal")
	}
}
func TestFloatCoercion(t *testing.T) {
	for _, c := range []struct {
		v    any
		want float64
	}{{true, 1}, {int64(2), 2}, {"1_000.5", 1000.5}, {" -2e-2\n", -.02}, {".5", .5}, {"1.", 1}, {"Infinity", math.Inf(1)}} {
		f, e := Float(c.v)
		if e != nil || f != c.want {
			t.Errorf("Float(%v)=%v,%v", c.v, f, e)
		}
	}
	for _, s := range []string{"", " ", "1__0", "1_", "_1", "0x1", "1e", "1e_2", "١"} {
		if _, e := Float(s); !errors.Is(e, pycompat.ErrValue) {
			t.Errorf("Float(%q) error=%v", s, e)
		}
	}
	if _, e := Float(nil); !errors.Is(e, pycompat.ErrType) {
		t.Error(e)
	}
}
