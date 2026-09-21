"""Legendas rasterizadas em PNG (backend 'overlay').

Alternativa ao drawtext para ffmpeg compilado sem libfreetype (ex.: build
mínima do Homebrew no macOS). Cada segmento de fala vira um PNG RGBA do
tamanho do frame, sobreposto com overlay+enable na janela de tempo do
segmento — mesmo resultado visual do drawtext.

O estilo (caixa preta translúcida, texto branco com contorno, posição) segue
as mesmas constantes de config usadas pelo drawtext, para as duas vias
renderizarem igual.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from . import config

_FONT = ImageFont.truetype(config.FONT, config.FONTSIZE)


def _draw_outlined(d, xy, text, fill, ow):
    """Texto com contorno. Usa stroke_width do Pillow (>=6.2) quando existe."""
    x, y = xy
    try:
        d.text((x, y), text, font=_FONT, fill=fill, anchor="ls",
               stroke_width=ow, stroke_fill=(0, 0, 0, 255))
    except TypeError:  # Pillow antigo, sem stroke_width
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx * dx + dy * dy <= ow * ow:
                    d.text((x + dx, y + dy), text, font=_FONT,
                           fill=(0, 0, 0, 255), anchor="ls")
        d.text((x, y), text, font=_FONT, fill=fill, anchor="ls")


def render_caption_png(lines: list[str], out_path: str) -> str:
    """Desenha as linhas de uma legenda num PNG transparente 1080x1920.

    Espelha o layout do drawtext: linhas centralizadas, empilhadas de baixo
    para cima a partir de BASE_Y, cada uma sobre uma caixa preta translúcida.
    """
    img = Image.new("RGBA", (config.FRAME_W, config.FRAME_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(lines)
    alpha = int(round(config.CAP_BOX_ALPHA * 255))
    pad = config.CAP_BOX_BORDER

    for li, line in enumerate(lines):
        y = config.BASE_Y - (n - 1 - li) * config.LINE_H
        w = _FONT.getlength(line)
        x = (config.FRAME_W - w) / 2
        # caixa atrás do texto (equivale a box=1:boxcolor=black@ALPHA)
        asc, desc = _FONT.getmetrics()
        d.rectangle([x - pad, y - asc - pad, x + w + pad, y + desc + pad],
                    fill=(0, 0, 0, alpha))
        _draw_outlined(d, (x, y), line, (255, 255, 255, 255), config.CAP_BORDER)

    img.save(out_path)
    return out_path


def build_overlay_graph(caption_items, base_label="comp", out_label="outv") -> str:
    """Monta a cadeia de overlays a partir de [(png_path, start, end)].

    Os PNGs entram como inputs extras do ffmpeg (índices 1..N, já que 0 é o
    vídeo). Retorna o trecho de filtergraph que encadeia os overlays.
    """
    if not caption_items:
        return f"[{base_label}]null[{out_label}]"

    parts, cur = [], base_label
    for i, (_png, rs, re_) in enumerate(caption_items, start=1):
        nxt = out_label if i == len(caption_items) else f"ov{i}"
        parts.append(
            f"[{cur}][{i}:v]overlay=0:0:enable='between(t,{rs:.3f},{re_:.3f})'[{nxt}]"
        )
        cur = nxt
    return ";".join(parts)
