// Package schedule validates editorial schedules and filters unpublished work.
package schedule

import (
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/posts"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"github.com/fernandoduro/talaria/internal/transcript"
	"os"
	"slices"
	"sort"
	"strings"
	"time"
)

func Today() (time.Time, error) {
	loc, e := config.PublishLocation()
	if e != nil {
		return time.Time{}, e
	}
	n := time.Now().In(loc)
	return time.Date(n.Year(), n.Month(), n.Day(), 0, 0, 0, 0, time.UTC), nil
}
func PlatformsOf(item *pyjson.Object) []string {
	if text.String(item, "kind") == "clip" {
		return []string{layout.YouTubeShorts, layout.InstagramReels}
	}
	if text.String(item, "kind") == "post" {
		return []string{layout.InstagramPosts}
	}
	return nil
}
func DateOf(item *pyjson.Object) (time.Time, error) {
	s, ok := text.Value(item, "date").(string)
	if !ok {
		return time.Time{}, fmt.Errorf("date must be a string")
	}
	return pycompat.DateFromISOFormat(s)
}
func Moments(pd string) ([]*pyjson.Object, error) {
	p := layout.Moments(pd)
	v, e := pyjson.ReadFile(p)
	if errors.Is(e, os.ErrNotExist) {
		return nil, fmt.Errorf("%s does not exist. Run 'python run.py curate --project <slug> --export' before scheduling clips.", p)
	}
	if e != nil {
		return nil, e
	}
	return transcript.Objects(v)
}
func Load(pd string) ([]*pyjson.Object, error) {
	p := layout.Schedule(pd)
	v, e := pyjson.ReadFile(p)
	if errors.Is(e, os.ErrNotExist) {
		return nil, fmt.Errorf(`%s does not exist. Write the publishing schedule: {"schedule": [{"date": "YYYY-MM-DD", "kind": "clip|post", "slug": "..."}]}`, p)
	}
	if e != nil {
		return nil, e
	}
	var items []*pyjson.Object
	if pyjson.Truthy(v) {
		o, ok := v.(*pyjson.Object)
		if !ok {
			return nil, fmt.Errorf("schedule.json: expected object")
		}
		items, e = transcript.Objects(text.Value(o, "schedule"))
		if e != nil {
			return nil, e
		}
	}
	if len(items) == 0 {
		return nil, fmt.Errorf("%s has no item in 'schedule'", p)
	}
	var clips, ps []*pyjson.Object
	seen := map[string]bool{}
	for i, item := range items {
		slug, kind := text.String(item, "slug"), text.String(item, "kind")
		whereSlug := slug
		if whereSlug == "" {
			whereSlug = "?"
		}
		where := fmt.Sprintf("schedule item %d ('%s')", i+1, whereSlug)
		if kind != "clip" && kind != "post" {
			return nil, fmt.Errorf("%s: kind %s — use 'clip' or 'post'", where, pyjson.Repr(kind))
		}
		if slug == "" {
			return nil, fmt.Errorf("%s: no slug", where)
		}
		if strings.ContainsAny(slug, "/\\") || strings.Trim(slug, ". ") != slug {
			return nil, fmt.Errorf("%s: the slug cannot carry a slash nor start/end with a dot — it becomes a filename in publish/, and would then point outside the episode folder", where)
		}
		key := kind + "\x00" + slug
		if seen[key] {
			return nil, fmt.Errorf("%s: %s appears twice — to change the date, edit the existing item instead of repeating it", where, kind)
		}
		seen[key] = true
		if _, e := DateOf(item); e != nil {
			return nil, fmt.Errorf("%s: date %s invalid — use YYYY-MM-DD of a day that exists", where, pyjson.Repr(text.Value(item, "date")))
		}
		var source []*pyjson.Object
		sourcePath, label := layout.Moments(pd), "clips"
		if kind == "clip" {
			if clips == nil {
				clips, e = Moments(pd)
				if e != nil {
					return nil, e
				}
			}
			source = clips
		} else {
			sourcePath, label = layout.Posts(pd), "posts"
			if ps == nil {
				ps, e = posts.Load(pd)
				if e != nil {
					return nil, e
				}
			}
			source = ps
		}
		slugs := []string{}
		var found *pyjson.Object
		for _, o := range source {
			s := text.String(o, "slug")
			slugs = append(slugs, s)
			if s == slug {
				found = o
			}
		}
		if found == nil {
			sort.Strings(slugs)
			slugs = slices.Compact(slugs)
			return nil, fmt.Errorf("%s: not in %s — available %s: %s", where, sourcePath, label, strings.Join(slugs, ", "))
		}
		if kind == "post" {
			a, _ := text.Value(found, "cards").([]any)
			if len(a) > 10 {
				return nil, fmt.Errorf("post '%s' has %d cards — the Instagram carousel accepts at most 10; break it into two posts", slug, len(a))
			}
		}
	}
	return items, nil
}

type Pair struct {
	Item     *pyjson.Object
	Platform string
}
type PendingOptions struct {
	Day       time.Time
	Only      []string
	Platforms []string
}

func Pending(pd string, opt PendingOptions) ([]Pair, error) {
	day := opt.Day
	if day.IsZero() {
		d, e := Today()
		if e != nil {
			return nil, e
		}
		day = d
	}
	known := []string{layout.InstagramPosts, layout.InstagramReels, layout.YouTubeShorts}
	unknown := []string{}
	if opt.Platforms != nil {
		for _, p := range opt.Platforms {
			if !slices.Contains(known, p) {
				unknown = append(unknown, p)
			}
		}
		sort.Strings(unknown)
		unknown = slices.Compact(unknown)
		if len(unknown) > 0 {
			return nil, fmt.Errorf("unknown platform: %s — use %s", strings.Join(unknown, ", "), strings.Join(known, ", "))
		}
	}
	items, e := Load(pd)
	if e != nil {
		return nil, e
	}
	if opt.Only != nil {
		slugs := []string{}
		for _, o := range items {
			slugs = append(slugs, text.String(o, "slug"))
		}
		unknown = nil
		for _, s := range opt.Only {
			if !slices.Contains(slugs, s) {
				unknown = append(unknown, s)
			}
		}
		sort.Strings(unknown)
		unknown = slices.Compact(unknown)
		if len(unknown) > 0 {
			return nil, fmt.Errorf("--only: %s not in the schedule (%s)", strings.Join(unknown, ", "), layout.Schedule(pd))
		}
	}
	reg, e := LoadPublished(pd)
	if e != nil {
		return nil, e
	}
	pairs := []Pair{}
	for _, item := range items {
		slug := text.String(item, "slug")
		if opt.Only != nil {
			if !slices.Contains(opt.Only, slug) {
				continue
			}
		} else {
			d, e := DateOf(item)
			if e != nil {
				return nil, e
			}
			if d.After(day) {
				continue
			}
		}
		for _, pl := range PlatformsOf(item) {
			if opt.Platforms != nil && !slices.Contains(opt.Platforms, pl) {
				continue
			}
			if !IsPublished(reg, pl, slug) {
				pairs = append(pairs, Pair{item, pl})
			}
		}
	}
	return pairs, nil
}
