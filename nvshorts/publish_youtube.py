"""Upload de Shorts via YouTube Data API v3.

OAuth2 com refresh token: a autorização (consentimento do dono do canal) é
manual e única, via scripts/youtube_auth.py — o pipeline nunca abre browser.
O upload custa ~1600 unidades da quota diária de 10k; no volume da casa
(poucos Shorts por semana) isso não encosta no limite.
"""
from __future__ import annotations

import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ESCOPO = ["https://www.googleapis.com/auth/youtube.upload"]

# Categoria "People & Blogs" — o YouTube exige uma; é a de videocast.
CATEGORIA = "22"

# Privacidade aceita pelo YouTube. `unlisted` serve para conferir o Short no
# canal antes de abrir ao público — útil na estreia e em teste de agenda.
PRIVACIDADES = ("public", "unlisted", "private")
PRIVACIDADE_PADRAO = "public"


def privacidade() -> str:
    """Privacidade do Short, do `.env`. Sem a variável, publica público.

    Valor inválido ABORTA em vez de cair no padrão: um typo em
    `YT_PRIVACY=unlised` publicaria aberto justo quando se pediu o contrário,
    e vídeo público não se despublica sem já ter sido visto.
    """
    valor = (os.environ.get("YT_PRIVACY") or "").strip().lower()
    if not valor:
        return PRIVACIDADE_PADRAO
    if valor not in PRIVACIDADES:
        raise ValueError(
            f"YT_PRIVACY={valor!r} não é válido — use "
            f"{', '.join(PRIVACIDADES)}."
        )
    return valor


def _credenciais() -> Credentials:
    caminho = os.environ.get("YT_CLIENT_SECRET_PATH", "")
    refresh = os.environ.get("YT_REFRESH_TOKEN", "")
    faltam = [n for n, v in (("YT_CLIENT_SECRET_PATH", caminho),
                             ("YT_REFRESH_TOKEN", refresh)) if not v]
    if faltam:
        raise RuntimeError(
            f"{', '.join(faltam)} não definido no ambiente (.env). Rode "
            f"'python scripts/youtube_auth.py <client_secret.json>' uma vez "
            f"para gerar o refresh token."
        )
    with open(caminho, encoding="utf-8") as f:
        cs = json.load(f)["installed"]
    return Credentials(None, refresh_token=refresh,
                       token_uri=cs["token_uri"], client_id=cs["client_id"],
                       client_secret=cs["client_secret"], scopes=ESCOPO)


def upload(video_path: str, titulo: str, descricao: str) -> dict:
    """Sobe o vídeo (resumable) e devolve id e URL do Short."""
    service = build("youtube", "v3", credentials=_credenciais())
    corpo = {
        "snippet": {"title": titulo, "description": descricao,
                    "categoryId": CATEGORIA},
        "status": {"privacyStatus": privacidade(),
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    req = service.videos().insert(part="snippet,status", body=corpo,
                                  media_body=media)
    resposta = None
    while resposta is None:
        _, resposta = req.next_chunk()
    vid = resposta["id"]
    return {"id": vid, "url": f"https://www.youtube.com/shorts/{vid}"}
