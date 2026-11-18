// Package posts handles posts.json and safe filenames. Rendering arrives in G2.
package posts

import (
	"errors"
	"fmt"
	"github.com/dlclark/regexp2"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/transcript"
	"os"
	"strings"
	"time"
)

var unsafe = func() *regexp2.Regexp {
	r := regexp2.MustCompile(`[^\p{L}\p{N}_.-]`, 0)
	r.MatchTimeout = 2 * time.Second
	return r
}()

func FileSlug(s string) (string, error) {
	s, e := unsafe.Replace(pycompat.Strip(s), "_", -1, -1)
	if e != nil {
		return "", e
	}
	s = strings.Trim(s, "._-")
	if s == "" {
		s = "post"
	}
	return s, nil
}
func Load(pd string) ([]*pyjson.Object, error) {
	p := layout.Posts(pd)
	v, e := pyjson.ReadFile(p)
	if errors.Is(e, os.ErrNotExist) {
		return nil, fmt.Errorf("%s does not exist. Run 'python run.py post --project <slug> --clips <n,n>' and choose the quotes in session before generating.", p)
	}
	if e != nil {
		return nil, e
	}
	if !pyjson.Truthy(v) {
		return []*pyjson.Object{}, nil
	}
	o, ok := v.(*pyjson.Object)
	if !ok {
		return nil, fmt.Errorf("posts.json: expected object")
	}
	return transcript.Objects(text.Value(o, "posts"))
}
