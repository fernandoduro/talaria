"""Metadados do episódio — fonte da verdade para names próprios e numeração.

Não inventar: transcrição automática erra name próprio. Estes campos são
entrada explícita do gestor, nunca inferência a partir do áudio.
"""
from __future__ import annotations

import json
import os

from . import layout

REQUIRED_FIELDS = ["season", "episode", "company", "city", "uf", "guests"]

# Subconjunto que também precisa ter valor. `guests` pode ser lista vazia:
# episódio só com os apresentadores é caso real.
# `company` sai daqui e é checada à parte, porque no episódio host-only ela
# pode legitimamente ficar vazia (ver _validate_company_or_topic).
REQUIRED_NONEMPTY_FIELDS = [c for c in REQUIRED_FIELDS
                                   if c not in ("guests", "company")]

FILE_NAME = "episode.json"


def template() -> dict:
    """Esqueleto para o gestor preencher."""
    return {
        "season": 0,
        "episode": 0,
        "company": "",
        "city": "",
        "uf": "SP",
        "guests": [{"name": "", "role": "", "linkedin": ""}],
        "topics": [],  # opcional — fallback de hashtag quando não há company
        # URL do episódio completo no YouTube, preenchida quando o vídeo longo
        # sobe. Entra na descrição dos Shorts como chamada para o episódio.
        # Opcional: o clip é renderizado antes de o longo estar no ar.
        "youtube_url": "",
    }


def _validate_company_or_topic(ep: dict) -> None:
    """Exige `company`, exceto no episódio só com os apresentadores.

    Sem convidado externo não há company, e é o tema que sustenta a linha 1 da
    thumb e a hashtag — por isso ele passa a ser obrigatório exatamente aí.
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
    """A URL do episódio completo, ou vazio quando não há.

    Não passa pelo `load` de propósito: este campo é opcional e serve a um
    caption, que não pode quebrar por episode.json ausente ou incompleto. O
    `load` validate o episódio inteiro e ABORTA — contrato certo para quem
    precisa dos names próprios, errado para um bloco de texto que pode faltar.
    """
    path = layout.episode(project_dir)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            ep = json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return ""
    valor = ep.get("youtube_url")
    return valor.strip() if isinstance(valor, str) else ""


def load(project_dir: str) -> dict:
    """Lê e validate o episode.json do project."""
    path = layout.episode(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py ingest' para criar o template."
        )
    with open(path, encoding="utf-8") as f:
        ep = json.load(f)
    faltando = [c for c in REQUIRED_FIELDS if c not in ep]
    if faltando:
        raise ValueError(f"episode.json incompleto — falta: {', '.join(faltando)}")

    # `guests` fica fora da checagem de vazio de propósito: o prompt de materiais
    # prevê "episódio sem convidado externo, só com os apresentadores", então
    # lista vazia é preenchimento legítimo, não campo esquecido.
    vazios = [c for c in REQUIRED_NONEMPTY_FIELDS
              if ep[c] == "" or ep[c] == [] or ep[c] == 0]
    if vazios:
        raise ValueError(
            f"episode.json não preenchido — campos em branco: {', '.join(vazios)}"
        )

    _validate_company_or_topic(ep)

    for campo in ("season", "episode"):
        try:
            ep[campo] = int(ep[campo])
        except (TypeError, ValueError):
            raise ValueError(
                f"episode.json: '{campo}' deve ser número inteiro, "
                f"recebido {ep[campo]!r}"
            ) from None
    return ep


def save(project_dir: str, data: dict) -> str:
    path = layout.ensure_dir(layout.episode(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def code(ep: dict) -> str:
    """T[N]E[NN] — episódio sempre com dois dígitos (T2E07, nunca T2E7)."""
    return f"T{ep['season']}E{int(ep['episode']):02d}"
