"""Gera a thumbnail do YouTube (1280x720) a partir de um frame do vídeo.

Todo o texto vem de parâmetros (nada hardcoded de episódio). Composição:
frame escurecido + gradiente na base + selo, chamada em destaque e créditos.
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from . import config


def sugere_frames(momentos: list, n: int = 5) -> list:
    """Instantes candidatos a frame de thumbnail, tirados dos cortes aprovados.

    A escolha final é visual — expressão, mãos, enquadramento — e fica com o
    gestor. O que dá para automatizar é ONDE procurar: dentro de um corte
    aprovado o convidado está falando com energia, ao contrário de um instante
    sorteado no episódio, que costuma pegar pausa ou o host.

    Devolve o meio de cada corte, que evita as bordas (entrada e saída de fala).
    """
    meios = sorted((m["start"] + m["end"]) / 2 for m in momentos or [])
    if len(meios) <= n:
        return [round(t, 1) for t in meios]
    passo = len(meios) / n
    return [round(meios[int(i * passo)], 1) for i in range(n)]


def extract_frame(video_path: str, at_seconds: float, out_path: str):
    """Extrai um frame 16:9 do vídeo no tempo indicado."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(at_seconds), "-i", video_path,
         "-frames:v", "1", "-update", "1", out_path],
        check=True, capture_output=True,
    )


def _font(sz):
    return ImageFont.truetype(config.FONT, sz)


def _outlined(draw, xy, text, fnt, fill, ow=4, anchor="la"):
    x, y = xy
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx * dx + dy * dy <= ow * ow:
                draw.text((x + dx, y + dy), text, font=fnt, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def build_thumbnail(frame_path, out_path, *, selo, chamada_l1, chamada_l2,
                    creditos="", subtitulo=""):
    """Monta a thumbnail. Textos totalmente parametrizados.

    selo:        faixa laranja superior esquerda (ex.: 'MEU PODCAST • T2E02')
    chamada_l1:  1ª linha grande (branca)
    chamada_l2:  2ª linha grande (laranja)
    creditos:    canto superior direito (ex.: nomes dos convidados)
    subtitulo:   abaixo dos créditos
    """
    W, H = config.THUMB_W, config.THUMB_H
    img = Image.open(frame_path).convert("RGB").resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(config.THUMB_BRIGHTNESS)
    img = ImageEnhance.Contrast(img).enhance(config.THUMB_CONTRAST)

    # gradiente escuro na base p/ destacar a chamada
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        v = int(230 * max(0, (y - H * 0.45) / (H * 0.55)))
        grad.putpixel((0, y), min(255, v))
    grad = grad.resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, grad)

    d = ImageDraw.Draw(img)

    # selo (faixa laranja)
    if selo:
        ftag = _font(30)
        tb = d.textbbox((0, 0), selo, font=ftag)
        pad = 16
        d.rectangle([28, 30, 28 + (tb[2] - tb[0]) + pad * 2, 30 + (tb[3] - tb[1]) + pad * 2],
                    fill=config.THUMB_ORANGE)
        d.text((28 + pad, 30 + pad - tb[1]), selo, font=ftag, fill=config.THUMB_WHITE)

    # chamada principal (2 linhas na base)
    if chamada_l1:
        _outlined(d, (40, H - 210), chamada_l1, _font(72), config.THUMB_WHITE, ow=5)
    if chamada_l2:
        _outlined(d, (40, H - 120), chamada_l2, _font(56), config.THUMB_ORANGE, ow=5)

    # créditos (canto superior direito)
    if creditos:
        _outlined(d, (W - 40, 40), creditos, _font(28), config.THUMB_WHITE, ow=3, anchor="ra")
    if subtitulo:
        _outlined(d, (W - 40, 78), subtitulo, _font(24), (210, 210, 210), ow=3, anchor="ra")

    img.save(out_path, quality=92)
    print(f"[thumb] salva -> {out_path}")
