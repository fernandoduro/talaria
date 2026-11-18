package pycompat

import (
	"math"
	"strconv"
	"testing"

	"github.com/fernandoduro/talaria/internal/golden"
)

func fromBits(t *testing.T, hex string) float64 {
	t.Helper()
	u, err := strconv.ParseUint(hex, 16, 64)
	if err != nil {
		t.Fatalf("bad float bits %q: %v", hex, err)
	}
	return math.Float64frombits(u)
}

func TestFloatRepr(t *testing.T) {
	// Expectations are CPython 3.12's repr(); the golden test below covers
	// ~1,000 more values.
	cases := []struct {
		in   float64
		want string
	}{
		{0, "0.0"},
		{math.Copysign(0, -1), "-0.0"},
		{12, "12.0"}, // -ss str(start): Go's FormatFloat(-1) prints "12"
		{3.5, "3.5"}, // -t str(CARD_DURATION_S)
		{0.1, "0.1"}, // shortest round-trip digits
		{1.0 / 3, "0.3333333333333333"},
		{0.0001, "0.0001"}, // last fixed-notation power below 1
		{0.00001, "1e-05"}, // exponent form, two exponent digits at least
		{1.5e-7, "1.5e-07"},
		{1e15, "1000000000000000.0"},
		{9999999999999998, "9999999999999998.0"}, // 16 digits: still fixed
		{1e16, "1e+16"},                          // exponent form with explicit +
		{1.2345e22, "1.2345e+22"},
		{5e-324, "5e-324"},
		{math.MaxFloat64, "1.7976931348623157e+308"},
		{-12.5, "-12.5"},
		{math.Inf(1), "inf"},
		{math.Inf(-1), "-inf"},
		{math.NaN(), "nan"},
	}
	for _, c := range cases {
		if got := FloatRepr(c.in); got != c.want {
			t.Errorf("FloatRepr(%v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestFloatReprMatchesPythonGolden(t *testing.T) {
	var rows [][3]string // bits, repr(x), json.dumps(x)
	golden.ReadJSON(t, "pycompat/float_repr.json", &rows)
	if len(rows) < 1000 {
		t.Fatalf("only %d golden rows", len(rows))
	}
	for _, r := range rows {
		x := fromBits(t, r[0])
		if got := FloatRepr(x); got != r[1] {
			t.Errorf("FloatRepr(%s) = %q, Python repr = %q", r[0], got, r[1])
		}
	}
}

func TestRound(t *testing.T) {
	cases := []struct {
		x    float64
		n    int
		want float64
	}{
		{2.675, 2, 2.67}, // the double nearest 2.675 lies below it
		{1.005, 2, 1.0},  // likewise below 1.005
		{0.125, 2, 0.12}, // exact binary tie: to even
		{0.375, 2, 0.38}, // exact binary tie: to even
		{2.5, 0, 2.0},    // ties to even, not away from zero
		{3.5, 0, 4.0},    //
		{-2.5, 0, -2.0},  //
		{1234.5678, 3, 1234.568},
		{3725.3333333, 3, 3725.333},
		{1250, -2, 1200}, // negative ndigits: tie to even hundred
		{1350, -2, 1400}, //
		{0.1 + 0.2, 1, 0.3},
		{7, 3, 7},
		{1e300, 400, 1e300}, // beyond NDIGITS_MAX: unchanged
	}
	for _, c := range cases {
		if got := Round(c.x, c.n); got != c.want {
			t.Errorf("Round(%v, %d) = %v, want %v", c.x, c.n, got, c.want)
		}
	}
	// Signs of zero survive, as in CPython: round(-0.001, 2) == -0.0.
	for _, c := range []struct {
		x float64
		n int
	}{{-0.001, 2}, {-0.4, 0}, {math.Copysign(0, -1), 3}, {-5, -400}} {
		if got := Round(c.x, c.n); got != 0 || !math.Signbit(got) {
			t.Errorf("Round(%v, %d) = %v, want -0.0", c.x, c.n, got)
		}
	}
	if got := Round(math.NaN(), 2); !math.IsNaN(got) {
		t.Errorf("Round(NaN) = %v", got)
	}
	if got := Round(math.Inf(-1), 2); !math.IsInf(got, -1) {
		t.Errorf("Round(-Inf) = %v", got)
	}
}

func TestRoundMatchesPythonGolden(t *testing.T) {
	var rows [][3]any // bits, n, bits of round(x, n)
	golden.ReadJSON(t, "pycompat/round.json", &rows)
	if len(rows) < 1000 {
		t.Fatalf("only %d golden rows", len(rows))
	}
	for _, r := range rows {
		x := fromBits(t, r[0].(string))
		n := int(r[1].(float64))
		want := fromBits(t, r[2].(string))
		got := Round(x, n)
		if math.Float64bits(got) != math.Float64bits(want) {
			t.Errorf("Round(%s=%v, %d) = %v, Python = %v", r[0], x, n, got, want)
		}
	}
}

func TestRoundHalfEvenAndRoundInt(t *testing.T) {
	cases := []struct {
		in   float64
		want int
	}{
		{0.5, 0}, {1.5, 2}, {2.5, 2}, {-0.5, 0}, {-1.5, -2}, {2.4999, 2}, {2.5001, 3},
		{0.8 * 255, 204}, // int(round(CAP_BOX_ALPHA * 255)) shape
	}
	for _, c := range cases {
		if got := RoundInt(c.in); got != c.want {
			t.Errorf("RoundInt(%v) = %d, want %d", c.in, got, c.want)
		}
		if got := RoundHalfEven(c.in); got != float64(c.want) {
			t.Errorf("RoundHalfEven(%v) = %v, want %d", c.in, got, c.want)
		}
	}
}
