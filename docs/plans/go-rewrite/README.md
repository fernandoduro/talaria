# Go rewrite: harness

Talaria is being ported from Python to Go in stages G0–G5 (named apart from the roadmap's Phases 2–4). Each stage is one PR from a `go/gN-*` branch into `main`. Go code stays inert until G4 switches the CLI; until then Python is the shipped tool and its suite must stay green on every PR. Python feature work is frozen meanwhile (see the roadmap in `docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md`).

## Running the checks

```bash
just check            # go vet, go test ./..., the Python suite, golden freshness, ledger
just ledger-unported  # the ledger check, listing every unported row
just golden           # rewrite testdata/golden from the Python implementation
```

`just` picks `.venv/bin/python` when it exists; set `TALARIA_PYTHON` to point elsewhere (a worktree has no venv of its own).

## Test ledger

`test-map.tsv` has one row per Python test, keyed by name, never by `file:line`:

| Column | Format |
|---|---|
| `python_test` | `module.Class.test_name`, e.g. `test_utils.TestStripMarkup.test_removes_html_entities` |
| `go_test` | `<package dir>.TestName[/subtest]`, e.g. `internal/text.TestStripMarkup/removes_html_entities`; empty while unported or dropped |
| `status` | `unported`, `ported`, `strengthened` or `dropped: <reason>` |

`go run ./tools/ledger` checks it. The Python side comes from `git ls-files tests/test_*.py`; `-python <interpreter>` also cross-checks the parsed names against unittest discovery. The Go side runs `go test -json` on every package a ported row names, so a row only passes when that exact test or subtest ran and passed. `-done test_utils,test_layout` fails while those modules have unported rows, which is how a stage proves its rows are complete. `-sync` adds missing Python tests as unported rows.

## Golden oracle

`tools/golden/dump.py` runs the Python implementation and writes the expected outputs under `testdata/golden/`; the Go tests read them and compare bytes. `testdata/golden/SOURCE` records the last commit touching `talaria/` or `tests/fixtures/` and a hash of those files. `dump.py --check` (part of `just check`) regenerates into a temp dir and fails on any difference, so a golden can never silently drift from the Python it claims to describe.

G0 dumps:

- `json/`: files Talaria writes, produced by its own save paths (`episode.save(template())`, `curation.save`, `curation.save_moments`, `transcribe._write_outputs` on `tests/fixtures/example.txt`), plus an adversarial document. `internal/pyjson` must decode and re-encode each one byte for byte.
- `pycompat/`: CPython's answers for `repr(float)`, `json.dumps(float)`, `round(x, n)`, `int(v)`, `repr(str)`, `str.isprintable()` and `str.capitalize()` (the last two for every code point).

The goldens freeze as plain test data at G5, when Python and `dump.py` are removed.

## G1 pure-logic harness

`g1/replay.json` records all 245 original G1 tests as API-call tables; `internal/parity.TestReplay/<python_test>` compares complete results, mutations, stdout and filesystem bytes instead of the original weaker assertions. The extra golden covers adversarial inputs and full reading packets. Default Go tests use only committed data; `just check` also regenerates it from Python to prove freshness. See [G1 parity notes](g1-findings.md) for the schema, Python quirks, safety boundaries, and exact fuzz commands.

The `pyoracle` build tag enables the long-lived Python differential oracle for `FuzzCleanCaption`, `FuzzFixProperNouns` and `FuzzFileSlug`. CI runs their regression seeds; ten-minute campaigns are an explicit stage gate, not part of default `go test`.
