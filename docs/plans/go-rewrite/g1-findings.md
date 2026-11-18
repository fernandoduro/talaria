# G1: parity notes

G1 ports pure logic only. Python remains the shipped CLI; no Go command or cutover is introduced.

## Tests and goldens

The 245 original G1 unittest names become table cases in `internal/parity.TestReplay`. Rather than copying weak substring assertions, `tools/golden/dump.py` runs each original test against Python and records its top-level API calls: inputs, results, argument mutations, warning bytes, and filesystem snapshots before and after. Go replays those inputs without Python and compares the observations, including the complete bytes of every written file. Filesystem snapshot key order is immaterial; file content and JSON result order are not. The ledger marks these rows `strengthened`; all 149 later-stage rows remain unported.

The extra table adds adversarial text, complete materials/clips/posts packets, rolling VTT, transcript JSON/text IO, unknown-field round-trips, numeric coercion, schedule retries, and the existing order-dependent approval behavior. The VTT input is a synthetic representative of YouTube rolling captions, not a downloaded episode. The original `example.txt` remains the real text transcript fixture. G2 owns `_segments_in_cut` and pixel wrapping; G1 tests the proportional trim helper moved out of render for brief generation.

The four new `pycompat/` goldens pin Unicode properties, `re.IGNORECASE` sets, string methods, and ISO dates. Property tests compare all Unicode scalar values with CPython 3.12 (Unicode 15.0.0), including normalization. Generated Unicode tables are intentionally large and GitHub marks `testdata/golden/**` as generated.

## Python semantics found during G1

- Python `re` classes are not regexp2's defaults: `\w` is letters/numbers/underscore, not combining marks or all connector punctuation, and `\s` additionally includes U+001C–U+001F. Literal ignore-case sets include dotless i, long s, Greek symbol variants and CPython's extra-case table. Case-insensitive backreferences compare simple lowercase without those extra pairs. Explicit classes and literal sets preserve the difference; regexp2 is imported only by text and posts, with match timeouts.
- `regexp2.Escape` emits an invalid short `\u605` escape for U+0605. Differential fuzz exposed a panic when that character occurred in a name. Literal patterns now use `\x{...}` escapes, and the minimized input is retained.
- `fix_proper_nouns` uses a Python replacement template in its recasing branch but a literal callback in its phonetic branch. A backslash in a name may therefore become an escape or raise an error only in one branch. G1 reproduces this rather than silently treating every name literally. A minimized template-error input and explicit template cases guard the distinction. Candidate simplification after cutover: make both branches literal.
- A long whitespace run originally exhausted regexp2's two-second timeout during failed filler/punctuation searches. Restricting those searches to the beginning of a whitespace run removes the quadratic rescans without changing successful matches; the minimized corpus input is retained.
- `datetime.date.fromisoformat` accepts basic and ISO week dates, not only `YYYY-MM-DD`. CPython 3.12 even ignores suffix bytes in a ten-byte basic-date string such as `2026082499`. G1 preserves those accepted inputs. Candidate tightening after cutover: enforce the format the operator message already advertises.
- `approve` replaces a same-slug entry immediately when encountered. Adjusting the first approved clip can therefore invade a later clip; adjusting a later clip onto an earlier one fails. G1 preserves and golden-tests that order dependence. Candidate fix after cutover: check every other clip before replacing.
- Speaker resolution still alternates blindly on turn markers: a host backchannel can shift all later labels. The existing known-risk test remains represented; no editorial heuristic is added.

## Safety boundaries

`RecordAt` injects the clock and `Record` uses the real clock in America/Sao_Paulo. Publication recording loads first and refuses invalid JSON, writes a complete synced temporary in the same directory, closes it, then calls `os.Rename`; failed paths clean up the temporary and retain the old file. Native tests force rename failure, observe concurrent readers, check corrupt-file preservation and pin the timezone. This is atomic replacement, not a cross-process read/modify/write lock; simultaneous writers can still lose updates, as in Python. Do not infer concurrent-publisher support from the reader test.

The common invalid-JSON diagnostics embedded in the fail-closed message use Python wording; other decoder diagnostics retain the Go detail. Refusal and recovery instructions do not depend on that formatting. G0's intentional `PyInt` divergences (underscores/non-ASCII digits/out-of-int64 inputs) and non-finite JSON read policy remain unchanged.

## Reproducing the checks

```bash
TALARIA_PYTHON=/path/to/python just check
go run ./tools/ledger -summary -done test_utils,test_txt_parse,test_layout,test_episode,test_curation,test_schedule,test_published,test_hashtags,test_texts,test_caption,test_brief,test_environment
go test -race ./...
TALARIA_PYTHON=/path/to/python go test -tags pyoracle ./internal/text ./internal/posts
TALARIA_PYTHON=/path/to/python go test -tags pyoracle ./internal/text -run '^$' -fuzz '^FuzzCleanCaption$' -fuzztime=10m -parallel=2
TALARIA_PYTHON=/path/to/python go test -tags pyoracle ./internal/text -run '^$' -fuzz '^FuzzFixProperNouns$' -fuzztime=10m -parallel=2
TALARIA_PYTHON=/path/to/python go test -tags pyoracle ./internal/posts -run '^$' -fuzz '^FuzzFileSlug$' -fuzztime=10m -parallel=2
```

The fuzz protocol is one request/response per line over a long-lived `python -I tools/golden/oracle.py` process per worker. Fuzz domains are valid UTF-8 strings of at most 4096 bytes (names at most 512 bytes); invalid UTF-8 cannot be a Python `str`. Default Go tests do not need Python. CI runs oracle regression seeds after `just check`, not thirty minutes of fuzzing.
