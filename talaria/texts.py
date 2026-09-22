"""texts.json — materiais de publicação e alimentação da thumbnail.

O texto da thumb é derivado do episode.json (linha 1 = company, ou o primeiro
tema quando não há company; linha 2 = T[N]E[NN]), mas o texts.json pode
sobrescrever qualquer campo quando o modelo propõe algo melhor na etapa de
materiais.
"""
from __future__ import annotations

import json
import os

from . import config, episode, layout

FILE_NAME = "texts.json"


def load(project_dir: str) -> dict:
    """Lê o texts.json do project. Retorna dict vazio se ainda não existe."""
    path = layout.texts(project_dir)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, data: dict) -> str:
    """Grava o texts.json do project e devolve o caminho escrito."""
    path = layout.ensure_dir(layout.texts(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def thumb_args(project_dir: str) -> dict:
    """Argumentos da thumbnail, derivados do episódio e sobrescritos por texts.json."""
    ep = episode.load(project_dir)
    cod = episode.code(ep)
    guests = ep.get("guests") or []
    credits = " & ".join(c.get("name", "") for c in guests if c.get("name"))

    # Em episódio sem convidado externo (logo, sem company), a linha 1
    # recebe o tema do episódio.
    topics = ep.get("topics") or []
    l1 = ep.get("company", "") or (topics[0] if topics else "")

    args = {
        "badge": f"{config.SHOW_NAME} • {cod}",
        "l1": l1,
        "l2": cod,
        "credits": credits,
        "subtitle": f"{ep.get('cidade','')}/{ep.get('uf','')}",
    }
    args.update(load(project_dir).get("thumb", {}))
    return args


def build_kwargs(project_dir: str) -> dict:
    """Argumentos no formato que thumbnail.build_thumbnail espera.

    Ponto único de tradução l1/l2 -> headline_l1/headline_l2: mapear à mão no
    call site esquece campo em silêncio (credits e subtitle têm default "" e
    são pulados sem aviso).
    """
    args = thumb_args(project_dir)
    return {
        "badge": args["badge"],
        "headline_l1": args["l1"],
        "headline_l2": args["l2"],
        "credits": args["credits"],
        "subtitle": args["subtitle"],
    }
