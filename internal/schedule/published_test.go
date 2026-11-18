package schedule

import (
	"bytes"
	"errors"
	"fmt"
	"github.com/fernandoduro/talaria/internal/layout"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestRecordRenameFailurePreservesOldBytes(t *testing.T) {
	pd := t.TempDir()
	now := time.Date(2026, 11, 18, 15, 0, 0, 0, time.UTC)
	p, e := RecordAt(pd, "youtube_shorts", "a", "id", "url", now)
	if e != nil {
		t.Fatal(e)
	}
	old, _ := os.ReadFile(p)
	sentinel := errors.New("rename refused")
	calls := 0
	_, e = recordAt(pd, "instagram_reels", "b", "id2", "url2", now, func(tmp, dest string) error {
		calls++
		if filepath.Dir(tmp) != filepath.Dir(dest) {
			t.Error("temporary not on same filesystem")
		}
		b, e := os.ReadFile(tmp)
		if e != nil {
			t.Fatal(e)
		}
		if !bytes.Contains(b, []byte(`"slug": "b"`)) {
			t.Fatal("new record not complete before rename")
		}
		if dest != p {
			t.Errorf("wrong destination %s", dest)
		}
		return sentinel
	})
	if !errors.Is(e, sentinel) || calls != 1 {
		t.Fatalf("%v, calls=%d", e, calls)
	}
	got, _ := os.ReadFile(p)
	if !bytes.Equal(old, got) {
		t.Fatal("old record changed on rename failure")
	}
	entries, _ := os.ReadDir(filepath.Dir(p))
	if len(entries) != 1 || entries[0].Name() != "published.json" {
		t.Fatalf("temporary leaked: %v", entries)
	}
}
func TestRecordCorruptFailsClosed(t *testing.T) {
	for _, bad := range []string{"{half of a json", "{", "[]garbage", `{"youtube_shorts": [`, `{"youtube_shorts": true}`, `"not a record"`} {
		t.Run(bad, func(t *testing.T) {
			pd := t.TempDir()
			p, e := layout.EnsureDir(layout.Published(pd))
			if e != nil {
				t.Fatal(e)
			}
			os.WriteFile(p, []byte(bad), 0644)
			_, e = Record(pd, "youtube_shorts", "a", "id", "url")
			if e == nil {
				t.Fatal("corrupt record was overwritten")
			}
			b, _ := os.ReadFile(p)
			if string(b) != bad {
				t.Fatal("corrupt record changed")
			}
			entries, _ := os.ReadDir(filepath.Dir(p))
			if len(entries) != 1 {
				t.Fatal("temporary created before validation")
			}
		})
	}
}
func TestReadersNeverSeePartialRecord(t *testing.T) {
	pd := t.TempDir()
	if _, e := Record(pd, "youtube_shorts", "initial", "id", "url"); e != nil {
		t.Fatal(e)
	}
	done := make(chan struct{})
	errs := make(chan error, 1)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-done:
				return
			default:
				if _, e := LoadPublished(pd); e != nil {
					select {
					case errs <- e:
					default:
					}
					return
				}
			}
		}
	}()
	for i := 0; i < 50; i++ {
		if _, e := Record(pd, "youtube_shorts", fmt.Sprintf("clip%d", i), "id", "url"); e != nil {
			t.Fatal(e)
		}
	}
	close(done)
	wg.Wait()
	select {
	case e := <-errs:
		t.Fatal(e)
	default:
	}
	reg, e := LoadPublished(pd)
	if e != nil || !IsPublished(reg, "youtube_shorts", "clip49") {
		t.Fatalf("last publication missing: %v", e)
	}
}
func TestPublishedUnknownFieldsAndClock(t *testing.T) {
	pd := t.TempDir()
	p, _ := layout.EnsureDir(layout.Published(pd))
	os.WriteFile(p, []byte(`{"extra":{"z":2.0,"a":"é"}}`), 0644)
	_, e := RecordAt(pd, "youtube_shorts", "a", "id", "url", time.Date(2026, 11, 18, 1, 2, 3, 0, time.UTC))
	if e != nil {
		t.Fatal(e)
	}
	b, _ := os.ReadFile(p)
	for _, s := range []string{`"z": 2.0`, `"a": "é"`, `"published_at": "2026-11-17T22:02:03-03:00"`} {
		if !strings.Contains(string(b), s) {
			t.Errorf("missing %s in %s", s, b)
		}
	}
}
