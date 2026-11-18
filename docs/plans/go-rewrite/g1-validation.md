# G1 local verification — 2026-11-18

Branch: `go/g1-pure-logic`. Worktree: `/data/Code/gittrees/talaria/go-g1`. Go 1.26.2; CPython 3.12.13 via the main checkout's existing interpreter (`TALARIA_PYTHON=/data/Code/side_projects/talaria/.venv/bin/python`). The shared venv was not modified.

| Check | Observed result |
|---|---|
| `just check` | Passed: vet, Go suite, Python suite, golden regeneration and ledger |
| Python unittest | 394 tests, OK; the existing unclosed-fixture ResourceWarning remains |
| Go suite, `-json -count=1` | 53 top-level tests, 946 leaf test cases, 1,513 passing test/subtest events, zero failures |
| Original G1 cases | 245 names, replaying 567 observed Python API calls |
| Extra golden cases | 318 additional API calls/cases |
| Ledger | 245 strengthened, 149 unported, zero dropped; `-done` passes for all twelve G1 modules |
| Golden freshness | All 20 files match Python; includes the six new G1 Unicode/date/string and replay/extra files |
| `go test -race ./...` | Passed, including publication readers during atomic replacement |
| `go vet -tags pyoracle ./...` | Passed |
| Tagged oracle seeds | `go test -tags pyoracle ./internal/text ./internal/posts` passed |

## Final differential campaigns

Each target used two workers, valid UTF-8 input up to 4,096 bytes, and at most 512 bytes per proper name. Go's fuzz execution counts include generated inputs rejected by those domain guards; they are not counts of Python round-trips.

| Target | Requested duration | Go-reported package elapsed | Fuzz executions | Final campaign differences |
|---|---|---|---|---|
| `FuzzCleanCaption` | 10 minutes | 600.116 s | 8,846,911 | 0 |
| `FuzzFixProperNouns` | 10 minutes | 600.398 s | 7,056,631 | 0 |
| `FuzzFileSlug` | 10 minutes | 600.093 s | 9,579,850 | 0 |

Earlier discovery campaigns were not clean: proper-name fuzzing found an invalid regexp2 literal escape and then a replacement-template error-message mismatch; caption fuzzing found a long-whitespace match timeout. All three were fixed, minimized inputs were retained under `internal/text/testdata/fuzz/`, and the final ten-minute campaigns above were restarted after the fixes. They are not presented as zero-difference discovery runs.

CI is recorded in the PR after it runs; this file reports local execution, not a prediction of CI. Python application modules, the original test suite and `run.py` remain unchanged. No live media generation or publishing is required for G1, and none was attempted.
