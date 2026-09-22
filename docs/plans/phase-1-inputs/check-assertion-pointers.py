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
        # The pointer must land on the assertion line ITSELF, not merely near
        # one. A row that names one assertion while pointing at another passes
        # every weaker check -- same file, in range, an assert within a few
        # lines, inside the right test -- and seven rows drifted exactly that
        # way in a single wave. The first line of a multi-line assert statement
        # contains the word, so this costs nothing legitimate: all 116 rows
        # satisfy it.
        if "assert" not in lines[n - 1]:
            bad.append(f"{f}:{n} -- pointer is not on an assertion line: "
                       f"{lines[n-1].strip()[:60]!r}")
            continue

        # And it must sit inside the test the row names, or the `proves`
        # statement describes someone else's assertion.
        enclosing = None
        for k in range(n - 1, -1, -1):
            m = re.match(r"\s*def (test_\w+)", lines[k])
            if m:
                enclosing = m.group(1); break
        want = row[2] if len(row) > 2 else ""
        if want and enclosing and enclosing != want:
            bad.append(f"{f}:{n} -- row says {want}, assertion is in {enclosing}")

for b in bad:
    print(b)
print(f"\n{checked} pointers checked, {len(bad)} stale")
sys.exit(1 if bad else 0)
