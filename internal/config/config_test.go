package config

import (
	"os"
	"testing"
	"time"
)

func TestRoot(t *testing.T) {
	t.Setenv(RootEnv, "/root/from-env")
	r, e := Root()
	if e != nil || r != "/root/from-env" {
		t.Fatalf("%s %v", r, e)
	}
	t.Setenv(RootEnv, "")
	cwd, _ := os.Getwd()
	r, e = Root()
	if e != nil || r != cwd {
		t.Fatalf("%s %v", r, e)
	}
}
func TestPublishingTimezone(t *testing.T) {
	loc, e := PublishLocation()
	if e != nil {
		t.Fatal(e)
	}
	s := time.Date(2026, 11, 18, 1, 0, 0, 0, time.UTC).In(loc).Format("2006-01-02 -07:00")
	if s != "2026-11-17 -03:00" {
		t.Fatal(s)
	}
}
