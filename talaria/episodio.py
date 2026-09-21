"""Metadados do episódio — fonte da verdade para nomes próprios e numeração.

A seção 4 do prompt de materiais é categórica: não inventar, e transcrição
automática erra nome próprio. Estes campos são entrada explícita do gestor,
nunca inferência a partir do áudio.
"""
from __future__ import annotations

import json
import os

from . import layout

CAMPOS_OBRIGATORIOS = ["temporada", "episodio", "empresa", "cidade", "uf", "convidados"]

# Subconjunto que também precisa ter valor. `convidados` pode ser lista vazia:
# episódio só com os apresentadores é caso real previsto no prompt de materiais.
# `empresa` sai daqui e é checada à parte, porque no episódio host-only ela
# pode legitimamente ficar vazia (ver _valida_empresa_ou_tema).
CAMPOS_OBRIGATORIOS_PREENCHIDOS = [c for c in CAMPOS_OBRIGATORIOS
                                   if c not in ("convidados", "empresa")]

NOME_ARQUIVO = "episodio.json"


def template() -> dict:
    """Esqueleto para o gestor preencher."""
    return {
        "temporada": 0,
        "episodio": 0,
        "empresa": "",
        "cidade": "",
        "uf": "SP",
        "convidados": [{"nome": "", "cargo": "", "linkedin": ""}],
        "temas": [],  # opcional — fallback de hashtag quando não há empresa
        # URL do episódio completo no YouTube, preenchida quando o vídeo longo
        # sobe. Entra na descrição dos Shorts como chamada para o episódio.
        # Opcional: o corte é renderizado antes de o longo estar no ar.
        "url_youtube": "",
    }


def _valida_empresa_ou_tema(ep: dict) -> None:
    """Exige `empresa`, exceto no episódio só com os apresentadores.

    O prompt de materiais prevê o caso em três pontos: a seção 1 descreve o
    "episódio sem convidado externo, só com os apresentadores"; a seção 5 diz
    que nesse caso a linha 1 da thumb recebe o tema do episódio; e a seção 2
    manda substituir a hashtag da empresa por uma pertinente ao tema. Ou seja,
    sem empresa o tema é que sustenta thumb e hashtag — por isso ele passa a
    ser obrigatório exatamente aí.
    """
    tem_convidado = bool(ep.get("convidados"))
    tem_empresa = bool(str(ep.get("empresa") or "").strip())
    if tem_empresa:
        return
    if tem_convidado:
        raise ValueError(
            "episodio.json não preenchido — campos em branco: empresa "
            "(obrigatória quando há convidado externo)"
        )
    if not (ep.get("temas") or []):
        raise ValueError(
            "episodio.json: episódio sem convidado externo e sem empresa "
            "precisa de ao menos um tema em 'temas' — é dele que saem a "
            "linha 1 da thumb e a hashtag do tema"
        )


def url_youtube(project_dir: str) -> str:
    """A URL do episódio completo, ou vazio quando não há.

    Não passa pelo `load` de propósito: este campo é opcional e serve a um
    caption, que não pode quebrar por episodio.json ausente ou incompleto. O
    `load` valida o episódio inteiro e ABORTA — contrato certo para quem
    precisa dos nomes próprios, errado para um bloco de texto que pode faltar.
    """
    path = layout.episodio(project_dir)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            ep = json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return ""
    valor = ep.get("url_youtube")
    return valor.strip() if isinstance(valor, str) else ""


def load(project_dir: str) -> dict:
    """Lê e valida o episodio.json do projeto."""
    path = layout.episodio(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py ingest' para criar o template."
        )
    with open(path, encoding="utf-8") as f:
        ep = json.load(f)
    faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in ep]
    if faltando:
        raise ValueError(f"episodio.json incompleto — falta: {', '.join(faltando)}")

    # `convidados` fica fora da checagem de vazio de propósito: o prompt de materiais
    # prevê "episódio sem convidado externo, só com os apresentadores", então
    # lista vazia é preenchimento legítimo, não campo esquecido.
    vazios = [c for c in CAMPOS_OBRIGATORIOS_PREENCHIDOS
              if ep[c] == "" or ep[c] == [] or ep[c] == 0]
    if vazios:
        raise ValueError(
            f"episodio.json não preenchido — campos em branco: {', '.join(vazios)}"
        )

    _valida_empresa_ou_tema(ep)

    for campo in ("temporada", "episodio"):
        try:
            ep[campo] = int(ep[campo])
        except (TypeError, ValueError):
            raise ValueError(
                f"episodio.json: '{campo}' deve ser número inteiro, "
                f"recebido {ep[campo]!r}"
            ) from None
    return ep


def save(project_dir: str, data: dict) -> str:
    path = layout.garante(layout.episodio(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def codigo(ep: dict) -> str:
    """T[N]E[NN] — episódio sempre com dois dígitos (T2E07, nunca T2E7)."""
    return f"T{ep['temporada']}E{int(ep['episodio']):02d}"
