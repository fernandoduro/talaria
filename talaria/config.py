"""Configuração central do pipeline. Valores validados no EP2.

Todas as constantes de render/thumbnail/transcrição ficam aqui — nada de path
absoluto ou texto específico de episódio espalhado pelo código.
"""
import os
import shutil

# ---------------------------------------------------------------------------
# Fonte (usada em render e thumbnail). Detecta DejaVu Sans Bold em locais comuns.
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    # Linux (DejaVu — usada na validação do EP2)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    # macOS — DejaVu, se instalada via `brew install --cask font-dejavu`
    "/Library/Fonts/DejaVuSans-Bold.ttf",
    os.path.expanduser("~/Library/Fonts/DejaVuSans-Bold.ttf"),
    # macOS — fontes nativas (métrica próxima da DejaVu, não exige instalar nada)
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
]


def find_font() -> str:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    # fallback: qualquer bold do fontconfig
    fc = shutil.which("fc-match")
    if fc:
        import subprocess
        try:
            out = subprocess.check_output(
                ["fc-match", "-f", "%{file}", "DejaVu Sans:bold"], text=True
            ).strip()
            if out:
                return out
        except Exception:
            pass
    raise FileNotFoundError(
        "Nenhuma fonte bold encontrada. Linux: apt install fonts-dejavu | "
        "macOS: brew install --cask font-dejavu"
    )


FONT = find_font()

