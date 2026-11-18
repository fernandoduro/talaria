// Package dotenv loads `.env` into the process environment
// (talaria/environment.py).
//
// The publishing code reads credentials from the environment, but the person
// who writes `.env` is the manager in an editor; without this bridge the file
// is filled in and publish complains about an undefined variable.
//
// It is a minimal parser on purpose: a dozen hand-written KEY=value lines. It
// does not interpolate ${OTHER}, does not expand ~ and does not read
// multi-line values.
package dotenv

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/pycompat"
)

// DefaultPath is <root>/.env.
func DefaultPath() (string, error) {
	root, err := config.Root()
	if err != nil {
		return "", err
	}
	return filepath.Join(root, ".env"), nil
}

// cleanValue strips surrounding whitespace and one pair of matching quotes.
// Pasting from a console often brings the quotes along, and a quoted token
// fails at the API with "invalid credential".
func cleanValue(v string) string {
	v = pycompat.Strip(v)
	if len(v) >= 2 && v[0] == v[len(v)-1] && (v[0] == '"' || v[0] == '\'') {
		v = v[1 : len(v)-1]
	}
	return v
}

// Load puts whatever is in the file at path (DefaultPath when empty) into
// the environment and returns how many variables entered.
//
// What is already in the environment wins over the file: `IG_PAGE_TOKEN=x
// talaria ...` has to override, which is how another credential gets tested
// without editing anything. A missing file is not an error, and a variable
// declared empty does not enter: "not configured" is the honest state.
func Load(path string) (int, error) {
	if path == "" {
		p, err := DefaultPath()
		if err != nil {
			return 0, err
		}
		path = p
	}
	data, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	if !utf8.Valid(data) {
		return 0, &os.PathError{Op: "read", Path: path, Err: errors.New("'utf-8' codec can't decode the file")}
	}
	// Python reads the file in text mode: "\r\n" and a lone "\r" both end a line.
	text := strings.ReplaceAll(string(data), "\r\n", "\n")
	text = strings.ReplaceAll(text, "\r", "\n")
	added := 0
	for _, line := range strings.Split(text, "\n") {
		line = pycompat.Strip(line)
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		key, value, _ := strings.Cut(line, "=") // '=' in the value stays in the value
		key = pycompat.Strip(key)
		value = cleanValue(value)
		if key == "" || value == "" {
			continue
		}
		if _, set := os.LookupEnv(key); set {
			continue
		}
		if err := os.Setenv(key, value); err != nil {
			return added, err
		}
		added++
	}
	return added, nil
}
