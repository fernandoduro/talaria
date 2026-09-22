"""Loads `.env` into the process environment.

The publishing modules read credentials from `os.environ`, but the person who
writes `.env` is the manager in an editor — without this bridge the file is
filled in and `publish` complains about an undefined variable, the most
confusing error possible (the answer is in the file open on screen).

It is a minimal parser on purpose: `.env` holds a dozen hand-written
`KEY=value` lines. It does not interpolate `${OTHER}`, does not expand `~` and
does not read multi-line values — each of those would be one more rule for the
manager to remember when pasting a token, and none of them showed up in use.
"""
from __future__ import annotations

import os

# The repo root, two levels above this file (talaria/environment.py).
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      ".env")


def _clean_value(value: str) -> str:
    """Strips surrounding whitespace and one pair of quotes, if present.

    Pasting from a console often brings the quotes along, and a quoted token
    fails at the API with "invalid credential" — an error that does not point
    at the quote pair as the cause.
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def load(path: str = None) -> int:
    """Puts whatever is in `.env` into the environment. Returns how many entered.

    What is already in the environment WINS over the file: `IG_PAGE_TOKEN=x
    python run.py` has to override, which is how another credential gets tested
    without editing anything.

    A missing file is not an error — someone who only renders clips never made
    one. A variable declared empty does not enter either: "not configured" is
    the honest state, and an empty string would let the credential check pass
    for the API to refuse later, with a worse message.
    """
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return 0

    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)   # '=' in the value stays in the value
            key = key.strip()
            value = _clean_value(value)
            if not key or not value or key in os.environ:
                continue
            os.environ[key] = value
            added += 1
    return added
