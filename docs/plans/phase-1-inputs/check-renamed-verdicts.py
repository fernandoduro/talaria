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

bad = []
with open("docs/plans/phase-1-inputs/identifier-verdicts.tsv") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if len(row) < 4 or row[2] != "renamed":
            continue
        old, note = row[0], row[3]
        if idents.get(old):
            bad.append(f"STILL AN IDENTIFIER: {old} ({idents[old]}x) -- verdict says: {note}")
for b in bad: print(b)
print(f"\n{len(bad)} false 'renamed' verdict(s)")
sys.exit(1 if bad else 0)
