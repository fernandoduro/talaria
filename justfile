# Talaria task runner. `just check` is the gate every Go-rewrite stage (G0-G5)
# must pass: both suites green, goldens fresh, ledger consistent.

set shell := ["bash", "-euo", "pipefail", "-c"]

# The venv interpreter when present; override with TALARIA_PYTHON=/path/to/python.
python := env("TALARIA_PYTHON", if path_exists(".venv/bin/python") == "true" { ".venv/bin/python" } else { "python3" })

default: check

# go vet + go test + the Python suite + golden freshness + test ledger
check: vet test-go test-py golden-check ledger

vet:
    go vet ./...

test-go:
    go test ./...

test-py:
    {{python}} -m unittest discover -s tests

# Rewrite testdata/golden from the Python implementation
golden:
    {{python}} tools/golden/dump.py

# Fail if testdata/golden differs from what the Python implementation produces now
golden-check:
    {{python}} tools/golden/dump.py --check

# Ledger check: summary only, plus the unittest cross-check
ledger:
    go run ./tools/ledger -summary -python {{python}}

# Ledger check listing every unported row
ledger-unported:
    go run ./tools/ledger
