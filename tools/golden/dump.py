# python-reason: drives the Python implementation to produce golden files
"""Python oracle for the Go port: writes the expected outputs under testdata/golden.

The Go tests read these files and compare bytes. Expectations come from
running CPython and the `talaria` package, never from hand-written guesses,
so a parity failure means the Go code is wrong, not the golden.

    python tools/golden/dump.py           # (re)write testdata/golden
    python tools/golden/dump.py --check   # regenerate into a temp dir and diff

Run it with the project venv (it imports talaria, which needs Pillow and
ffmpeg at import time). It lives only until stage G5, when Python is removed
and the goldens freeze as plain test data.

Each dumper is a function registered with @dumper("<relative path>"); it
returns the file's bytes. Later stages add dumpers next to the G0 ones.
"""
from __future__ import annotations

import argparse
import contextlib
import filecmp
import hashlib
import io
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "testdata" / "golden"
FIXTURES = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(ROOT))

from talaria import curation, episode, layout, transcribe, txt_parse  # noqa: E402

DUMPERS: dict[str, Callable[[], bytes]] = {}


def dumper(relpath: str):
    def register(fn):
        if relpath in DUMPERS:
            raise SystemExit(f"duplicate dumper for {relpath}")
        DUMPERS[relpath] = fn
        return fn
    return register


def case_json(value) -> bytes:
    """Serialises a case file: ASCII-only, so no reader can misdecode it.
    A list is written one row per line, which keeps diffs readable."""
    if isinstance(value, list):
        rows = ",\n".join(json.dumps(row, ensure_ascii=True) for row in value)
        return f"[\n{rows}\n]\n".encode("ascii")
    return (json.dumps(value, ensure_ascii=True, indent=1) + "\n").encode("ascii")


def float_hex(x: float) -> str:
    """The IEEE-754 bits of x, so Go reconstructs exactly the same double."""
    return struct.pack(">d", x).hex()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@dumper("SOURCE")