# ---------------------------------------------------------------------------
# Backend de legenda — detectado em runtime.
#
# 'drawtext' é o caminho validado no EP2, mas exige ffmpeg compilado com
# libfreetype. Builds mínimas (ex.: Homebrew no macOS) não têm o filtro; nesse
# caso caímos para 'overlay': legendas rasterizadas em PNG com Pillow e
# sobrepostas com overlay+enable. Mesmo resultado visual, sem depender de libs
# externas do ffmpeg.
# ---------------------------------------------------------------------------
def has_drawtext() -> bool:
    """True se o ffmpeg deste ambiente tem o filtro drawtext."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return False
    import subprocess
    try:
        out = subprocess.run([ff, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return False
    return any(line.split()[1:2] == ["drawtext"] for line in out.splitlines() if line.strip())


# 'drawtext' | 'overlay' — sobrescreva com TALARIA_CAPTION_BACKEND para forçar.
CAPTION_BACKEND = os.environ.get(
    "TALARIA_CAPTION_BACKEND",
    "drawtext" if has_drawtext() else "overlay",
)

# ---------------------------------------------------------------------------
# Vídeo vertical (Shorts / Reels)
# ---------------------------------------------------------------------------
FRAME_W = 1080
FRAME_H = 1920

# Legenda (drawtext) — libass não desenha de forma confiável neste ambiente.
FONTSIZE = 40
SAFE_W = 980            # largura máx. da linha em px (deixa ~50px de margem/lado)
LINE_H = 58             # espaçamento vertical entre linhas
# y da base da ÚLTIMA linha. As linhas empilham para cima, então este valor
# precisa deixar espaço abaixo da faixa de vídeo para a legenda mais alta:
# com fonte 1280x720 escalada para FG_SCALE_W, a faixa termina em y=1340 e
# sobram 580px de blur. Em 1360 uma legenda de 5 linhas subia até y=1128 e
# invadia o vídeo; em 1560 ela começa em 1328 e fica inteira no blur.
BASE_Y = 1560
CAP_BORDER = 4          # contorno do texto
CAP_BOX_ALPHA = 0.55    # opacidade da caixa atrás do texto
CAP_BOX_BORDER = 12     # padding da caixa

# Enquadramento 9:16 com fundo blur
BG_BLUR_SIGMA = 28      # desfoque do fundo
FG_SCALE_W = 1350       # largura do vídeo em 1º plano (pessoas com boa presença)

# Encode
VCODEC = "libx264"
PRESET = "medium"
CRF = "20"
PIX_FMT = "yuv420p"
ACODEC = "aac"
ABITRATE = "160k"

# ---------------------------------------------------------------------------
# Transcrição
# ---------------------------------------------------------------------------
WHISPER_MODEL = "small"   # seguro p/ GPUs de 4GB; 'medium' estourou a GTX 1650 no EP2
WHISPER_LANG = "pt"

# Agrupamento de palavras -> frases (parser VTT e Whisper)
SEG_MAX_GAP = 0.7         # pausa (s) que quebra a frase
SEG_MAX_DUR = 5.0         # duração máx. (s) de um segmento
SEG_MAX_CHARS = 75        # nº máx. de caracteres antes de quebrar
SEG_END_PAD = 0.4         # padding no fim de cada segmento (s)

# ---------------------------------------------------------------------------
# Curadoria (seções 3 e 5 do prompt de cortes)
# ---------------------------------------------------------------------------
CORTE_MIN_S = 60         # duração mínima de um corte
CORTE_MAX_S = 90         # duração máxima
FALA_CONVIDADO_MIN = 0.5 # fração mínima de fala do convidado no corte

# ---------------------------------------------------------------------------
# Thumbnail (YouTube)
# ---------------------------------------------------------------------------
THUMB_W = 1280
THUMB_H = 720
THUMB_ORANGE = (240, 100, 20)
THUMB_WHITE = (255, 255, 255)
THUMB_BRIGHTNESS = 0.82
THUMB_CONTRAST = 1.08

# ---------------------------------------------------------------------------
# Post de citação para Instagram (4:5)
#
# As medidas saem do próprio template (assets/template_instagram.png), medido
# pixel a pixel: o arquivo já traz logo, aspas, filete e barra desenhados, e o
# código só escreve citação, nome e cargo por cima.
# ---------------------------------------------------------------------------
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST_TEMPLATE = os.path.join(_RAIZ, "assets", "template_instagram.png")

# ---------------------------------------------------------------------------
# Marca d'água e card de encerramento
# ---------------------------------------------------------------------------
# Validado em protótipo manual e aprovado pelo gestor (EP9, corte1) antes de
# virar padrão do pipeline.
LOGO_PATH = os.path.join(_RAIZ, "assets", "logo.png")
MARCA_DAGUA_LARGURA = 170
MARCA_DAGUA_MARGEM = 40
CARD_DURACAO_S = 3.5
CARD_FADE_S = 0.35
CARD_LOGO_LARGURA = 620
CARD_ARROBA = "@seuperfil"
CARD_COR_ARROBA = (255, 140, 66)   # laranja da marca
CARD_FUNDO = (10, 10, 10)

POST_W = 2160
POST_H = 2700

POST_MARGEM_X = 195       # margem esquerda de todo o texto
POST_LARGURA_UTIL = 1800  # largura máx. da linha da citação

# Citação. A 1ª linha começa 211px abaixo das aspas (que terminam em y=933),
# mesmo respiro do design aprovado. As linhas empilham para BAIXO.
POST_CIT_Y = 1144
POST_CIT_PASSO = 190      # distância entre inícios de linha consecutivos
POST_CIT_ALTURA = 160     # altura de uma linha de texto
POST_CIT_MAX_LINHAS = 5   # a 6ª invadiria o filete em y=2242
POST_FILETE_Y = 2242

# Rodapé (o filete já vem desenhado no template)
# Nome do programa, usado no selo da thumbnail. Trocar aqui vale para todos
# os episódios — é identidade do canal, não dado de um episódio.
NOME_PROGRAMA = "MEU PODCAST"

POST_NOME_Y = 2338
POST_CARGO_Y = 2459

POST_CIT_SIZE = 160
POST_NOME_SIZE = 62
POST_CARGO_SIZE = 38

POST_COR_CITACAO = (245, 242, 234)
POST_COR_NOME = (255, 255, 255)
POST_COR_CARGO = (154, 149, 144)

# Fonte da citação. O design usa uma geométrica (Poppins/Montserrat); quando
# não está instalada cai na Avenir Next Demi Bold, a mais próxima do sistema.
# Avenir Next é .ttc e o Demi Bold é o índice 2 — sem o índice o Pillow carrega
# o Bold, mais pesado que o design.
_POST_FONT_CANDIDATES = [
    (os.path.expanduser("~/Library/Fonts/Poppins-SemiBold.ttf"), 0),
    (os.path.expanduser("~/Library/Fonts/Montserrat-SemiBold.ttf"), 0),
    ("/Library/Fonts/Poppins-SemiBold.ttf", 0),
    ("/System/Library/Fonts/Avenir Next.ttc", 2),
]

_POST_MONO_CANDIDATES = [
    ("/System/Library/Fonts/Menlo.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Courier New.ttf", 0),
]


def _primeira_fonte(candidatas, fallback):
    """(caminho, índice) da primeira fonte existente. Índice importa em .ttc."""
    for caminho, idx in candidatas:
        if os.path.exists(caminho):
            return caminho, idx
    return fallback, 0


POST_FONT, POST_FONT_INDEX = _primeira_fonte(_POST_FONT_CANDIDATES, FONT)
POST_MONO, POST_MONO_INDEX = _primeira_fonte(_POST_MONO_CANDIDATES, FONT)

# ---------------------------------------------------------------------------
# Publicação agendada
# ---------------------------------------------------------------------------
# Fuso da publicação — explícito porque máquina em UTC perto da meia-noite
# mudaria o dia da publicação em silêncio (AP-13: data sempre com zona).
FUSO_PUBLICACAO = "America/Sao_Paulo"
