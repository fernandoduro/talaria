package pyjson

import (
	"bytes"
	"encoding/json"
	"math"
	"math/big"
	"path"
	"slices"
	"strconv"
	"strings"
	"testing"

	"github.com/fernandoduro/talaria/internal/golden"
)

// TestReencodesPythonWrittenFilesByteForByte is the G0 done-criterion: every
// JSON file Talaria's Python code wrote into the golden set (episode
// template, curation state, moments, transcript.json from example.txt, plus
// an adversarial document) decodes and re-encodes to identical bytes.
func TestReencodesPythonWrittenFilesByteForByte(t *testing.T) {
	files := golden.Glob(t, "json/*.json")
	for _, need := range []string{"episode_template", "curation_state", "transcript_example"} {
		if !slices.Contains(files, "json/"+need+".json") {
			t.Fatalf("golden set lacks json/%s.json (have %v)", need, files)
		}
	}
	for _, rel := range files {
		t.Run(strings.TrimSuffix(path.Base(rel), ".json"), func(t *testing.T) {
			want := golden.Read(t, rel)
			v, err := Unmarshal(want)
			if err != nil {
				t.Fatalf("Unmarshal: %v", err)
			}
			got, err := Marshal(v)
			if err != nil {
				t.Fatalf("Marshal: %v", err)
			}
			if !bytes.Equal(got, want) {
				t.Errorf("re-encoded bytes differ from Python's\n%s", firstDiff(got, want))
			}
		})
	}
}

func firstDiff(got, want []byte) string {
	i := 0
	for i < len(got) && i < len(want) && got[i] == want[i] {
		i++
	}
	lo := max(0, i-40)
	return "at byte " + strconv.Itoa(i) + ":\n got: " + strconv.Quote(string(got[lo:min(len(got), i+40)])) +
		"\nwant: " + strconv.Quote(string(want[lo:min(len(want), i+40)]))
}

func TestMarshalFloatsMatchPythonGolden(t *testing.T) {
	var rows [][3]string // bits, repr(x), json.dumps(x)
	golden.ReadJSON(t, "pycompat/float_repr.json", &rows)
	for _, r := range rows {
		u, _ := strconv.ParseUint(r[0], 16, 64)
		got, err := Marshal(math.Float64frombits(u))
		if err != nil || string(got) != r[2] {
			t.Errorf("Marshal(%s) = %q, %v; Python json.dumps = %q", r[0], got, err, r[2])
		}
	}
}

func TestMarshalStringsMatchPythonGolden(t *testing.T) {
	var rows [][3]string // s, repr(s), json.dumps(s, ensure_ascii=False)
	golden.ReadJSON(t, "pycompat/str_repr.json", &rows)
	for _, r := range rows {
		got, err := Marshal(r[0])
		if err != nil || string(got) != r[2] {
			t.Errorf("Marshal(%q) = %q, %v; Python json.dumps = %q", r[0], got, err, r[2])
		}
	}
}

func TestMarshal(t *testing.T) {
	cases := []struct {
		name string
		in   any
		want string
	}{
		{"null", nil, `null`},
		{"bools", []any{true, false}, "[\n  true,\n  false\n]"},
		{"int vs float", []any{10, int64(10), 10.0}, "[\n  10,\n  10,\n  10.0\n]"},
		{"big int", new(big.Int).Lsh(big.NewInt(1), 70), `1180591620717411303424`},
		{"non-finite floats", []any{math.NaN(), math.Inf(1), math.Inf(-1)}, "[\n  NaN,\n  Infinity,\n  -Infinity\n]"},
		{"top-level string has no newline", "x", `"x"`},
		{"empty containers", NewObject("l", []any{}, "o", NewObject(), "s", []string{}),
			"{\n  \"l\": [],\n  \"o\": {},\n  \"s\": []\n}"},
		{"html and line separators stay raw", "<a href=\"x\">&</a>\u2028\u2029",
			"\"<a href=\\\"x\\\">&</a>\u2028\u2029\""},
		{"controls", "\x00\b\f\n\r\t\x1f\x7f", `"\u0000\b\f\n\r\t\u001f` + "\x7f\""},
		{"non-ASCII raw", "Ribeir\u00e3o \u2014 \U0001F600", "\"Ribeir\u00e3o \u2014 \U0001F600\""},
		{"insertion order, not sorted", NewObject("z", 1, "a", 2), "{\n  \"z\": 1,\n  \"a\": 2\n}"},
		{"nesting", NewObject("a", []any{NewObject("b", []any{[]any{}})}),
			"{\n  \"a\": [\n    {\n      \"b\": [\n        []\n      ]\n    }\n  ]\n}"},
		{"typed slices", []*Object{NewObject("k", "v")}, "[\n  {\n    \"k\": \"v\"\n  }\n]"},
		{"Valuer", PyValuer{NewObject("season", 2)}, "{\n  \"season\": 2\n}"},
	}
	for _, c := range cases {
		got, err := Marshal(c.in)
		if err != nil {
			t.Errorf("%s: %v", c.name, err)
			continue
		}
		if string(got) != c.want {
			t.Errorf("%s:\n got %q\nwant %q", c.name, got, c.want)
		}
	}
}

