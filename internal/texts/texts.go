// Package texts loads publishing materials and derives thumbnail inputs.
package texts

import (
	"errors"
	"github.com/fernandoduro/talaria/internal/config"
	"github.com/fernandoduro/talaria/internal/curation"
	"github.com/fernandoduro/talaria/internal/episode"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"github.com/fernandoduro/talaria/internal/text"
	"golang.org/x/text/unicode/norm"
	"os"
	"regexp"
	"strings"
	"unicode"
)

var ChannelTags = []string{"#MyPodcast", "#Entrepreneurship", "#Startups"}
var alnum = regexp.MustCompile(`[A-Za-z0-9]+`)

func Slug(s string) string {
	var b strings.Builder
	for _, r := range norm.NFD.String(s) {
		if !unicode.Is(unicode.Mn, r) {
			b.WriteRune(r)
		}
	}
	parts := alnum.FindAllString(b.String(), -1)
	for i, p := range parts {
		parts[i] = strings.ToUpper(p[:1]) + p[1:]
	}
	return strings.Join(parts, "")
}
func Hashtags(city, company string, fallback ...string) []string {
	tags := append([]string{}, ChannelTags...)
	if company == "" && len(fallback) > 0 {
		company = fallback[0]
	}
	for _, v := range []string{city, company} {
		s := Slug(v)
		if s != "" {
			tag := "#" + s
			found := false
			for _, t := range tags {
				if t == tag {
					found = true
				}
			}
			if !found {
				tags = append(tags, tag)
			}
		}
	}
	return tags
}
func FormatLine(city, company string, fallback ...string) string {
	return strings.Join(Hashtags(city, company, fallback...), " ")
}
func Load(pd string) (*pyjson.Object, error) {
	o, e := pyjson.ReadObject(layout.Texts(pd))
	if errors.Is(e, os.ErrNotExist) {
		return pyjson.NewObject(), nil
	}
	return o, e
}
func Save(pd string, o *pyjson.Object) (string, error) {
	p, e := layout.EnsureDir(layout.Texts(pd))
	if e != nil {
		return "", e
	}
	return p, pyjson.WriteFile(p, o)
}
func ThumbArgs(pd string) (*pyjson.Object, error) {
	ep, e := episode.Load(pd)
	if e != nil {
		return nil, e
	}
	code := episode.Code(ep)
	names := []string{}
	for _, g := range curation.Objects(ep, "guests") {
		if pyjson.Truthy(text.Value(g, "name")) {
			names = append(names, text.String(g, "name"))
		}
	}
	l1 := text.Value(ep, "company")
	if !pyjson.Truthy(l1) {
		a, _ := text.Value(ep, "topics").([]any)
		if len(a) > 0 {
			l1 = a[0]
		} else {
			l1 = ""
		}
	}
	o := pyjson.NewObject("badge", config.ShowName+" • "+code, "l1", l1, "l2", code, "credits", strings.Join(names, " & "), "subtitle", text.String(ep, "city")+"/"+text.String(ep, "uf"))
	ts, e := Load(pd)
	if e != nil {
		return nil, e
	}
	if thumb, ok := text.Value(ts, "thumb").(*pyjson.Object); ok {
		for k, v := range thumb.All() {
			o.Set(k, v)
		}
	}
	return o, nil
}
func BuildKwargs(pd string) (*pyjson.Object, error) {
	o, e := ThumbArgs(pd)
	if e != nil {
		return nil, e
	}
	return pyjson.NewObject("badge", text.Value(o, "badge"), "headline_l1", text.Value(o, "l1"), "headline_l2", text.Value(o, "l2"), "credits", text.Value(o, "credits"), "subtitle", text.Value(o, "subtitle")), nil
}
