"""Every row in the assertion classification must still point at its own assertion.

The classification keys on file:line, and every task that edits a test file
shifts those lines. A stale pointer silently detaches a `proves` statement
from the assertion it describes, which is worse than having no pointer -- the
next task reads the wrong row and re-derives the wrong expectation.
"""
import csv, pathlib, re, sys


def enclosing_test(lines, n):
    """Name of the nearest `def test_*` at or above line n, or None."""
    for i in range(n - 1, -1, -1):
        m = re.match(r"\s*def (test_[A-Za-z0-9_]+)", lines[i])
        if m:
            return m.group(1)
    return None


bad, checked = [], 0
with open("docs/plans/phase-1-inputs/assertion-classification.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) < 4 or row[0] == "file":
            continue
        f, ln, named = row[0], row[1], row[2]
        try:
            n = int(ln)
        except ValueError:
            bad.append(f"{f}:{ln} -- line is not a number"); continue
        p = pathlib.Path(f)
        if not p.exists():
            bad.append(f"{f}:{n} -- file does not exist"); continue
        lines = p.read_text().splitlines()
        checked += 1
        if n < 1 or n > len(lines):
            bad.append(f"{f}:{n} -- past end of file ({len(lines)} lines)"); continue
        # The pointer may sit on the first line of a multi-line statement, so
        # accept an assertion within the next two lines.
        window = " ".join(lines[n - 1:n + 2])
        if "assert" not in window:
            bad.append(f"{f}:{n} -- no assertion here: {lines[n-1].strip()[:70]!r}")
            continue
        # An assertion at the pointer is not enough: a row shifted onto a
        # DIFFERENT test's assertion satisfies every check above while its
        # `proves` statement now describes the wrong test. The row names the
        # test, so hold it to that.
        here = enclosing_test(lines, n)
        if here != named:
            bad.append(f"{f}:{n} -- row says {named}, assertion is in "
                       f"{here or '<no enclosing test>'}")

for b in bad:
    print(b)
print(f"\n{checked} pointers checked, {len(bad)} stale")
sys.exit(1 if bad else 0)
