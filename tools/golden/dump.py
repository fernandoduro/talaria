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
import re
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
# G1: Unicode properties behind Python's str methods and re semantics
# ---------------------------------------------------------------------------

def _all_chars():
    for cp in range(0x110000):
        if not 0xD800 <= cp < 0xE000:
            yield cp


@dumper("pycompat/unicode.json")
def unicode_props() -> bytes:
    """What `re` and `str` treat as space, word, digit and case, per code point.

    re's \\s, \\w and \\d on a str pattern are str.isspace(), str.isalnum() or
    "_", and str.isdecimal(); IGNORECASE compares _sre.unicode_tolower() and
    adds re._casefix._EXTRA_CASES. str.splitlines() has its own separator set.
    """
    import _sre
    from re import _casefix
    space, word, digit = re.compile(r"\s"), re.compile(r"\w"), re.compile(r"\d")
    return case_json({
        "unicode_version": unicodedata.unidata_version,
        "space": _ranges(lambda c: bool(space.match(c))),
        "isspace": _ranges(str.isspace),
        "word": _ranges(lambda c: bool(word.match(c))),
        "decimal": [[cp, int(chr(cp))] for cp in _all_chars() if digit.match(chr(cp))],
        "sre_lower": [[cp, _sre.unicode_tolower(cp)] for cp in _all_chars()
                      if _sre.unicode_tolower(cp) != cp],
        "sre_cased": _ranges(lambda c: _sre.unicode_iscased(ord(c))),
        "lower_full": [[cp, chr(cp).lower()] for cp in _all_chars()
                       if chr(cp).lower() != chr(_sre.unicode_tolower(cp))],
        "extra_cases": [[k, list(v)] for k, v in sorted(_casefix._EXTRA_CASES.items())],
        "line_breaks": [cp for cp in _all_chars()
                        if ("a" + chr(cp) + "b").splitlines() == ["a", "b"]],
        "mn": _ranges(lambda c: unicodedata.category(c) == "Mn"),
        "nfd": [[cp, unicodedata.normalize("NFD", chr(cp))] for cp in _all_chars()
                if unicodedata.normalize("NFD", chr(cp)) != chr(cp)],
    })


@dumper("pycompat/re_ignorecase.json")
def re_ignorecase() -> bytes:
    """For every cased character p, the characters re.I lets match it.

    Candidates are every character related to p by lower(), upper(),
    casefold() or the extra-cases table; the regex engine itself decides.
    """
    import _sre
    from re import _casefix
    by = {}
    for cp in _all_chars():
        c = chr(cp)
        for key in (("l", _sre.unicode_tolower(cp)), ("u", c.upper()), ("f", c.casefold())):
            by.setdefault(key, []).append(cp)
    rows = []
    for p in _all_chars():
        if not _sre.unicode_iscased(p):
            continue
        c = chr(p)
        lo = _sre.unicode_tolower(p)
        cand = set(by[("l", lo)]) | set(by[("u", c.upper())]) | set(by[("f", c.casefold())])
        for x in _casefix._EXTRA_CASES.get(lo, ()):
            cand |= set(by.get(("l", x), ())) | {x}
        rx = re.compile(re.escape(c), re.IGNORECASE)
        rows.append([p, sorted(x for x in cand if rx.fullmatch(chr(x)))])
    return case_json(rows)


ISO_DATES = [
    "2026-08-24", "20260824", "2026-W35", "2026W35", "2026-W35-1", "2026W351",
    "2026-W35-7", "2026-W35-0", "2026-W35-8", "2026-W00", "2026-W53", "2020-W53",
    "2015-W53-7", "2026-W35-", "2026-W351", "2026W35-1", "2026082499", "2026-08-2x",
    "+026-08-24", "2026-8-24 ", "2026-08-24 ", " 2026-08-24", "2026-02-30", "2024-02-29",
    "2023-02-29", "0000-01-01", "0001-01-01", "9999-12-31", "9999-W52-5", "9999-W52-6",
    "0001-W01-1", "0001-W01", "2026-13-01", "2026-00-10", "2026-12-00", "2026-12-32",
    "24/08/2026", "", "2026", "2026-08", "202608", "2026-0824", "202608-24",
    "2026-08-24T00", "2026/08/24", "\u0662\u0660\u0662\u0666-08-24", "2026-08-\u0662\u0664",
    "2026\u201108\u201124", "2026-08-24\n", "2026-W5a", "abcd-ef-gh", "2026-W35-1x",
    "1999-W52-7", "2004-W53-7", "2026--8-24", "2026-+8-24", "2026-08--4",
]