def source() -> bytes:
    files = sorted(git("ls-files", "talaria", "tests/fixtures").splitlines())
    h = hashlib.sha256()
    for name in files:
        h.update(name.encode() + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return (
        "# Python sources these goldens were dumped from (tools/golden/dump.py).\n"
        f"talaria_commit {git('log', '-1', '--format=%H', '--', 'talaria', 'tests/fixtures')}\n"
        f"talaria_sha256 {h.hexdigest()}\n"
    ).encode()


# ---------------------------------------------------------------------------
# JSON files Talaria writes, produced by the real save paths
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def project():
    with tempfile.TemporaryDirectory(prefix="talaria-golden-") as pd:
        with contextlib.redirect_stdout(io.StringIO()):
            yield pd


@dumper("json/episode_template.json")
def episode_template() -> bytes:
    with project() as pd:
        return Path(episode.save(pd, episode.template())).read_bytes()


def _curation_state() -> dict:
    state = curation.new_state(target=5)
    state["rounds"] = 2
    curation.approve(state, {
        "slug": "side-project-to-company",
        "start": 44.0,
        "end": 121.5,
        "kind": "story",
        "screen_text": "It began as a side project — then a customer asked to buy it",
        "youtube_title": "From side project to company: “we had no ambition at all”",
        "summary": "How Acme went from night tinkering to a real company",
        "hashtags": ["#Acme", "#Ribeir\u00e3oA\u00e7a\u00ed", "#startups"],
        "speaker_note": "Guest answers; host asks the question at 0:35",
    })
    curation.approve(state, {
        "slug": "validate-before-building",
        "start": 3730.0,
        "end": 3801.25,
        "kind": "advice",
        "screen_text": "Validate before you build",
        "confidence": 0.85,
        "extra": {"nested": [1, 2.0, None, True], "empty": {}, "list": []},
    })
    curation.reject(state, {"start": 10.0, "end": 75.333, "summary": "Intro chit-chat"},
                    "no thesis — just greetings\nand a line break")
    curation.reject(state, {"start": 300, "end": 370, "screen_text": "R&D <story> & \"quotes\""},
                    "duplicate of an approved clip")
    return state


@dumper("json/curation_state.json")
def curation_state() -> bytes:
    with project() as pd:
        return Path(curation.save(pd, _curation_state())).read_bytes()


@dumper("json/moments.json")
def moments() -> bytes:
    with project() as pd:
        return Path(curation.save_moments(pd, _curation_state())).read_bytes()


@dumper("json/transcript_example.json")
def transcript_example() -> bytes:
    segs = txt_parse.parse_txt(str(FIXTURES / "example.txt"))
    with project() as pd:
        transcribe._write_outputs(segs, pd)
        return Path(layout.transcript(pd)).read_bytes()


@dumper("json/transcript_example_duration.json")
def transcript_example_duration() -> bytes:
    segs = txt_parse.parse_txt(str(FIXTURES / "example.txt"), total_duration=3750.4)
    with project() as pd:
        transcribe._write_outputs(segs, pd)
        return Path(layout.transcript(pd)).read_bytes()


@dumper("json/adversarial.json")
def adversarial() -> bytes:
    """Every encoder quirk in one document, written by plain json.dump."""
    value = {
        "floats": [0.0, -0.0, 1.0, 10.0, 0.1, 0.30000000000000004, 1 / 3, 2.675,
                   0.0001, 0.00001, 1e15, 1e16, 9999999999999998.0, 1.5e-7,
                   123456789.123, 5e-324, 1.7976931348623157e308, -12.5, 3750.4],
        "ints": [0, -1, 2 ** 63 - 1, -(2 ** 63), 2 ** 70, -(2 ** 70)],
        "strings": ["", "plain", "\u00e3 \u00e9 \u00e7 \u00fc \u00f1", "em — dash … “curly” ‘quotes’",
                    "emoji 😀 and 🇧🇷", "<b>&amp;</b>", "line\u2028sep\u2029para",
                    "ctrl \x00\x01\x08\x09\x0a\x0b\x0c\x0d\x1b\x1f end",
                    "del \x7f nbsp \xa0 bom \ufeff zwsp \u200b",
                    "quote \" backslash \\ slash /", "\\u00e9 is not an escape"],
        "literals": [True, False, None],
        "empty": {"list": [], "object": {}},
        "nested": [[], [[]], [{}], {"a": [{"b": {"c": []}}]}],
        "\u00e3\u00e7\u00e9 key": "unicode key",
        "": "empty key",
        "order": {"z": 1, "a": 2, "m": 3},
    }
    buf = io.StringIO()
    json.dump(value, buf, ensure_ascii=False, indent=2)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# pycompat expectations
# ---------------------------------------------------------------------------

HAND_FLOATS = [
    0.0, -0.0, 1.0, -1.0, 0.5, 1.5, 2.5, 12.0, 3.5, 0.1, 0.2, 0.3, 1 / 3, 2 / 3,
    2.675, 1.005, 0.125, 0.375, 1e-4, 9.999e-5, 1e-5, 1e15, 1e16, 1e17,
    9999999999999998.0, 1e16 - 2, 1e22, 1e23, 123456789012345678.0,
    5e-324, 2.2250738585072014e-308, 1.7976931348623157e308,
    float("inf"), float("-inf"), float("nan"),
]


def _float_samples() -> list[float]:
    rnd = random.Random(20261118)
    xs = list(HAND_FLOATS)
    for _ in range(400):  # arbitrary bit patterns: every exponent range
        x = struct.unpack(">d", rnd.getrandbits(64).to_bytes(8, "big"))[0]
        if x == x:
            xs.append(x)
    for _ in range(400):  # the shapes Talaria writes: seconds with ms precision
        xs.append(round(rnd.uniform(0, 7200), rnd.randint(0, 3)))
    for _ in range(200):  # around the fixed/exponent switch points
        xs.append(rnd.uniform(1, 10) * 10.0 ** rnd.randint(-7, 18))
    return xs


@dumper("pycompat/float_repr.json")
def float_repr() -> bytes:
    rows = [[float_hex(x), repr(x), json.dumps(x)] for x in _float_samples()]
    return case_json(rows)


@dumper("pycompat/round.json")
def round_cases() -> bytes:
    rnd = random.Random(1118)
    # the hand-picked values and Talaria-shaped seconds, not the random bit
    # patterns: those almost all come back unchanged and only add bulk
    xs = [x for x in HAND_FLOATS if x == x]
    xs += [round(rnd.uniform(0, 7200), rnd.randint(1, 6)) for _ in range(80)]
    xs += [rnd.uniform(1, 10) * 10.0 ** rnd.randint(-7, 18) for _ in range(40)]
    # exact binary ties and their neighbours
    for k in range(-20, 21):
        xs += [k / 2, k / 4, k / 8, k / 16, k + 0.5, (k + 0.5) / 100]
    for _ in range(100):
        xs.append(rnd.randint(-10 ** 6, 10 ** 6) / 1000 + 0.0005)
    rows = []
    for x in xs:
        for n in (-309, -2, 0, 1, 2, 3, 6, 324):
            try:
                r = round(x, n)
            except OverflowError:
                continue  # documented divergence: Go returns ±Inf
            rows.append([float_hex(x), n, float_hex(r)])
    return case_json(rows)


def _typed(v):
    """Tags a Python value so Go can rebuild exactly the same input."""
    if v is None:
        return ["none"]
    if isinstance(v, bool):
        return ["bool", v]
    if isinstance(v, int):
        return ["int", str(v)]
    if isinstance(v, float):
        return ["float", float_hex(v)]
    if isinstance(v, str):
        return ["str", v]
    if isinstance(v, list):
        return ["list"]
    return ["dict"]


@dumper("pycompat/int.json")
def int_cases() -> bytes:
    inputs = [0, 7, -7, 2 ** 70, 2.7, -2.7, 0.9999, -0.5, 1e18, 1e20, float("inf"),
              float("-inf"), float("nan"), True, False, None, [], [1], {}, {"a": 1},
              "2", " -3\n", "+5", "007", "-0", "", " ", "2.0", "2e3", "--5", "+-5",
              "two", "0x10", "2_0", "\u0663", "\u00a02\u2003", "\t42\x0b", "\x1c7\x1f",
              "9223372036854775807", "9223372036854775808"]
    rows = []
    for v in inputs:
        try:
            out = ["ok", str(int(v))]
        except Exception as e:  # noqa: BLE001 - the exception class is the expectation
            out = [type(e).__name__, str(e)]
        rows.append([_typed(v), out])
    return case_json(rows)


STR_SAMPLES = [
    "", "abc", "it's", 'say "hi"', "both ' and \"", "tab\there", "nl\nend", "cr\r",
    "\x00\x01\x1f\x7f", "\x80\x9f\xa0\xad\xff", "\u00e3 \u00e9 \u00e7 — “quoted” …", "😀 🇧🇷",
    "\u2028\u2029", "\u200b\ufeff\u00ad", "\U000e0001", "\ue000", "\U0010ffff",
    "\u0378", "e\u0301", "a\\b", "#Ribeir\u00e3oA\u00e7a\u00ed", "Ζεύς ΣΊΣΥΦΟΣ", "İstanbul",
    "\u00df ﬁ ŉ ǰ", "\u3000 ideographic space", "\u0085 nel", "x\u202ey",
]


@dumper("pycompat/str_repr.json")
def str_repr() -> bytes:
    rows = [[s, repr(s), json.dumps(s, ensure_ascii=False)] for s in STR_SAMPLES]
    return case_json(rows)


def _ranges(pred) -> list[list[int]]:
    out, start = [], None
    for cp in range(0x110000 + 1):
        hit = cp < 0x110000 and not (0xD800 <= cp < 0xE000) and pred(chr(cp))
        if hit and start is None:
            start = cp
        elif not hit and start is not None:
            out.append([start, cp - 1])
            start = None
    return out


@dumper("pycompat/printable.json")
def printable() -> bytes:
    return case_json({
        "unicode_version": unicodedata.unidata_version,
        "printable_ranges": _ranges(str.isprintable),
    })


@dumper("pycompat/capitalize.tsv")
def capitalize() -> bytes:
    """Every code point whose capitalize() differs from itself, in either
    position: `cp<TAB>first<TAB>rest`, where first = c.capitalize() and
    rest = ("A" + c).capitalize()[1:], each as space-separated hex."""
    def hx(s: str) -> str:
        return " ".join(f"{ord(ch):x}" for ch in s)
    lines = [f"# unicode {unicodedata.unidata_version}; absent code points map to themselves"]
    for cp in range(0x110000):
        if 0xD800 <= cp < 0xE000:
            continue
        c = chr(cp)
        first, rest = c.capitalize(), ("A" + c).capitalize()[1:]
        if first != c or rest != c:
            lines.append(f"{cp:x}\t{hx(first)}\t{hx(rest)}")
    return ("\n".join(lines) + "\n").encode()


@dumper("pycompat/sigma.json")
def sigma() -> bytes:
    """Final-sigma context: for which neighbour c does capital sigma lower to ς."""
    return case_json({
        "before": _ranges(lambda c: ("A" + c + "Σ").capitalize()[-1] == "ς"),
        "after": _ranges(lambda c: ("AΣ" + c).capitalize()[1] == "ς"),
        "samples": [[s, s.capitalize()] for s in
                    ["ΣΑΣ", "aΣ", "aΣb", "aΣ.", "a'Σ", "a.Σ b", "ΣΣ", "aΣΣ", "a\u0301Σ",
                     "ΟΔΥΣΣΕΥΣ", "1Σ", " Σ", "aΣ\u0301", "aΣ\u0301b"]],
    })


# ---------------------------------------------------------------------------

def write_all(dest: Path) -> list[str]:
    written = []
    for rel, fn in DUMPERS.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fn())
        written.append(rel)
    return written


def check() -> int:
    with tempfile.TemporaryDirectory(prefix="talaria-golden-check-") as tmp:
        write_all(Path(tmp))
        bad = []
        for rel in DUMPERS:
            committed = GOLDEN / rel
            if not committed.exists():
                bad.append(f"missing: {rel}")
            elif not filecmp.cmp(committed, Path(tmp) / rel, shallow=False):
                bad.append(f"stale:   {rel}")
        on_disk = {str(p.relative_to(GOLDEN)) for p in GOLDEN.rglob("*") if p.is_file()}
        bad += [f"orphan:  {rel}" for rel in sorted(on_disk - set(DUMPERS))]
    for line in bad:
        print(f"[golden] {line}")
    if bad:
        print("[golden] regenerate with: python tools/golden/dump.py", file=sys.stderr)
        return 1
    print(f"[golden] {len(DUMPERS)} files match the Python oracle")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="regenerate into a temp dir and fail if testdata/golden differs")
    args = ap.parse_args()
    if args.check:
        return check()
    written = write_all(GOLDEN)
    print(f"[golden] wrote {len(written)} files under {GOLDEN.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
