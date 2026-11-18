// Package episode validates metadata, preserving arbitrary extra fields.
package episode

import (
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"os"
	"strings"
)

var RequiredFields = []string{"season", "episode", "company", "city", "uf", "guests"}

func Template() *pyjson.Object {
	return pyjson.NewObject("season", 0, "episode", 0, "company", "", "city", "", "uf", "SP", "guests", []*pyjson.Object{pyjson.NewObject("name", "", "role", "", "linkedin", "")}, "topics", []any{}, "youtube_url", "")
}
func value(o *pyjson.Object, k string) any { v, _ := o.Get(k); return v }
func Load(pd string) (*pyjson.Object, error) {
	p := layout.Episode(pd)
	o, e := pyjson.ReadObject(p)
	if errors.Is(e, os.ErrNotExist) {
		return nil, fmt.Errorf("%s does not exist. Run 'python run.py ingest' to create the template.", p)
	}
	if e != nil {
		return nil, e
	}
	missing := []string{}
	for _, k := range RequiredFields {
		if !o.Has(k) {
			missing = append(missing, k)
		}
	}
	if len(missing) > 0 {
		return nil, fmt.Errorf("episode.json incomplete — missing: %s", strings.Join(missing, ", "))
	}
	empty := []string{}
	for _, k := range []string{"season", "episode", "city", "uf"} {
		v := value(o, k)
		if pyjson.Equal(v, "") || pyjson.Equal(v, []any{}) || pyjson.Equal(v, 0) {
			empty = append(empty, k)
		}
	}
	if len(empty) > 0 {
		return nil, fmt.Errorf("episode.json not filled in — blank fields: %s", strings.Join(empty, ", "))
	}
	company := value(o, "company")
	if !pyjson.Truthy(company) {
		company = ""
	}
	if pycompat.Strip(pyjson.Str(company)) == "" {
		if pyjson.Truthy(value(o, "guests")) {
			return nil, fmt.Errorf("episode.json not filled in — blank fields: company (required when there is an external guest)")
		}
		if !pyjson.Truthy(value(o, "topics")) {
			return nil, fmt.Errorf("episode.json: an episode with no external guest and no company needs at least one topic in 'topics' — it supplies thumbnail line 1 and the topic hashtag")
		}
	}
	for _, k := range []string{"season", "episode"} {
		v := value(o, k)
		n, e := pycompat.PyInt(v)
		if e != nil {
			if errors.Is(e, pycompat.ErrOverflow) {
				return nil, e
			}
			return nil, fmt.Errorf("episode.json: '%s' must be a whole number, got %s", k, pyjson.Repr(v))
		}
		o.Set(k, n)
	}
	return o, nil
}
func Save(pd string, o *pyjson.Object) (string, error) {
	p, e := layout.EnsureDir(layout.Episode(pd))
	if e != nil {
		return "", e
	}
	return p, pyjson.WriteFile(p, o)
}
func Code(o *pyjson.Object) string {
	n, _ := pycompat.PyInt(value(o, "episode"))
	return fmt.Sprintf("T%sE%02d", pyjson.Str(value(o, "season")), n)
}
func YouTubeURL(pd string) string {
	o, e := pyjson.ReadObject(layout.Episode(pd))
	if e != nil {
		return ""
	}
	s, _ := value(o, "youtube_url").(string)
	return pycompat.Strip(s)
}