// PyValuer adapts an *Object into a Valuer for the test above.
type PyValuer struct{ o *Object }

func (p PyValuer) PyJSON() any { return p.o }

func TestMarshalRejects(t *testing.T) {
	for name, v := range map[string]any{
		"map (unordered)":     map[string]any{"a": 1},
		"struct":              struct{ A int }{1},
		"invalid UTF-8":       "\xff",
		"invalid UTF-8 key":   NewObject("\xff", 1),
		"float32 (ambiguous)": float32(1.5),
	} {
		if _, err := Marshal(v); err == nil {
			t.Errorf("%s: Marshal succeeded, want an error", name)
		}
	}
}

func TestUnmarshalThenMarshalAgreesWithPython(t *testing.T) {
	// want = json.dumps(json.loads(in), ensure_ascii=False, indent=2), run in
	// CPython 3.12.
	cases := []struct{ in, want string }{
		{`{"a":1,"b":2,"a":3}`, "{\n  \"a\": 3,\n  \"b\": 2\n}"}, // first position, last value
		{`1e5`, `100000.0`}, // exponent means float
		{`1E2`, `100.0`},
		{`0.1e1`, `1.0`},
		{`10.000`, `10.0`},
		{`-0`, `0`},      // an int: the sign goes
		{`-0.0`, `-0.0`}, // a float: the sign stays
		{`1e400`, `Infinity`},
		{`-1e400`, `-Infinity`},
		{`123456789012345678901234567890`, `123456789012345678901234567890`},
		{` [1, 2.50, "x"] `, "[\n  1,\n  2.5,\n  \"x\"\n]"},
		{`"\u2028<>&"`, "\"\u2028<>&\""},
		{`"\ud83d\ude00"`, `"😀"`},
		{`[[], {}, [[]], {"a": {}}]`, "[\n  [],\n  {},\n  [\n    []\n  ],\n  {\n    \"a\": {}\n  }\n]"},
		{`null`, `null`},
		{`true`, `true`},
	}
	for _, c := range cases {
		v, err := Unmarshal([]byte(c.in))
		if err != nil {
			t.Errorf("Unmarshal(%s): %v", c.in, err)
			continue
		}
		got, err := Marshal(v)
		if err != nil || string(got) != c.want {
			t.Errorf("%s -> %q, %v; Python %q", c.in, got, err, c.want)
		}
	}
}

func TestUnmarshalTypes(t *testing.T) {
	v, err := Unmarshal([]byte(`{"i": 2, "f": 2.0, "s": "x", "b": true, "n": null, "l": [], "o": {}, "big": 99999999999999999999}`))
	if err != nil {
		t.Fatal(err)
	}
	o := v.(*Object)
	checks := map[string]func(any) bool{
		"i":   func(x any) bool { n, ok := x.(int64); return ok && n == 2 },
		"f":   func(x any) bool { f, ok := x.(float64); return ok && f == 2 },
		"s":   func(x any) bool { s, ok := x.(string); return ok && s == "x" },
		"b":   func(x any) bool { b, ok := x.(bool); return ok && b },
		"n":   func(x any) bool { return x == nil },
		"l":   func(x any) bool { l, ok := x.([]any); return ok && l != nil && len(l) == 0 },
		"o":   func(x any) bool { m, ok := x.(*Object); return ok && m.Len() == 0 },
		"big": func(x any) bool { b, ok := x.(*big.Int); return ok && b.String() == "99999999999999999999" },
	}
	for k, ok := range checks {
		x, present := o.Get(k)
		if !present || !ok(x) {
			t.Errorf("key %q decoded as %#v", k, x)
		}
	}
}

