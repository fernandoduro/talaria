// Package layout is the single authority over project paths and migration.
package layout

import (
	"fmt"
	"os"
	"path/filepath"
)

const (
	Source         = "source"
	Decisions      = "decisions"
	Briefs         = "briefs"
	Publish        = "publish"
	YouTubeShorts  = "youtube_shorts"
	InstagramReels = "instagram_reels"
	InstagramPosts = "instagram_posts"
)

func Episode(pd string) string        { return filepath.Join(pd, "episode.json") }
func Video(pd string) string          { return filepath.Join(pd, Source, "video.mp4") }
func Transcript(pd string) string     { return filepath.Join(pd, Source, "transcript.json") }
func TranscriptTxt(pd string) string  { return filepath.Join(pd, Source, "transcript.txt") }
func SourceDir(pd string) string      { return filepath.Join(pd, Source) }
func Curation(pd string) string       { return filepath.Join(pd, Decisions, "curation.json") }
func Moments(pd string) string        { return filepath.Join(pd, Decisions, "moments.json") }
func Texts(pd string) string          { return filepath.Join(pd, Decisions, "texts.json") }
func Posts(pd string) string          { return filepath.Join(pd, Decisions, "posts.json") }
func Schedule(pd string) string       { return filepath.Join(pd, Decisions, "schedule.json") }
func Published(pd string) string      { return filepath.Join(pd, Decisions, "published.json") }
func Brief(pd, kind string) string    { return filepath.Join(pd, Briefs, kind+".md") }
func Thumbnail(pd string) string      { return filepath.Join(pd, Publish, "thumbnail.jpg") }
func EndCardMP4(pd string) string     { return filepath.Join(pd, Publish, "_end_card.mp4") }
func EpisodeTxt(pd string) string     { return filepath.Join(pd, Publish, "episode.txt") }
func Platform(pd, name string) string { return filepath.Join(pd, Publish, name) }
func PostsPNG(pd string) string       { return Platform(pd, InstagramPosts) }
func EnsureDir(path string) (string, error) {
	err := os.MkdirAll(filepath.Dir(path), 0755)
	return path, err
}
func Exists(path string) bool { _, err := os.Stat(path); return err == nil }
func isDir(path string) bool  { s, err := os.Stat(path); return err == nil && s.IsDir() }

var migration = []struct {
	old  string
	dest func(string) string
}{
	{"source.mp4", Video}, {"transcript.json", Transcript}, {"transcript.txt", TranscriptTxt}, {"curation.json", Curation}, {"moments.json", Moments}, {"texts.json", Texts}, {"posts.json", Posts},
	{"brief_materials.md", func(pd string) string { return Brief(pd, "materials") }}, {"brief_clips.md", func(pd string) string { return Brief(pd, "clips") }}, {"brief_posts.md", func(pd string) string { return Brief(pd, "posts") }}, {"thumbnail.jpg", Thumbnail},
}

func CheckDirs(pd string) error {
	for _, name := range []string{Source, Decisions, Briefs, Publish} {
		p := filepath.Join(pd, name)
		if Exists(p) && !isDir(p) {
			return fmt.Errorf("'%s' must be a folder, but it is a file in %s. Rename or remove that file and run again.", name, pd)
		}
	}
	return nil
}

// Move reports one origin/destination pair, including duplicate and removed notes.
type Move [2]string

// Migrate preserves duplicates as .bak and can resume after an interrupted move.
func Migrate(pd string) ([]Move, error) { return migrate(pd, os.Rename) }

// MigrateWithMove provides the filesystem move seam used to test recovery
// from an interrupted migration. Production callers use Migrate.
func MigrateWithMove(pd string, move func(string, string) error) ([]Move, error) {
	return migrate(pd, move)
}
func migrate(pd string, move func(string, string) error) ([]Move, error) {
	moved := []Move{}
	if !isDir(pd) {
		return moved, nil
	}
	if err := CheckDirs(pd); err != nil {
		return nil, err
	}
	for _, m := range migration {
		origin := filepath.Join(pd, m.old)
		if !Exists(origin) {
			continue
		}
		dest := m.dest(pd)
		if Exists(dest) {
			bak := origin + ".bak"
			if Exists(bak) {
				if err := os.Remove(bak); err != nil {
					return moved, err
				}
			}
			if err := os.Rename(origin, bak); err != nil {
				return moved, err
			}
			note := "(duplicate)"
			a, e := os.Stat(bak)
			b, f := os.Stat(dest)
			if e == nil && f == nil && a.Size() > b.Size() {
				note = "(duplicate — the .bak is BIGGER, check which counts)"
			}
			moved = append(moved, Move{m.old, filepath.Base(bak) + " " + note})
			continue
		}
		if _, err := EnsureDir(dest); err != nil {
			return moved, err
		}
		if err := move(origin, dest); err != nil {
			return moved, err
		}
		rel, _ := filepath.Rel(pd, dest)
		moved = append(moved, Move{m.old, rel})
	}
	for _, name := range []string{YouTubeShorts, InstagramReels, InstagramPosts} {
		origin := filepath.Join(pd, name)
		if !isDir(origin) {
			continue
		}
		dest := Platform(pd, name)
		if !isDir(dest) {
			if err := os.MkdirAll(filepath.Join(pd, Publish), 0755); err != nil {
				return moved, err
			}
			if err := move(origin, dest); err != nil {
				return moved, err
			}
			rel, _ := filepath.Rel(pd, dest)
			moved = append(moved, Move{name + "/", rel + "/"})
			continue
		}
		entries, err := os.ReadDir(origin)
		if err != nil {
			return moved, err
		}
		for _, ent := range entries {
			file := ent.Name()
			target := filepath.Join(dest, file)
			current := filepath.Join(origin, file)
			note := ""
			if Exists(target) {
				target += ".bak"
				if Exists(target) {
					if err := os.Remove(target); err != nil {
						return moved, err
					}
				}
				note = " (duplicate)"
			}
			if err := move(current, target); err != nil {
				return moved, err
			}
			rel, _ := filepath.Rel(pd, target)
			moved = append(moved, Move{name + "/" + file, rel + note})
		}
		if err := os.Remove(origin); err != nil {
			return moved, err
		}
	}
	p := filepath.Join(pd, "_thumb_frame.jpg")
	if Exists(p) {
		if err := os.Remove(p); err != nil {
			return moved, err
		}
		moved = append(moved, Move{"_thumb_frame.jpg", "(removed)"})
	}
	return moved, nil
}
