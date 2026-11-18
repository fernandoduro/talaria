// Package golden locates and reads the files tools/golden/dump.py writes
// under testdata/golden, for use from tests in any package.
package golden

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// Dir returns the absolute path of testdata/golden, found by walking up from
// the test's working directory to the directory holding go.mod.
func Dir(t testing.TB) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return filepath.Join(dir, "testdata", "golden")
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("golden: no go.mod above the working directory")
		}
		dir = parent
	}
}

// Path is the absolute path of a golden file, relative to testdata/golden.
func Path(t testing.TB, rel string) string {
	t.Helper()
	return filepath.Join(Dir(t), filepath.FromSlash(rel))
}

// Read returns a golden file's bytes. A missing file fails the test with a
// pointer to the generator.
func Read(t testing.TB, rel string) []byte {
	t.Helper()
	b, err := os.ReadFile(Path(t, rel))
	if err != nil {
		t.Fatalf("golden: %v (regenerate with: python tools/golden/dump.py)", err)
	}
	return b
}

// ReadJSON decodes a golden case file (always ASCII JSON) into v.
func ReadJSON(t testing.TB, rel string, v any) {
	t.Helper()
	if err := json.Unmarshal(Read(t, rel), v); err != nil {
		t.Fatalf("golden: %s: %v", rel, err)
	}
}

// Glob lists golden files matching pattern (relative to testdata/golden),
// as paths relative to testdata/golden.
func Glob(t testing.TB, pattern string) []string {
	t.Helper()
	dir := Dir(t)
	matches, err := filepath.Glob(filepath.Join(dir, filepath.FromSlash(pattern)))
	if err != nil {
		t.Fatal(err)
	}
	rels := make([]string, 0, len(matches))
	for _, m := range matches {
		rel, err := filepath.Rel(dir, m)
		if err != nil {
			t.Fatal(err)
		}
		rels = append(rels, filepath.ToSlash(rel))
	}
	return rels
}
