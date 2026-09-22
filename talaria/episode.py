"""Episode metadata — the source of truth for proper nouns and numbering.

Do not invent: automatic transcription gets proper nouns wrong. These fields
are explicit manager input, never inferred from the audio.
"""
from __future__ import annotations

import json
import os

from . import layout

REQUIRED_FIELDS = ["season", "episode", "company", "city", "uf", "guests"]

# The subset that must also carry a value. `guests` may be an empty list:
# a hosts-only episode is a real case.
# `company` is excluded here and checked separately, because in a hosts-only
# episode it may legitimately be empty (see _validate_company_or_topic).
REQUIRED_NONEMPTY_FIELDS = [c for c in REQUIRED_FIELDS
                                   if c not in ("guests", "company")]

FILE_NAME = "episode.json"


def template() -> dict:
    """Skeleton for the manager to fill in."""
    return {
        "season": 0,
        "episode": 0,
        "company": "",
        "city": "",
        "uf": "SP",
        "guests": [{"name": "", "role": "", "linkedin": ""}],
        "topics": [],  # optional — hashtag fallback when there is no company
        # URL of the full episode on YouTube, filled in when the long video
        # goes up. Enters the Shorts description as a call to the episode.
        # Optional: the clip is rendered before the long one is live.
        "youtube_url": "",
    }


def _validate_company_or_topic(ep: dict) -> None:
    """Requires `company`, except in a hosts-only episode.

    With no external guest there is no company, and it is the topic that carries
    thumbnail line 1 and the hashtag — so the topic becomes required exactly there.
    """
    has_guest = bool(ep.get("guests"))
    has_company = bool(str(ep.get("company") or "").strip())
    if has_company:
        return
    if has_guest:
        raise ValueError(
            "episode.json não preenchido — campos em branco: company "
            "(obrigatória quando há convidado externo)"
        )
    if not (ep.get("topics") or []):
        raise ValueError(
            "episode.json: episódio sem convidado externo e sem company "
            "precisa de ao menos um tema em 'topics' — é dele que saem a "
            "linha 1 da thumb e a hashtag do tema"
        )


def youtube_url(project_dir: str) -> str:
    """The full episode URL, or empty when there is none.

    It deliberately does not go through `load`: this field is optional and
    serves a caption, which cannot break over a missing or incomplete
    episode.json. `load` validates the whole episode and ABORTS — the right
    contract for proper nouns, the wrong one for an optional block of text.
    """
    path = layout.episode(project_dir)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            ep = json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return ""
    value = ep.get("youtube_url")
    return value.strip() if isinstance(value, str) else ""


def load(project_dir: str) -> dict:
    """Reads and validates the project's episode.json."""
    path = layout.episode(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py ingest' para criar o template."
        )
    with open(path, encoding="utf-8") as f:
        ep = json.load(f)
    missing = [c for c in REQUIRED_FIELDS if c not in ep]
    if missing:
        raise ValueError(f"episode.json incompleto — falta: {', '.join(missing)}")

    # `guests` is deliberately outside the empty check: the materials prompt
    # allows for "an episode with no external guest, hosts only", so an empty
    # list is legitimate input, not a forgotten field.
    empty = [c for c in REQUIRED_NONEMPTY_FIELDS
              if ep[c] == "" or ep[c] == [] or ep[c] == 0]
    if empty:
        raise ValueError(
            f"episode.json não preenchido — campos em branco: {', '.join(empty)}"
        )

    _validate_company_or_topic(ep)

    for field in ("season", "episode"):
        try:
            ep[field] = int(ep[field])
        except (TypeError, ValueError):
            raise ValueError(
                f"episode.json: '{field}' deve ser número inteiro, "
                f"recebido {ep[field]!r}"
            ) from None
    return ep


def save(project_dir: str, data: dict) -> str:
    path = layout.ensure_dir(layout.episode(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def code(ep: dict) -> str:
    """T[N]E[NN] — the episode number is always two digits (T2E07, never T2E7)."""
    return f"T{ep['season']}E{int(ep['episode']):02d}"
