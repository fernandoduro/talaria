// Package pyjson reads and writes JSON the way Talaria's Python code does:
// objects keep their key order, integers and floats stay distinct (10 vs
// 10.0), and the encoder reproduces json.dump(obj, f, ensure_ascii=False,
// indent=2) byte for byte, with no trailing newline.
//
// Decoded values use these Go types:
//
//	null    -> nil
//	true    -> bool
//	1       -> int64 (or *big.Int beyond int64; Python ints are unbounded)
//	1.0     -> float64 (any number with a fraction or exponent, as in Python)
//	"s"     -> string
//	[...]   -> []any
//	{...}   -> *Object
//
// Use structs for reading known fields; keep the *Object when a file is
// rewritten, so that fields Talaria does not know about survive.
package pyjson

import "iter"

// Object is a JSON object that remembers key insertion order, like a Python
// dict. The zero value is an empty object ready to use.
type Object struct {
	keys []string
	vals map[string]any
}

// NewObject builds an object from alternating key, value arguments:
// NewObject("season", 0, "uf", "SP"). It panics on an odd count or a
// non-string key, since that is a programming error.
func NewObject(kv ...any) *Object {
	if len(kv)%2 != 0 {
		panic("pyjson.NewObject: odd number of arguments")
	}
	o := &Object{}
	for i := 0; i < len(kv); i += 2 {
		k, ok := kv[i].(string)
		if !ok {
			panic("pyjson.NewObject: key is not a string")
		}
		o.Set(k, kv[i+1])
	}
	return o
}

// Set assigns v to key k. A new key goes to the end; an existing key keeps
// its position and takes the new value, as d[k] = v does in Python.
func (o *Object) Set(k string, v any) {
	if o.vals == nil {
		o.vals = make(map[string]any)
	}
	if _, ok := o.vals[k]; !ok {
		o.keys = append(o.keys, k)
	}
	o.vals[k] = v
}

// Get returns the value under k and whether it was present.
func (o *Object) Get(k string) (any, bool) {
	if o == nil {
		return nil, false
	}
	v, ok := o.vals[k]
	return v, ok
}

// Has reports whether k is present (Python's `k in d`).
func (o *Object) Has(k string) bool {
	_, ok := o.Get(k)
	return ok
}

// Delete removes k, keeping the order of the remaining keys.
func (o *Object) Delete(k string) {
	if o == nil {
		return
	}
	if _, ok := o.vals[k]; !ok {
		return
	}
	delete(o.vals, k)
	for i, key := range o.keys {
		if key == k {
			o.keys = append(o.keys[:i:i], o.keys[i+1:]...)
			break
		}
	}
}

// Len is the number of keys.
func (o *Object) Len() int {
	if o == nil {
		return 0
	}
	return len(o.keys)
}

// Keys returns the keys in insertion order. The slice is a copy.
func (o *Object) Keys() []string {
	if o == nil {
		return nil
	}
	return append([]string(nil), o.keys...)
}

// All iterates over key, value pairs in insertion order.
func (o *Object) All() iter.Seq2[string, any] {
	return func(yield func(string, any) bool) {
		if o == nil {
			return
		}
		for _, k := range o.keys {
			if !yield(k, o.vals[k]) {
				return
			}
		}
	}
}

// Clone is a shallow copy, Python's dict(d): nested objects and lists are
// shared, not copied.
func (o *Object) Clone() *Object {
	c := &Object{}
	for k, v := range o.All() {
		c.Set(k, v)
	}
	return c
}
