package pycompat

import (
	"math"
	"math/big"
	"strconv"
	"strings"
)

// FloatRepr returns Python's str(x) / repr(x) for a float.
//
// Python prints the shortest digit string that round-trips (as Go does), but
// always marks a float as a float: 12.0 where Go's FormatFloat prints 12. It
// switches to exponent notation when the decimal exponent is below -4 or at
// least 16 (1e-05, 1e+16), keeping at least two exponent digits.
func FloatRepr(x float64) string {
	switch {
	case math.IsNaN(x):
		return "nan"
	case math.IsInf(x, 1):
		return "inf"
	case math.IsInf(x, -1):
		return "-inf"
	}
	e := strconv.FormatFloat(x, 'e', -1, 64) // e.g. "1.2345e+16", "5e-324"
	mant, exp, _ := strings.Cut(e, "e")
	n, _ := strconv.Atoi(exp)
	// CPython's float_repr_style 'short': exponent form when decpt <= -4 or
	// decpt > 16, where decpt = exponent + 1 (digits are 0.d1d2... x 10^decpt).
	if decpt := n + 1; decpt <= -4 || decpt > 16 {
		return mant + "e" + exp
	}
	f := strconv.FormatFloat(x, 'f', -1, 64)
	if !strings.ContainsRune(f, '.') {
		f += ".0"
	}
	return f
}

// CPython's float_round bounds (Objects/floatobject.c): beyond NDIGITS_MAX
// the value is returned unchanged, below NDIGITS_MIN it rounds to a signed 0.
const (
	ndigitsMax = 323  // (DBL_MANT_DIG - DBL_MIN_EXP) * 0.30103
	ndigitsMin = -308 // -(DBL_MAX_EXP + 1) * 0.30103
)

// Round returns Python's round(x, n) for a float x.
//
// Python rounds the exact binary value of x to n decimal places, ties to
// even, then converts back to the nearest double. That is why
// round(2.675, 2) == 2.67: the double nearest 2.675 is slightly below it.
// Never use math.Round, which rounds ties away from zero.
//
// Where CPython raises OverflowError (a rounded value too large for a
// double, only reachable with negative n near the float maximum), Round
// returns the infinity of the same sign.
func Round(x float64, n int) float64 {
	if math.IsNaN(x) || math.IsInf(x, 0) || x == 0 {
		return x
	}
	if n > ndigitsMax {
		return x
	}
	if n < ndigitsMin {
		return math.Copysign(0, x)
	}
	scale := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(abs(n))), nil)
	r := new(big.Rat).SetFloat64(x)
	if n >= 0 {
		r.Mul(r, new(big.Rat).SetInt(scale))
	} else {
		r.Quo(r, new(big.Rat).SetInt(scale))
	}
	q := roundRatHalfEven(r)
	res := new(big.Rat).SetInt(q)
	if n >= 0 {
		res.Quo(res, new(big.Rat).SetInt(scale))
	} else {
		res.Mul(res, new(big.Rat).SetInt(scale))
	}
	f, _ := res.Float64()
	if f == 0 {
		return math.Copysign(0, x) // round(-0.001, 2) == -0.0
	}
	return f
}

// roundRatHalfEven rounds r to the nearest integer, ties to even.
func roundRatHalfEven(r *big.Rat) *big.Int {
	num, den := r.Num(), r.Denom()
	q, rem := new(big.Int).QuoRem(num, den, new(big.Int)) // truncates toward zero
	if rem.Sign() == 0 {
		return q
	}
	twice := new(big.Int).Abs(rem)
	twice.Lsh(twice, 1)
	switch c := twice.Cmp(den); {
	case c > 0, c == 0 && q.Bit(0) == 1:
		if num.Sign() < 0 {
			q.Sub(q, big.NewInt(1))
		} else {
			q.Add(q, big.NewInt(1))
		}
	}
	return q
}

// RoundHalfEven is Python's round(x) with no ndigits, as a float: ties go to
// the even integer (round(0.5) == 0, round(1.5) == 2, round(2.5) == 2).
func RoundHalfEven(x float64) float64 { return math.RoundToEven(x) }

// RoundInt is Python's int(round(x)). x must be finite: CPython raises on
// NaN and infinities, and so must the caller before reaching here.
func RoundInt(x float64) int { return int(math.RoundToEven(x)) }

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}
