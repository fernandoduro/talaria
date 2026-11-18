package pycompat

import (
	"errors"
	"fmt"
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode"
)

// The Python exception classes PyInt can raise. Callers match them with
// errors.Is; episode.load, for instance, catches TypeError and ValueError but
// lets OverflowError escape.
var (
	ErrType     = errors.New("TypeError")
	ErrValue    = errors.New("ValueError")
	ErrOverflow = errors.New("OverflowError")
)

// PyInt is Python's int(v) applied to a value decoded from JSON (nil, bool,
// int, int64, *big.Int, float64 or string):
//
//	int(2.7) == 2, int(-2.7) == -2   (truncates toward zero)
//	int("2") == 2, int(" -3\n") == -3 (surrounding whitespace allowed)
//	int(True) == 1, int(False) == 0
//	int(None), int([..]), int({..})  -> TypeError
//	int("2.0"), int("")              -> ValueError
//	int(float("inf"))                -> OverflowError; NaN -> ValueError
//
// Deliberate divergences, all on inputs no operator types on purpose:
// "2_0" (Python reads 20) and non-ASCII digits such as "٣" (Python reads 3)
// are ValueError here, and values outside int64 are OverflowError where
// Python would return a big integer.
func PyInt(v any) (int64, error) {
	switch x := v.(type) {
	case bool:
		if x {
			return 1, nil
		}
		return 0, nil
	case int:
		return int64(x), nil
	case int64:
		return x, nil
	case *big.Int:
		if !x.IsInt64() {
			return 0, fmt.Errorf("%w: int too large for int64: %s", ErrOverflow, x.String())
		}
		return x.Int64(), nil
	case float64:
		switch {
		case math.IsNaN(x):
			return 0, fmt.Errorf("%w: cannot convert float NaN to integer", ErrValue)
		case math.IsInf(x, 0):
			return 0, fmt.Errorf("%w: cannot convert float infinity to integer", ErrOverflow)
		}
		t := math.Trunc(x)
		if t < math.MinInt64 || t >= math.MaxInt64 {
			return 0, fmt.Errorf("%w: int too large for int64: %s", ErrOverflow, FloatRepr(x))
		}
		return int64(t), nil
	case string:
		return parseIntLiteral(x)
	case nil:
		return 0, fmt.Errorf("%w: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'", ErrType)
	default:
		return 0, fmt.Errorf("%w: int() argument must be a string, a bytes-like object or a real number, not '%s'", ErrType, pyTypeName(v))
	}
}

func parseIntLiteral(s string) (int64, error) {
	invalid := fmt.Errorf("%w: invalid literal for int() with base 10: %s", ErrValue, StrRepr(s))
	t := strings.TrimFunc(s, isIntSpace)
	body := strings.TrimLeft(t, "+-")
	if len(t)-len(body) > 1 || body == "" {
		return 0, invalid
	}
	for _, c := range body {
		if c < '0' || c > '9' {
			return 0, invalid
		}
	}
	n, err := strconv.ParseInt(t, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%w: int too large for int64: %s", ErrOverflow, StrRepr(s))
	}
	return n, nil
}

// isIntSpace is the whitespace int() strips: CPython maps non-ASCII
// whitespace to a plain space, then skips only the ASCII " \t\n\v\f\r", so
// "\u00a02\u2003" parses but "\x1c7" does not, although "\x1c".isspace().
func isIntSpace(r rune) bool {
	if r < 0x80 {
		return strings.ContainsRune(" \t\n\v\f\r", r)
	}
	return unicode.IsSpace(r)
}

// pyTypeName names v's Python type for TypeError messages, assuming v came
// out of a JSON decoder: arrays are lists and objects are dicts.
func pyTypeName(v any) string {
	switch v.(type) {
	case []any, []string:
		return "list"
	default:
		return "dict"
	}
}