@dumper("pycompat/isodate.json")
def isodate() -> bytes:
    import datetime as dt
    rows = []
    for s in ISO_DATES:
        try:
            rows.append([s, dt.date.fromisoformat(s).isoformat()])
        except ValueError:
            rows.append([s, None])
    return case_json(rows)


@dumper("pycompat/strings.json")
def str_methods() -> bytes:
    samples = STR_SAMPLES + [
        "  padded\t\n", "\x1c\x1dfile sep\x1e\x1f", "\u00a0nbsp\u3000", "\u200bzw\u200b",
        "a\nb\r\nc\rd\x0be\x0cf\x1cg\x1dh\x1ei\x85j\u2028k\u2029l", "trail\n", "\n\nx\n\n",
        "one  two\tthree\u2003four", "", "   ", "x\r", "\r\n", "...dots. ", ". .",
        "ΣΑΣ σ Σ", "İSTANBUL", "MAŁOPOLSKA",
    ]
    return case_json([[s, s.strip(), s.split(), s.splitlines(), s.lower(), s.strip(". ")]
                      for s in samples])


# ---------------------------------------------------------------------------
# G1: replay each original test's real calls against Go, with filesystem IO
# ---------------------------------------------------------------------------

@dumper("g1/replay.json")
def g1_replay(extra: bool = False) -> bytes:
    import copy
    import datetime as dt
    import types
    import unittest
    from unittest import mock
    from talaria import (brief, caption, environment, hashtags, post_instagram,
                         published, schedule, texts, utils, vtt_parse, render)

    modules = [] if extra else ["utils", "txt_parse", "layout", "episode", "curation", "schedule",
               "published", "hashtags", "texts", "caption", "brief", "environment"]
    api = {
        utils: "srt_ts mmss strip_markup clean_caption fix_proper_nouns group_words_into_segments",
        txt_parse: "parse_txt regroup_into_sentences resolve_speakers",
        layout: "ensure_dir episode video transcript transcript_txt source_dir curation moments texts posts schedule published brief thumbnail end_card_mp4 episode_txt platform posts_png migrate",
        episode: "template load save code youtube_url",
        curation: "new_state overlaps burned_spans is_burned slots_left load save has_hedged_number segments_in_clip guest_speech_fraction sentence_ends validate_clip attribution_trustworthy host_opening clip_warnings approve reject composition missing_kinds reasons is_closed to_moments save_moments",
        schedule: "today platforms_of date_of moments load pending",
        published: "load is_published record",
        hashtags: "slug build format_line",
        texts: "load save thumb_args build_kwargs",
        caption: "validate episode_line compose compose_episode txt_path write",
        brief: "readable_transcript readable_metadata fill_template readable_curation build clip_speech readable_clips build_posts",
        environment: "load",
        post_instagram: "load file_slug",
        vtt_parse: "parse_vtt",
        transcribe: "_write_outputs",
        render: "_trim_text",
    }
    rows, calls, roots = [], [], []
    depth = 0
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*a, **kw):
        p = real_mkdtemp(*a, **kw)
        roots.append(p)
        return p

    def normalize(v):
        if isinstance(v, str):
            for i, root in sorted(enumerate(roots), key=lambda x: -len(x[1])):
                v = v.replace(root, f"<TMP{i}>")
            return v.replace(str(ROOT), "<ROOT>")
        if isinstance(v, dt.date):
            return v.isoformat()
        if isinstance(v, (list, tuple)):
            return [normalize(x) for x in v]
        if isinstance(v, dict):
            return {normalize(k): normalize(x) for k, x in v.items()}
        return v

    def snapshot():
        out = {}
        for i, root in enumerate(roots):
            tree = {}
            for p in sorted(Path(root).rglob("*")):
                rel = str(p.relative_to(root))
                tree[rel] = None if p.is_dir() else normalize(p.read_bytes().decode("utf-8"))
            out[f"<TMP{i}>"] = tree
        return out

    def wrapper(mod, name, fn):
        def call(*args, **kwargs):
            nonlocal depth
            if depth:
                return fn(*args, **kwargs)
            before = snapshot()
            inp = copy.deepcopy(normalize([args, kwargs]))
            env = {}
            if mod is environment and args and os.path.isfile(args[0]):
                for line in Path(args[0]).read_text().splitlines():
                    if "=" in line:
                        key = line.removeprefix("export ").split("=", 1)[0].strip()
                        if key and not key.startswith("#"):
                            env[key] = os.environ.get(key)
            buf, err, result = io.StringIO(), None, None
            depth += 1
            try:
                with contextlib.redirect_stdout(buf):
                    result = fn(*args, **kwargs)
            except BaseException as e:
                err = [type(e).__name__, str(e)]
                raise
            finally:
                depth -= 1
                row = {"op": f"{mod.__name__.split('.')[-1]}.{name}",
                       "input": inp, "result": normalize(result), "error": normalize(err),
                       "args_after": normalize([args, kwargs]), "stdout": normalize(buf.getvalue()),
                       "before": before, "after": snapshot()}
                if mod is environment:
                    row["env_before"] = env
                    row["env_after"] = {k: os.environ.get(k) for k in env}
                calls.append(row)
                print(buf.getvalue(), end="")
            return result
        return call

    class FrozenDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 12, 34, 56, tzinfo=tz)

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(tempfile, "mkdtemp", mkdtemp))
        stack.enter_context(mock.patch.object(published, "dt", types.SimpleNamespace(datetime=FrozenDatetime)))
        # `today` has no original G1 test, but a fixed clock keeps replay deterministic.
        stack.enter_context(mock.patch.object(schedule, "today", lambda: dt.date(2026, 11, 18)))
        for mod, names in api.items():
            for name in names.split():
                stack.enter_context(mock.patch.object(mod, name, wrapper(mod, name, getattr(mod, name))))
        for modname in modules:
            suite = unittest.defaultTestLoader.loadTestsFromName(f"tests.test_{modname}")
            def flatten(s):
                for t in s:
                    if isinstance(t, unittest.TestSuite):
                        yield from flatten(t)
                    else:
                        yield t
            for test in flatten(suite):
                calls, roots = [], []
                result = unittest.TestResult()
                with contextlib.redirect_stdout(io.StringIO()):
                    test.run(result)
                if result.errors or result.failures:
                    raise RuntimeError(f"oracle test failed: {test.id()}: {result.errors + result.failures}")
                name = test.id().removeprefix("tests.")
                # These three tests inspect constants or a signature, not a function
                # call. Pin the inspected API in a small direct trace operation.
                if name.endswith("test_required_fields_do_not_shrink"):
                    calls.append({"op": "episode.required_fields", "result": episode.REQUIRED_FIELDS})
                if name.endswith("test_own_company_phrases_are_detected") or name.endswith("test_bare_first_person_plural_is_not_a_marker") or name.endswith("test_third_person_is_not_detected"):
                    # The regex was not patched inside curation: its callers need the
                    # real Match, not a bool. These mirror the direct regex assertions.
                    samples = {
                        "test_own_company_phrases_are_detected": ["our team shipped it", "our first hire", "my co-founder left", "we set up our own studio"],
                        "test_bare_first_person_plural_is_not_a_marker": ["tell us how it started", "we are recording another episode", "today we are going to talk about it"],
                        "test_third_person_is_not_detected": ["the company hired three people"],
                    }[name.split(".")[-1]]
                    for s in samples:
                        calls.append({"op": "curation.has_first_person", "input": [[s], {}],
                                      "result": bool(curation.RE_FIRST_PERSON.search(s)), "args_after": [[s], {}]})
                if not calls:
                    raise RuntimeError(f"no observable calls for {name}")
                rows.append({"name": name, "calls": copy.deepcopy(calls)})
                # Tests use mkdtemp without cleanup; the generator must not leak them.
                import shutil
                for root in roots:
                    shutil.rmtree(root, ignore_errors=True)
        if extra:
            calls, roots = [], []
            def capture(name, fn, *a, **kw):
                nonlocal calls
                calls = []
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        fn(*a, **kw)
                    except Exception:
                        pass  # The observed exception is itself an expectation.
                if not calls:
                    raise RuntimeError(f"no call for {name}")
                rows.append({"name": name, "calls": copy.deepcopy(calls)})

            corpus = STR_SAMPLES + [
                "we we shipped it", "a a a a a a a a", "like, we like tools, like Slack, you know.",
                "you know, Gonna ship it. I mean, we wanna try. Like, it works, like!",
                "\u0130 i", "i \u0131", "\u03c3 \u03c2", "\u00b5 \u03bc", "\u017f s", "\u00b2 \u00b2",
                "e\u0301 e\u0301", "a\u203fa a\u203fa", "\x1cuh,\x1fgonna\u00a0ship\u3000it",
                "[\x1cMUSIC\x1f] [ important ] &lt;x&gt;&amp; [MU\u017fIC]",
                "Uh\u0301, Gonna\u0301 ship", "like\u0301, wanna go", "\u0131 mean, it works",
                "we  we   WE we", "gONNA WANNA GOTTA KINDA", "ahead umbrella error yeah",
                "../outside/clip", "..", " ._-- ", "foo\\bar.v2", "Ribeir\u00e3o A\u00e7a\u00ed",
            ]
            for i, s in enumerate(corpus):
                for mod, fn in ((utils, "clean_caption"), (utils, "strip_markup"),
                                (hashtags, "slug"), (post_instagram, "file_slug")):
                    capture(f"{mod.__name__.split('.')[-1]}.{fn}/{i}", getattr(mod, fn), s)
            names = ["Kestril", "Zarvik", "Delta", "Ribeir\u00e3oA\u00e7a\u00ed", "Ikea", "Stri\u00dfe", "E\u0301mark"]
            variants = ["Cestril Kestryl Keztril kestril Kestril", "zarvic zarvik", "the delta of the risk",
                        "ribeir\u00e3oa\u00e7a\u00ed Ribeir\u00e3oA\u00e7a\u00ed", "\u0130KEA \u0131kea", "stri\u00dfe STRI\u00dfE", "e\u0301mark E\u0301marc"]
            for i, (s, name) in enumerate(zip(variants, names)):
                capture(f"fix_proper_nouns/{i}", utils.fix_proper_nouns, s, [name])
            for i, name in enumerate([r"X\g<", r"X\g<>", r"X\g<foo>", r"X\g<-1>", r"X\g<1>",
                                      r"A\g<0>b", r"A\g<00>b", r"A\101b", r"A\000b", r"A\777b",
                                      r"A\9b", r"A\99b", r"A\999b", r"A\nb", r"A\&b", r"A\\b",
                                      r"A\qb", r"A\g", "A\\q\nb", "\u0578\u0605A0"]):
                capture(f"fix_proper_nouns/template/{i}", utils.fix_proper_nouns,
                        name if name[-1].isalnum() or name[-1] == "_" else name + "0", [name])
            for i, s in enumerate(["About \u0663 users", "we talked about 3 things", "roughly 1. about 2",
                                   "maybe " + "\u00e3" * 40 + "7", "\u00e3about 3", "our fir\u017ft hire"]):
                capture(f"hedged/{i}", curation.has_hedged_number, s)
            for i, seconds in enumerate([0.0, 1.2345, -0.0005, -1.5, 59.9995, 3599.9995, 3723.2]):
                capture(f"srt_ts/{i}", utils.srt_ts, seconds)
                capture(f"mmss/{i}", utils.mmss, seconds)
            for i, words in enumerate([
                [], [(0.0, "[music]")], [(0.0, "Hello"), (.7, "there"), (1.401, "world!")],
                [(0.0, "\u00e3" * 76), (.1, "next")], [(0.0, "\u00e3" * 75), (.1, "next")],
                [(0.0, "one"), (5.0, "two"), (5.001, "three")],
                [(i * .2, w) for i, w in enumerate("we gonna ship it. [laughter] then go!".split())],
            ]):
                capture(f"group_words/{i}", utils.group_words_into_segments, words)
            for i, (s, a, b) in enumerate([
                ("one two three four five", .5, .5), ("one two three. Four five.", 0, .4),
                ("\u00e3\u00e7a\u00ed\u00a0one\u3000two three.", .2, .7), ("one two. Three four five.", 0, .8),
                ("one two three.", 1, 1), (" ", .5, .6), (" one  two ", 0, 1),
            ]):
                capture(f"trim_text/{i}", render._trim_text, s, a, b)
            for i, (d, h, u) in enumerate([(None, None, None), ("desc", "#Tags", " https://youtu.be/x "),
                                          (" \u00e3\u00e7\x1c", "#Gda\u0144sk", ""), ("", "", "u")]):
                capture(f"compose/{i}", caption.compose, d, h, u)
            pd = mkdtemp(prefix="talaria-g1-extra-")
            ep = {"season": 2, "episode": 7, "company": "Ribeir\u00e3oA\u00e7a\u00ed", "city": "Gda\u0144sk",
                  "uf": "SP", "guests": [{"name": "Teresa", "role": "CTO", "linkedin": "https://x"}],
                  "topics": ["biotech", "B2B to B2C"], "extra": {"\u00e7": 2.0}}
            capture("episode.save", episode.save, pd, ep)
            capture("episode.load", episode.load, pd)
            for i, v in enumerate([2.7, "2", True, False, None]):
                data = dict(ep, season=v)
                Path(layout.episode(pd)).write_text(json.dumps(data), encoding="utf-8")
                capture(f"episode.coercion/{i}", episode.load, pd)
            episode.save(pd, ep)
            segs = txt_parse.parse_txt(str(FIXTURES / "example.txt"))
            capture("parse_txt/example", txt_parse.parse_txt, str(FIXTURES / "example.txt"))
            capture("parse_txt/duration", txt_parse.parse_txt, str(FIXTURES / "example.txt"), 3750.4)
            capture("transcript.outputs", transcribe._write_outputs, segs, pd)
            capture("texts.thumb_args", texts.thumb_args, pd)
            capture("texts.save", texts.save, pd, {"thumb": {"l1": "CUSTOM", "extra": 3.0}, "hashtags": "#Tags"})
            capture("texts.override", texts.thumb_args, pd)
            state = _curation_state()
            capture("curation.save", curation.save, pd, state)
            capture("curation.moments", curation.save_moments, pd, state)
            capture("brief.metadata", brief.readable_metadata, pd)
            capture("brief.curation", brief.readable_curation, state)
            capture("brief.materials", brief.build, pd, "materials")
            capture("brief.clips", brief.build, pd, "clips")
            capture("brief.posts", brief.build_posts, pd, state["approved"])
            for i, span in enumerate([(0., 65.), (10., 75.), (100., 170.), (3723., 3790.)]):
                capture(f"warnings/{i}", curation.clip_warnings, span, segs)
                capture(f"validate/{i}", curation.validate_clip, span, segs, state)
                capture(f"guest/{i}", curation.guest_speech_fraction, span, segs)
                capture(f"host/{i}", curation.host_opening, span, segs)
            multibyte = [{"start": 0., "end": 80., "text": "\u00e3" * 30 + ". " + "\u00e7" * 100 + "!"}]
            capture("sentence_ends/unicode", curation.sentence_ends, multibyte, 0., 60., 90.)
            # Representative YouTube rolling captions: consolidated line ignored,
            # new words carry inline timestamps, and cues without <c> ignored.
            vtt = Path(pd) / "rolling.vtt"
            vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nold repeated text\nHello <00:00:01.200><c>world.</c>\n\n00:00:03.000 --> 00:00:05.000\nHello world.\n<c>We</c><00:00:03.200><c>ship &amp; learn!</c>\n\n00:00:05.000 --> 00:00:07.000\nplain cue ignored\n", encoding="utf-8")
            capture("vtt/rolling", vtt_parse.parse_vtt, str(vtt))
            capture("posts/missing", post_instagram.load, pd)
            Path(layout.ensure_dir(layout.posts(pd))).write_text('{"posts": [{"slug": "q", "cards": ["quote"]}]}')
            capture("posts/load", post_instagram.load, pd)
            Path(layout.ensure_dir(layout.schedule(pd))).write_text(json.dumps({"schedule": [
                {"date": "2026-11-17", "kind": "clip", "slug": state["approved"][0]["slug"]},
                {"date": "2026-11-19", "kind": "post", "slug": "q"}]}))
            capture("schedule/pending", schedule.pending, pd, dt.date(2026, 11, 18))
            capture("schedule/no-platforms", schedule.pending, pd, dt.date(2026, 11, 18), platforms=[])
            capture("published/record", published.record, pd, "youtube_shorts", state["approved"][0]["slug"], "id", "u")
            capture("schedule/retry", schedule.pending, pd, dt.date(2026, 11, 18))
            # Pin the known order-dependent approve() quirk rather than fixing it.
            s = curation.new_state()
            curation.approve(s, {"slug": "a", "start": 0., "end": 70.})
            curation.approve(s, {"slug": "b", "start": 200., "end": 270.})
            capture("approve/early-same-slug", curation.approve, s, {"slug": "a", "start": 210., "end": 280.})
            import shutil
            for root in roots:
                shutil.rmtree(root, ignore_errors=True)
    return case_json(rows)


@dumper("g1/extra.json")
def g1_extra() -> bytes:
    return g1_replay(extra=True)


def write_all(dest: Path, only: str = "") -> list[str]:
    written = []
    for rel, fn in DUMPERS.items():
        if not rel.startswith(only):
            continue
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
    ap.add_argument("--only", default="", metavar="PREFIX",
                    help="write only the golden files whose path starts with PREFIX")
    args = ap.parse_args()
    if args.check:
        return check()
    written = write_all(GOLDEN, args.only)
    print(f"[golden] wrote {len(written)} files under {GOLDEN.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
