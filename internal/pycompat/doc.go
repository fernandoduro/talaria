// Package pycompat reproduces the small pieces of CPython semantics that the
// Talaria port depends on for byte-identical output: float repr, round(),
// int() coercion, character-based string length and slicing, repr() of
// strings, and str.capitalize().
//
// Each helper names the Python expression it stands in for. The expectations
// in the tests come from CPython 3.12 (see testdata/golden/pycompat, written
// by tools/golden/dump.py), never from reasoning about what Python "should"
// print.
package pycompat
