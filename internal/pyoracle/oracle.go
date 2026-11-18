//go:build pyoracle

// Package pyoracle runs the CPython reference as a long-lived subprocess.
package pyoracle

import (
	"bufio"
	"encoding/json"
	"fmt"
	"github.com/fernandoduro/talaria/internal/golden"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
)

type Client struct {
	cmd *exec.Cmd
	in  io.WriteCloser
	out *bufio.Reader
	mu  sync.Mutex
}

func Start(t testing.TB) *Client {
	t.Helper()
	python := os.Getenv("TALARIA_PYTHON")
	if python == "" {
		python = "python3"
	}
	root := filepath.Dir(filepath.Dir(golden.Dir(t)))
	cmd := exec.Command(python, "-I", filepath.Join(root, "tools/golden/oracle.py"))
	cmd.Stderr = os.Stderr
	in, e := cmd.StdinPipe()
	if e != nil {
		t.Fatal(e)
	}
	out, e := cmd.StdoutPipe()
	if e != nil {
		t.Fatal(e)
	}
	if e = cmd.Start(); e != nil {
		t.Fatal(e)
	}
	c := &Client{cmd: cmd, in: in, out: bufio.NewReader(out)}
	t.Cleanup(func() {
		in.Close()
		if e := cmd.Wait(); e != nil {
			t.Errorf("oracle subprocess: %v", e)
		}
	})
	return c
}
func (c *Client) Query(op, s string, names []string) (string, string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	req := struct {
		Op    string   `json:"op"`
		Text  string   `json:"text"`
		Names []string `json:"names"`
	}{op, s, names}
	b, e := json.Marshal(req)
	if e != nil {
		return "", "", e
	}
	if _, e = c.in.Write(append(b, '\n')); e != nil {
		return "", "", e
	}
	line, e := c.out.ReadBytes('\n')
	if e != nil {
		return "", "", fmt.Errorf("reading oracle: %w", e)
	}
	var r struct {
		Value string
		Error *string
	}
	if e = json.Unmarshal(line, &r); e != nil {
		return "", "", e
	}
	if r.Error != nil {
		return r.Value, *r.Error, nil
	}
	return r.Value, "", nil
}
