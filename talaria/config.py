"""Configuração central do pipeline.

Todas as constantes de render/thumbnail/transcrição ficam aqui — nada de path
absoluto ou texto específico de episódio espalhado pelo código.
"""
import os
import shutil

# ---------------------------------------------------------------------------
# Fontes — versionadas em assets/fonts/.
#
# O texto é queimado no vídeo e rasterizado nos PNG, então a fonte decide o
# resultado published. O fc-match substitui em silêncio: pede-se Poppins e vem
# Noto Sans, e o layout sai errado sem nenhum error. Arquivo no repositório =
# mesmo render em qualquer máquina, e falta de arquivo aborta na importação.
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTS_DIR = os.path.join(_ROOT, "assets", "fonts")


def _bundled_font(name: str) -> str:
    path = os.path.join(_FONTS_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"fonte {name} não encontrada em assets/fonts — o arquivo é "
            f"versionado; restaure com 'git checkout assets/fonts/{name}'."
        )
    return path


FONT = _bundled_font("DejaVuSans-Bold.ttf")

# ---------------------------------------------------------------------------
# Backend de legenda — detectado em runtime.
#
# 'drawtext' é o path padrão, mas exige ffmpeg compilado com
# libfreetype. Builds mínimas (ex.: Homebrew no macOS) não têm o filtro; nesse
# caso caímos para 'overlay': legendas rasterizadas em PNG com Pillow e
# sobrepostas com overlay+enable. Mesmo resultado visual, sem depender de libs
# externas do ffmpeg.
# ---------------------------------------------------------------------------
def has_drawtext() -> bool:
    """True se o ffmpeg deste environment tem o filtro drawtext."""
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

# Legenda (drawtext) — libass não desenha de forma confiável neste environment.
FONTSIZE = 40
SAFE_W = 980            # largura máx. da linha em px (deixa ~50px de margem/lado)
LINE_H = 58             # espaçamento vertical entre lines
# y da base da ÚLTIMA linha. As lines empilham para cima, então este valor
# precisa deixar espaço abaixo da span de vídeo para a legenda mais alta:
# com fonte 1280x720 escalada para FG_SCALE_W, a span termina em y=1340 e
# sobram 580px de blur. Em 1360 uma legenda de 5 lines subia até y=1128 e
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
WHISPER_MODEL = "small"   # seguro p/ GPUs de 4GB; 'medium' estourou uma GTX 1650
WHISPER_LANG = "pt"

# Agrupamento de words -> frases (parser VTT e Whisper)
SEG_MAX_GAP = 0.7         # pausa (s) que quebra a frase
SEG_MAX_DUR = 5.0         # duração máx. (s) de um segmento
SEG_MAX_CHARS = 75        # nº máx. de caracteres antes de quebrar
SEG_END_PAD = 0.4         # padding no end de cada segmento (s)

# ---------------------------------------------------------------------------
# Curadoria
# ---------------------------------------------------------------------------
CLIP_MIN_S = 60         # duração mínima de um clip
CLIP_MAX_S = 90         # duração máxima
GUEST_SPEECH_MIN = 0.5 # fração mínima de fala do convidado no clip

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
# pixel a pixel. O placeholder traz gradiente, filete e barra; logo e aspas
# são do canal. O código write citação, name e role por cima.
# ---------------------------------------------------------------------------
POST_TEMPLATE = os.path.join(_ROOT, "assets", "template_instagram.png")

# ---------------------------------------------------------------------------
# Marca d'água e card de end_card
# ---------------------------------------------------------------------------
LOGO_PATH = os.path.join(_ROOT, "assets", "logo.png")
WATERMARK_W = 170
WATERMARK_MARGIN = 40
CARD_DURATION_S = 3.5
CARD_FADE_S = 0.35
CARD_LOGO_W = 620
CARD_HANDLE = "@seuperfil"
CARD_HANDLE_COLOR = (255, 140, 66)   # laranja
CARD_BG = (10, 10, 10)

POST_W = 2160
POST_H = 2700

POST_MARGIN_X = 195       # margem esquerda de todo o texto
POST_TEXT_W = 1800  # largura máx. da linha da citação

# Citação. As lines empilham para BAIXO a partir de POST_QUOTE_Y, herdado do
# layout original: o placeholder não desenha nada nessa altura para conferir.
POST_QUOTE_Y = 1144
POST_QUOTE_STEP = 190      # distância entre inícios de linha consecutivos
POST_QUOTE_LINE_H = 160     # altura de uma linha de texto
POST_QUOTE_MAX_LINES = 5   # a 6ª invadiria o filete em y=2242
POST_RULE_Y = 2242

# Rodapé (o filete já vem desenhado no template)
# Nome do programa, usado no badge da thumbnail. Trocar aqui vale para todos
# os episódios — é identity do canal, não dado de um episódio.
SHOW_NAME = "MEU PODCAST"

POST_NAME_Y = 2338
POST_ROLE_Y = 2459

# 150 e não 160: a Poppins é mais larga que a Avenir Next Demi Bold em que o
# layout foi medido, e a 160 a citação de referência vira 6 lines — a 6ª
# cruzaria o filete em y=2242. A 150 sobram 83px na linha mais cheia.
POST_QUOTE_SIZE = 150
POST_NAME_SIZE = 62
POST_ROLE_SIZE = 38

POST_QUOTE_COLOR = (245, 242, 234)
POST_NAME_COLOR = (255, 255, 255)
POST_ROLE_COLOR = (154, 149, 144)

# Fonte da citação e do rodapé do post.
POST_FONT = _bundled_font("Poppins-SemiBold.ttf")
POST_MONO = _bundled_font("DejaVuSansMono-Bold.ttf")

# ---------------------------------------------------------------------------
# Publicação agendada
# ---------------------------------------------------------------------------
# Fuso da publicação — explícito porque máquina em UTC perto da meia-noite
# mudaria o day da publicação em silêncio — data sempre com zona.
PUBLISH_TZ = "America/Sao_Paulo"
