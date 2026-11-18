// Package caption assembles and writes publishing captions.
package caption

import (
	"fmt"
	"github.com/fernandoduro/talaria/internal/layout"
	"github.com/fernandoduro/talaria/internal/pycompat"
	"github.com/fernandoduro/talaria/internal/pyjson"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const Separator = "\n\n"
const EpisodePrefix = "▶ Full episode: "

func Validate(field string, value any, piece string, out io.Writer) error {
	if value != nil {
		if _, ok := value.(string); !ok {
			return fmt.Errorf("'%s': '%s' expected text, got %s — it is the caption that accompanies the publication, one string only.", piece, field, pyjson.TypeName(value))
		}
	}
	if s, ok := value.(string); ok && strings.Contains(s, "—") && out != nil {
		fmt.Fprintf(out, "[caption] !! %s: '%s' has an em dash — the channel does not use one in a caption (it reads as AI text). Rewrite the sentence before publishing.\n", piece, field)
	}
	return nil
}
func stringOrEmpty(v any) string { s, _ := v.(string); return pycompat.Strip(s) }
func EpisodeLine(url any) string {
	s := stringOrEmpty(url)
	if s == "" {
		return ""
	}
	return EpisodePrefix + s
}
func join(parts ...string) string {
	a := []string{}
	for _, s := range parts {
		if s != "" {
			a = append(a, s)
		}
	}
	return strings.Join(a, Separator)
}
func Compose(description, hashtags any, episodeURL ...any) string {
	var u any
	if len(episodeURL) > 0 {
		u = episodeURL[0]
	}
	return join(stringOrEmpty(description), EpisodeLine(u), stringOrEmpty(hashtags))
}
func ComposeEpisode(title, description, hashtags any) string {
	return join(stringOrEmpty(title), stringOrEmpty(description), stringOrEmpty(hashtags))
}

// TxtPath follows os.path.splitext, including hidden files (.clip has no extension).
func TxtPath(piece string) string {
	base := filepath.Base(piece)
	ext := filepath.Ext(base)
	prefix := strings.TrimSuffix(base, ext)
	if strings.Trim(prefix, ".") == "" {
		ext = ""
	}
	return strings.TrimSuffix(piece, ext) + ".txt"
}
func Write(piece, s string) (string, error) {
	p, e := layout.EnsureDir(TxtPath(piece))
	if e != nil {
		return "", e
	}
	return p, os.WriteFile(p, []byte(s), 0644)
}