func TestUnmarshalErrors(t *testing.T) {
	for _, in := range []string{
		``,           // Python: Expecting value
		`{"a":1} x`,  // Python: Extra data
		`{"a":1}{}`,  // Python: Extra data
		`[1,]`,       // trailing comma
		`{'a': 1}`,   // single quotes
		`NaN`,        // documented divergence: Python accepts
		`[Infinity]`, // documented divergence: Python accepts
	} {
		if v, err := Unmarshal([]byte(in)); err == nil {
			t.Errorf("Unmarshal(%q) = %#v, want an error", in, v)
		}
	}
}

func TestObject(t *testing.T) {
	var o Object // zero value is usable
	o.Set("b", 1)
	o.Set("a", 2)
	o.Set("b", 3) // replace keeps position
	if got := o.Keys(); !slices.Equal(got, []string{"b", "a"}) {
		t.Fatalf("Keys = %v", got)
	}
	if v, _ := o.Get("b"); v != 3 {
		t.Errorf("Get(b) = %v", v)
	}
	if !o.Has("a") || o.Has("zz") {
		t.Error("Has")
	}
	c := o.Clone()
	c.Set("c", 4)
	if o.Len() != 2 || c.Len() != 3 {
		t.Errorf("Clone shares keys: %d %d", o.Len(), c.Len())
	}
	o.Delete("b")
	o.Delete("missing")
	if got := o.Keys(); !slices.Equal(got, []string{"a"}) {
		t.Errorf("after Delete, Keys = %v", got)
	}
	o.Set("b", 5) // re-added key goes to the end
	if got := o.Keys(); !slices.Equal(got, []string{"a", "b"}) {
		t.Errorf("re-added Keys = %v", got)
	}
	var keys []string
	for k := range c.All() {
		keys = append(keys, k)
		if k == "a" {
			break // early exit must be honoured
		}
	}
	if !slices.Equal(keys, []string{"b", "a"}) {
		t.Errorf("All = %v", keys)
	}
	var nilObj *Object
	if nilObj.Len() != 0 || nilObj.Has("x") || nilObj.Keys() != nil {
		t.Error("nil *Object must read as empty")
	}
}

func TestNewObjectPanicsOnBadArguments(t *testing.T) {
	for name, args := range map[string][]any{"odd": {"a"}, "non-string key": {1, 2}} {
		func() {
			defer func() {
				if recover() == nil {
					t.Errorf("%s: no panic", name)
				}
			}()
			NewObject(args...)
		}()
	}
}

func TestRepr(t *testing.T) {
	// Expectations are CPython's repr(json.loads(...)).
	v, err := Unmarshal([]byte(`{"season": 2.0, "g": [{"name": "Z\u00e9", "n": null, "t": true}], "e": {}}`))
	if err != nil {
		t.Fatal(err)
	}
	if got, want := Repr(v), "{'season': 2.0, 'g': [{'name': 'Z\u00e9', 'n': None, 't': True}], 'e': {}}"; got != want {
		t.Errorf("Repr = %s, want %s", got, want)
	}
	v, _ = Unmarshal([]byte(`["it's", "a\"b", 1e16, -0.0]`))
	if got, want := Repr(v), `["it's", 'a"b', 1e+16, -0.0]`; got != want {
		t.Errorf("Repr = %s, want %s", got, want)
	}
	if got := Repr("2_0"); got != `'2_0'` { // episode.load: got {ep[field]!r}
		t.Errorf("Repr(str) = %s", got)
	}
}

// TestOutputIsValidJSONForStdlib guards the escaping rules against producing
// something only Python would accept (NaN aside).
func TestOutputIsValidJSONForStdlib(t *testing.T) {
	for _, rel := range golden.Glob(t, "json/*.json") {
		v, err := Unmarshal(golden.Read(t, rel))
		if err != nil {
			t.Fatal(err)
		}
		b, _ := Marshal(v)
		if !json.Valid(b) {
			t.Errorf("%s: Marshal output is not valid JSON", rel)
		}
	}
}
