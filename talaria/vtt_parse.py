"""Parser correto do VTT de rolagem do YouTube.

Cada cue tem 2 linhas de texto: a consolidada (repetição, sem tags) e a nova
(tags <c> de timing por palavra). Usamos SÓ a linha com <c>: zero duplicação.
"""
from __future__ import annotations

from . import utils


def parse_vtt(path: str) -> list[dict]:
    """Lê o VTT e retorna segmentos [{start, end, text}]."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    words = []  # (tempo, palavra)
    i = 0
    while i < len(lines):
        m = utils.RE_CUE.match(lines[i])
        if not m:
            i += 1
            continue
        cue_start = utils.vtt_ts_to_sec(m.group(1))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() != "" and not utils.RE_CUE.match(lines[i]):
            buf.append(lines[i])
            i += 1
        # a linha "nova" é a que contém tags <c>
        newline = next((l for l in buf if "<c>" in l), None)
        if newline is None:
            continue
        # texto antes da 1ª tag inline pertence ao início do cue
        import re
        head = re.sub(r"<[^>]+>", "", utils.RE_INLINE.split(newline)[0]).strip()
        if head:
            for w in head.split():
                words.append((cue_start, w))
        for ts, txt in utils.RE_INLINE.findall(newline):
            t = utils.vtt_ts_to_sec(ts)
            for w in re.sub(r"<[^>]+>", "", txt).strip().split():
                words.append((t, w))

    return utils.group_words_into_segments(words)
