// Package config holds talaria/config.py's constants and the project root.
//
// Python anchors projects/, prompts/, assets/ and .env to the directory of
// its own source files. A Go binary has no such anchor, so Root() is
// TALARIA_ROOT when set, else the working directory (decision D4).
//
// Only the constants the pure-logic packages need live here so far; the
// render, thumbnail and post constants arrive with the packages that use
// them (stage G2), together with the lazy caption-backend detection.
package config

import (
	"os"
	"sync"
	"time"
	_ "time/tzdata" // America/Sao_Paulo resolves on hosts without zoneinfo
)

// Grouping words into sentence segments (VTT and Whisper parsers).
const (
	SegMaxGap   = 0.7 // pause (s) that breaks the sentence
	SegMaxDur   = 5.0 // max duration (s) of a segment
	SegMaxChars = 75  // max characters before breaking
	SegEndPad   = 0.4 // padding at the end of each segment (s)
)

// Curation.
const (
	ClipMinS       = 60  // minimum clip duration
	ClipMaxS       = 90  // maximum duration
	GuestSpeechMin = 0.5 // minimum fraction of guest speech in the clip
)

// PostQuoteMaxLines is how many quote lines fit a post card; a 6th would
// invade the rule at y=2242.
const PostQuoteMaxLines = 5

// ShowName is the channel identity shown in the thumbnail badge.
const ShowName = "MY PODCAST"

// PublishTZ is the publishing timezone: dates always carry a zone, so a
// machine on UTC near midnight never shifts the publication day.
const PublishTZ = "America/Sao_Paulo"

// RootEnv names the environment variable that overrides the project root.
const RootEnv = "TALARIA_ROOT"

// Root is the directory holding projects/, prompts/, assets/ and .env:
// $TALARIA_ROOT when set and non-empty, else the working directory.
func Root() (string, error) {
	if r := os.Getenv(RootEnv); r != "" {
		return r, nil
	}
	return os.Getwd()
}

// PublishLocation is PublishTZ loaded once.
var PublishLocation = sync.OnceValues(func() (*time.Location, error) {
	return time.LoadLocation(PublishTZ)
})
