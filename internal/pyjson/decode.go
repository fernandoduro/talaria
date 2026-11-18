package pyjson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"os"
	"strconv"
	"strings"
)

// Unmarshal decodes one JSON document, as json.loads does, into the types
// listed in the package comment.
//
// Divergences from Python's json module, none reachable from a file Talaria
// itself wrote:
//   - NaN, Infinity and -Infinity are rejected (Python accepts them as an
//     extension). Python only writes them for non-finite floats, which no
//     Talaria field holds.
//   - A lone UTF-16 surrogate escape ("\ud800") decodes to U+FFFD; Python
//     keeps the surrogate and then fails when writing the file as UTF-8.
//   - Invalid UTF-8 bytes decode to U+FFFD; Python's open(encoding="utf-8")
//     raises UnicodeDecodeError.
//
// A key that appears twice keeps its first position and its last value, as
// Python's dict does.
func Unmarshal(data []byte) (any, error) {
	return Decode(bytes.NewReader(data))
}

// Decode reads one JSON document from r; anything but whitespace after it
// is an error ("Extra data" in Python).
func Decode(r io.Reader) (any, error) {
	dec := json.NewDecoder(r)
	dec.UseNumber()
	v, err := decodeValue(dec)
	if err != nil {
		return nil, err
	}
	if _, err := dec.Token(); err != io.EOF {
		if err == nil {
			return nil, errors.New("pyjson: extra data after the JSON value")
		}
		return nil, fmt.Errorf("pyjson: after the JSON value: %w", err)
	}
	return v, nil
}

// ReadFile decodes the JSON file at path.
func ReadFile(path string) (any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	v, err := Unmarshal(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return v, nil
}

// ReadObject decodes a JSON file whose top level must be an object.
func ReadObject(path string) (*Object, error) {
	v, err := ReadFile(path)
	if err != nil {
		return nil, err
	}
	o, ok := v.(*Object)
	if !ok {
		return nil, fmt.Errorf("%s: top-level JSON value is not an object", path)
	}
	return o, nil
}

func decodeValue(dec *json.Decoder) (any, error) {
	tok, err := dec.Token()
	if err != nil {
		if err == io.EOF {
			return nil, errors.New("pyjson: expecting value, got end of input")
		}
		return nil, fmt.Errorf("pyjson: %w", err)
	}
	return fromToken(dec, tok)
}

func fromToken(dec *json.Decoder, tok json.Token) (any, error) {
	switch t := tok.(type) {
	case json.Delim:
		switch t {
		case '{':
			o := &Object{}
			for dec.More() {
				kt, err := dec.Token()
				if err != nil {
					return nil, fmt.Errorf("pyjson: %w", err)
				}
				k, ok := kt.(string)
				if !ok {
					return nil, fmt.Errorf("pyjson: object key is %T, not a string", kt)
				}
				v, err := decodeValue(dec)
				if err != nil {
					return nil, err
				}
				o.Set(k, v)
			}
			if _, err := dec.Token(); err != nil { // '}'
				return nil, fmt.Errorf("pyjson: %w", err)
			}
			return o, nil
		case '[':
			list := []any{}
			for dec.More() {
				v, err := decodeValue(dec)
				if err != nil {
					return nil, err
				}
				list = append(list, v)
			}
			if _, err := dec.Token(); err != nil { // ']'
				return nil, fmt.Errorf("pyjson: %w", err)
			}
			return list, nil
		}
		return nil, fmt.Errorf("pyjson: unexpected delimiter %q", rune(t))
	case json.Number:
		return parseNumber(string(t))
	case string, bool, nil:
		return t, nil
	}
	return nil, fmt.Errorf("pyjson: unexpected token %T", tok)
}

// parseNumber follows Python's json scanner: a number with a fraction or an
// exponent is a float (so 1e5 re-encodes as 100000.0), otherwise an int.
func parseNumber(s string) (any, error) {
	if strings.ContainsAny(s, ".eE") {
		f, err := strconv.ParseFloat(s, 64)
		if err != nil && !errors.Is(err, strconv.ErrRange) {
			return nil, fmt.Errorf("pyjson: bad number %q: %w", s, err)
		}
		return f, nil // out of range: ±Inf, exactly as float() gives
	}
	if n, err := strconv.ParseInt(s, 10, 64); err == nil {
		return n, nil
	}
	b, ok := new(big.Int).SetString(s, 10)
	if !ok {
		return nil, fmt.Errorf("pyjson: bad number %q", s)
	}
	return b, nil
}
