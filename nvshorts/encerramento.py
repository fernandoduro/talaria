"""Card de encerramento: logo + @ ao final de cada corte, com fade-in.

O card é estático — igual em todo corte, não depende do conteúdo do vídeo.
Gerá-lo dentro do filtergraph de cada render obrigaria refazer o mesmo PNG a
cada corte; em vez disso ele é montado uma vez com Pillow e cacheado como um
`.mp4` mudo no mesmo codec/resolução do pipeline, para o `render_cut`
concatenar sem reencode (`concat demuxer -c copy`).

Formato validado em protótipo manual e aprovado pelo gestor antes de virar
padrão (EP9, corte1).
"""
from __future__ import annotations

import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from . import config, layout

_FONT_ARROBA = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_TAMANHO_ARROBA = 50


def monta_card() -> Image.Image:
    """O frame estático do card: fundo sólido, logo + @ centralizados.

    Devolve a imagem em memória — quem chama decide se grava PNG, vídeo, ou só
    inspeciona (é o que os testes fazem, sem precisar do ffmpeg cacheado).
    """
    if not os.path.exists(config.LOGO_PATH):
        raise FileNotFoundError(
            f"logo do encerramento não encontrado em {config.LOGO_PATH} — "
            f"o arquivo deveria estar versionado em assets/"
        )

    frame = Image.new("RGB", (config.FRAME_W, config.FRAME_H), config.CARD_FUNDO)

    logo = Image.open(config.LOGO_PATH).convert("RGBA")
    logo_w = config.CARD_LOGO_LARGURA
    logo_h = int(logo.height * logo_w / logo.width)
    logo_r = logo.resize((logo_w, logo_h))

    fonte = ImageFont.truetype(_FONT_ARROBA, _TAMANHO_ARROBA)
    d = ImageDraw.Draw(frame)
    bbox = d.textbbox((0, 0), config.CARD_ARROBA, font=fonte)
    arroba_h = bbox[3] - bbox[1]

    # Bloco logo + espaço + @ centralizado como uma unidade, não cada peça
    # centralizada isoladamente — senão a distância entre as duas varia com o
    # tamanho da fonte do sistema.
    espaco = 40
    bloco_h = logo_h + espaco + arroba_h
    topo = (config.FRAME_H - bloco_h) // 2

    frame.paste(logo_r, ((config.FRAME_W - logo_w) // 2, topo), logo_r)
    d.text(((config.FRAME_W - (bbox[2] - bbox[0])) // 2, topo + logo_h + espaco),
           config.CARD_ARROBA, font=fonte, fill=config.CARD_COR_ARROBA)

    return frame


def card_cacheado(project_dir: str) -> str:
    """Caminho do card em vídeo, gerando (ou regerando) quando preciso.

    Cache por mtime do logo: se `LOGO_PATH` for mais recente que o card já
    gravado, regenera. Trocar o arquivo do logo (redesign) já basta — não é
    preciso apagar nada à mão.
    """
    destino = layout.garante(layout.card_encerramento(project_dir))
    se_existe = os.path.exists(destino)
    if se_existe and os.path.getmtime(destino) >= os.path.getmtime(config.LOGO_PATH):
        return destino

    # Escreve num arquivo temporário próprio deste processo e só troca pelo
    # nome final com os.replace (atômico no mesmo filesystem) — mesmo padrão
    # do publicado.json. Sem isso, dois `render` concorrentes no mesmo
    # episódio (comum: um terminal por corte) escreveriam no mesmo
    # `frame_path`/`destino` e um corromperia o card do outro no meio do
    # ffmpeg, sem nenhum erro visível.
    # ffmpeg decide o formato de saída pela extensão — precisa terminar em
    # .mp4/.png, não pode ser um sufixo qualquer depois delas.
    raiz = destino[:-4] if destino.endswith(".mp4") else destino
    tmp_destino = f"{raiz}.{os.getpid()}.tmp.mp4"
    frame_path = f"{raiz}.{os.getpid()}.tmp.png"
    monta_card().save(frame_path)
    try:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-loop", "1", "-t", str(config.CARD_DURACAO_S), "-i", frame_path,
            "-f", "lavfi", "-t", str(config.CARD_DURACAO_S),
            "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", f"fade=in:st=0:d={config.CARD_FADE_S},format={config.PIX_FMT}",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            "-shortest", tmp_destino,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao gerar o card:\n{r.stderr[-1500:]}")
        os.replace(tmp_destino, destino)
    finally:
        if os.path.exists(frame_path):
            os.remove(frame_path)
        if os.path.exists(tmp_destino):
            os.remove(tmp_destino)

    return destino
