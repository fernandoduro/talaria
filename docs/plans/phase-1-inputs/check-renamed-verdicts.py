"""Every verdict of `renamed` must be true: the old name absent as an
identifier, the new name present. Grep cannot do this -- the old word
legitimately survives in Portuguese prose until the string pass."""
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
new_for = {}
with open("docs/plans/phase-1-inputs/rename-map.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) >= 3 and row[0] != "kind":
            new_for[row[1]] = row[2]

bad = []
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
print(f"\n{len(bad)} false 'renamed' verdict(s)")
sys.exit(1 if bad else 0)
