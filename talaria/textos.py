"""textos.json — materiais de publicação e alimentação da thumbnail.

O texto da thumb é derivado do episodio.json (linha 1 = empresa, ou o primeiro
tema quando não há empresa; linha 2 = T[N]E[NN], seção 5 do prompt de
materiais), mas o textos.json pode sobrescrever
qualquer campo quando o Claude propõe algo melhor na etapa de materiais.
"""
from __future__ import annotations

import json
import os

from . import config, episodio, layout

NOME_ARQUIVO = "textos.json"


def load(project_dir: str) -> dict:
    """Lê o textos.json do projeto. Retorna dict vazio se ainda não existe."""
    path = layout.textos(project_dir)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, data: dict) -> str:
    """Grava o textos.json do projeto e devolve o caminho escrito."""
    path = layout.garante(layout.textos(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def thumb_args(project_dir: str) -> dict:
    """Argumentos da thumbnail, derivados do episódio e sobrescritos por textos.json."""
    ep = episodio.load(project_dir)
    cod = episodio.codigo(ep)
    convidados = ep.get("convidados") or []
    creditos = " & ".join(c.get("nome", "") for c in convidados if c.get("nome"))

    # Seção 5: em episódio sem convidado externo (logo, sem empresa), a linha 1
    # recebe o tema do episódio.
    temas = ep.get("temas") or []
    l1 = ep.get("empresa", "") or (temas[0] if temas else "")

    args = {
        "selo": f"{config.NOME_PROGRAMA} • {cod}",
        "l1": l1,
        "l2": cod,
        "creditos": creditos,
        "subtitulo": f"{ep.get('cidade','')}/{ep.get('uf','')}",
    }
    args.update(load(project_dir).get("thumb", {}))
    return args


def build_kwargs(project_dir: str) -> dict:
    """Argumentos no formato que thumbnail.build_thumbnail espera.

    Ponto único de tradução l1/l2 -> chamada_l1/chamada_l2: mapear à mão no
    call site esquece campo em silêncio (creditos e subtitulo têm default "" e
    são pulados sem aviso).
    """
    args = thumb_args(project_dir)
    return {
        "selo": args["selo"],
        "chamada_l1": args["l1"],
        "chamada_l2": args["l2"],
        "creditos": args["creditos"],
        "subtitulo": args["subtitulo"],
    }
