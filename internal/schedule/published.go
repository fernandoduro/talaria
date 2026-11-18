package schedule

import (
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/transcript"
	"os"
	"path/filepath"
	"time"
)

// LoadPublished fails closed. Corrupt JSON never becomes an empty history.
func LoadPublished(pd string) (*pyjson.Object, error) {
	p := layout.Published(pd)
	b, e := os.ReadFile(p)
	if errors.Is(e, os.ErrNotExist) {
		return pyjson.NewObject(), nil
	}
	if e != nil {
		return nil, e
	}
	v, e := pyjson.Unmarshal(b)
	if e != nil {
		return nil, fmt.Errorf("%s is corrupt (%v). I will not assume 'nothing published' — that would republish everything. Check what is already live on the platform profiles and recreate the file by hand.", p, jsonDiagnostic(b, e))
	}
	if !pyjson.Truthy(v) {
		return pyjson.NewObject(), nil
	}
	o, ok := v.(*pyjson.Object)
	if !ok {
		return nil, fmt.Errorf("%s is corrupt (expected object). I will not assume 'nothing published' — that would republish everything. Check what is already live on the platform profiles and recreate the file by hand.", p)
	}
	return o, nil
}
func IsPublished(reg *pyjson.Object, platform, slug string) bool {
	a, _ := transcript.Objects(text.Value(reg, platform))
	for _, r := range a {
		if text.String(r, "slug") == slug {
			return true
		}
	}
	return false
}
func Record(pd, platform, slug, id, url string) (string, error) {
	return RecordAt(pd, platform, slug, id, url, time.Now())
}

// RecordAt injects the clock; a unique same-directory temporary is removed on
// every failed path. A successful rename replaces the old record atomically.
func RecordAt(pd, platform, slug, id, url string, now time.Time) (string, error) {
	return recordAt(pd, platform, slug, id, url, now, os.Rename)
}
func recordAt(pd, platform, slug, id, url string, now time.Time, rename func(string, string) error) (string, error) {
	reg, e := LoadPublished(pd)
	if e != nil {
		return "", e
	}
	loc, e := config.PublishLocation()
	if e != nil {
		return "", e
	}
	a, e := transcript.Objects(text.Value(reg, platform))
	if e != nil {
		return "", e
	}
	reg.Set(platform, append(a, pyjson.NewObject("slug", slug, "id", id, "url", url, "published_at", now.In(loc).Format("2006-01-02T15:04:05-07:00"))))
	p, e := layout.EnsureDir(layout.Published(pd))
	if e != nil {
		return "", e
	}
	b, e := pyjson.Marshal(reg)
	if e != nil {
		return "", e
	}
	f, e := os.CreateTemp(filepath.Dir(p), ".published-*.tmp")
	if e != nil {
		return "", e
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if e = f.Chmod(0644); e == nil {
		_, e = f.Write(b)
	}
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return "", e
	}
	if e = rename(tmp, p); e != nil {
		return "", e
	}
	return p, nil
}
