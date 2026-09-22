"""Every verdict of `renamed` must be true: the old name absent as an
identifier, the new name present. Grep cannot do this -- the old word
legitimately survives in Portuguese prose until the string pass. And every map
name still live as an identifier must carry a verdict row at all."""
import ast, pathlib, sys, csv, collections

idents = collections.Counter()
for f in list(pathlib.Path("talaria").glob("*.py")) + list(pathlib.Path("tests").glob("*.py")) \
       + [pathlib.Path("run.py")] + list(pathlib.Path("scripts").glob("*.py")):
    for n in ast.walk(ast.parse(f.read_text())):
        if   isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): idents[n.name] += 1
        elif isinstance(n, ast.arg):       idents[n.arg] += 1
        elif isinstance(n, ast.Name):      idents[n.id] += 1
        elif isinstance(n, ast.Attribute): idents[n.attr] += 1
        elif isinstance(n, ast.keyword) and n.arg: idents[n.arg] += 1

# The map is authoritative for what each old name became.
new_for, kind_of = {}, {}
with open("docs/plans/phase-1-inputs/rename-map.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) >= 3 and row[0] != "kind":
            new_for[row[1]] = row[2]
            kind_of[row[1]] = row[0]

verdicted = set()
with open("docs/plans/phase-1-inputs/identifier-verdicts.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if row and row[0] != "identifier":
            verdicted.add(row[0])

bad = []

# Half three: a map name still live as an identifier needs a verdict row of its
# own. `fonte` had no row anywhere -- the inventory excludes names already in
# the map, so the one site the map's carve-out did not cover was invisible to
# the verdicts file, and Step 5's `SURVIVED: fonte` was dismissed against that
# carve-out. A note saying what a name must NOT become is not a verdict.
for old, count in sorted(idents.items()):
    if old in new_for and count and old not in verdicted:
        bad.append(f"NO VERDICT ROW for a surviving map name: {old} "
                   f"({count}x, kind {kind_of[old]})")

with open("docs/plans/phase-1-inputs/identifier-verdicts.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) < 4 or row[2] != "renamed":
            continue
        old, note = row[0], row[3]
        # Half one: the old name must be gone as an identifier. Grep cannot ask
        # this -- the old word legitimately survives in Portuguese prose until
        # the string pass.
        if idents.get(old):
            bad.append(f"STILL AN IDENTIFIER: {old} ({idents[old]}x) -- verdict says: {note}")
        # Half two: the new name must actually exist. Without this, a symbol
        # DELETED rather than renamed passes silently -- old absent, new never
        # introduced, and the verdict still claims a rename.
        nn = new_for.get(old)
        if nn is None:
            bad.append(f"NO MAP ROW for a 'renamed' verdict: {old} -- verdict says: {note}")
        else:
            # A `new` value may be compound: one Portuguese word can split into
            # two English names when its senses differ by context (saida became
            # output_dir for a directory, concat_path for a file, output for a
            # returned string). Every part must exist, or the split is partly
            # unapplied.
            for part in (x.strip() for x in nn.split("/")):
                if not part:
                    continue
                if idents.get(part) or pathlib.Path(f"talaria/{part}.py").exists() \
                        or pathlib.Path(f"tests/{part}.py").exists():
                    continue
                bad.append(f"NEW NAME NEVER APPEARS: {old} -> {part} -- verdict says: {note}")

for b in bad: print(b)
print(f"\n{len(bad)} unsupported verdict claim(s)")
sys.exit(1 if bad else 0)
