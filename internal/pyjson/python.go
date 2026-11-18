package pyjson

import (
	"fmt"
	"math"
	"math/big"
	"strconv"
	"strings"

	"github.com/fernandoduro/talaria/internal/pycompat"
)

// The helpers below give decoded JSON values the Python semantics Talaria's
// code relies on: str(), truthiness, ==, float() and type(v).__name__.

// Str is Python's str(v) for a decoded value: a string is itself, anything
// else is its repr (None, True, 2.5, ['a']). f"{value}" produces the same.
func Str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	if vr, ok := v.(Valuer); ok {
		return Str(vr.PyJSON())
	}
	return Repr(v)
}

// Truthy is Python's bool(v): None, False, 0, 0.0, "", [] and {} are false.
func Truthy(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case int:
		return x != 0
	case int64:
		return x != 0
	case *big.Int:
		return x.Sign() != 0
	case float64:
		return x != 0
	case string:
		return x != ""
	case []any:
		return len(x) > 0
	case []string:
		return len(x) > 0
	case []*Object:
		return len(x) > 0
	case *Object:
		return x.Len() > 0
	case Valuer:
		return Truthy(x.PyJSON())
	}
	return true
}

// TypeName is type(v).__name__ for a decoded value.
func TypeName(v any) string {
	switch v.(type) {
	case nil:
		return "NoneType"
	case bool:
		return "bool"
	case int, int64, *big.Int:
		return "int"
	case float64:
		return "float"
	case string:
		return "str"
	case []any, []string, []*Object:
		return "list"
	}
	return "dict"
}

// number returns v as an exact rational when it is a Python number (bool,
// int or float); Python compares numbers of different types by value.
func number(v any) (*big.Rat, bool) {
	switch x := v.(type) {
	case bool:
		if x {
			return big.NewRat(1, 1), true
		}
		return new(big.Rat), true
	case int:
		return new(big.Rat).SetInt64(int64(x)), true
	case int64:
		return new(big.Rat).SetInt64(x), true
	case *big.Int:
		return new(big.Rat).SetInt(x), true
	case float64:
		if math.IsNaN(x) || math.IsInf(x, 0) {
			return nil, false
		}
		return new(big.Rat).SetFloat64(x), true
	}
	return nil, false
}

// Equal is Python's a == b for decoded values: numbers compare by value
// across bool, int and float (True == 1 == 1.0), lists element by element,
// dicts by key set and values regardless of order.
func Equal(a, b any) bool {
	if va, ok := a.(Valuer); ok {
		a = va.PyJSON()
	}
	if vb, ok := b.(Valuer); ok {
		b = vb.PyJSON()
	}
	if fa, ok := a.(float64); ok && math.IsInf(fa, 0) {
		fb, ok := b.(float64)
		return ok && fa == fb
	}
	if ra, ok := number(a); ok {
		rb, ok := number(b)
		return ok && ra.Cmp(rb) == 0
	}
	switch x := a.(type) {
	case nil:
		return b == nil
	case string:
		y, ok := b.(string)
		return ok && x == y
	case *Object:
		y, ok := b.(*Object)
		if !ok || x.Len() != y.Len() {
			return false
		}
		for k, v := range x.All() {
			w, ok := y.Get(k)
			if !ok || !Equal(v, w) {
				return false
			}
		}
		return true
	}
	la, ok := list(a)
	if !ok {
		return false
	}
	lb, ok := list(b)
	if !ok || len(la) != len(lb) {
		return false
	}
	for i := range la {
		if !Equal(la[i], lb[i]) {
			return false
		}
	}
	return true
}

func list(v any) ([]any, bool) {
	switch x := v.(type) {
	case []any:
		return x, true
	case []string:
		out := make([]any, len(x))
		for i, s := range x {
			out[i] = s
		}
		return out, true
	case []*Object:
		out := make([]any, len(x))
		for i, o := range x {
			out[i] = o
		}
		return out, true
	}
	return nil, false
}

// Float is Python's float(v): numbers convert, a string is parsed with
// Python's float() grammar (surrounding whitespace, "_" between digits,
// inf/nan spellings), anything else is a TypeError. The errors wrap
// pycompat.ErrType and pycompat.ErrValue. Non-ASCII digits, which Python
// accepts in a string, are a ValueError here.
func Float(v any) (float64, error) {
	switch x := v.(type) {
	case bool:
		if x {
			return 1, nil
		}
		return 0, nil
	case int:
		return float64(x), nil
	case int64:
		return float64(x), nil
	case *big.Int:
		f, acc := new(big.Float).SetInt(x).Float64()
		if math.IsInf(f, 0) && acc != big.Exact {
			return 0, fmt.Errorf("%w: int too large to convert to float", pycompat.ErrOverflow)
		}
		return f, nil
	case float64:
		return x, nil
	case string:
		return parseFloat(x)
	}
	return 0, fmt.Errorf("%w: float() argument must be a string or a real number, not '%s'",
		pycompat.ErrType, TypeName(v))
}

func parseFloat(s string) (float64, error) {
	invalid := fmt.Errorf("%w: could not convert string to float: %s", pycompat.ErrValue, pycompat.StrRepr(s))
	t := pycompat.Strip(s)
	body := t
	sign := 1.0
	if body != "" && (body[0] == '+' || body[0] == '-') {
		if body[0] == '-' {
			sign = -1
		}
		body = body[1:]
	}
	switch strings.ToLower(body) {
	case "inf", "infinity":
		return math.Inf(int(sign)), nil
	case "nan":
		return math.NaN(), nil
	}
	if !validFloatLiteral(body) {
		return 0, invalid
	}
	f, err := strconv.ParseFloat(strings.ReplaceAll(body, "_", ""), 64)
	if err != nil {
		// ParseFloat reports overflow as an error with ±Inf; Python returns inf.
		if ne, ok := err.(*strconv.NumError); ok && ne.Err == strconv.ErrRange {
			return sign * f, nil
		}
		return 0, invalid
	}
	return sign * f, nil
}

// validFloatLiteral checks Python's float() grammar after the sign:
// digitpart ["." [digitpart]] | "." digitpart, then an optional exponent,
// where digitpart is digits with single "_" between them.
func validFloatLiteral(s string) bool {
	i := 0
	digitpart := func() bool {
		start := i
		for i < len(s) {
			c := s[i]
			if c >= '0' && c <= '9' {
				i++
				continue
			}
			if c == '_' && i > start && i+1 < len(s) && s[i+1] >= '0' && s[i+1] <= '9' && s[i-1] != '_' {
				i++
				continue
			}
			break
		}
		return i > start
	}
	intPart := digitpart()
	frac := false
	if i < len(s) && s[i] == '.' {
		i++
		frac = digitpart()
	}
	if !intPart && !frac {
		return false
	}
	if i < len(s) && (s[i] == 'e' || s[i] == 'E') {
		i++
		if i < len(s) && (s[i] == '+' || s[i] == '-') {
			i++
		}
		if !digitpart() {
			return false
		}
	}
	return i == len(s)
}
