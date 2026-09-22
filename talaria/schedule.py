"""Agenda de publicação: que peça sai em que day.

O calendário é decisão editorial — o gestor write decisions/schedule.json
como write posts.json. Este módulo validate contra as fontes (moments.json,
posts.json) ANTES de qualquer publicação: slug digitado errado publicaria o
clip errado, e isso não tem correção depois de published.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import config, layout, post_instagram, published

# Plataformas por kind de item. Os names são os das pastas de publish/ e as
# chaves do published.json — uma grafia só, do arquivo ao registro.
PLATFORMS = {
    "clip": ("youtube_shorts", "instagram_reels"),
    "post": ("instagram_posts",),
}

# O carrossel do Instagram aceita 2-10 imagens.
CAROUSEL_MAX = 10


def today() -> dt.date:
    """A data corrente no fuso configurado — nunca a data ingênua da máquina."""
    return dt.datetime.now(ZoneInfo(config.PUBLISH_TZ)).date()


def platforms_of(item: dict) -> tuple:
    return PLATFORMS[item["kind"]]


def date_of(item: dict) -> dt.date:
    """A data do item como date. fromisoformat validate formato E day real."""
    return dt.date.fromisoformat(item["date"])


def moments(pd: str) -> list:
    """Os cortes exportados pela curation, ou error que diz o comando."""
    path = layout.moments(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py curate --project <slug> "
            f"--export' antes de agendar cortes."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(pd: str) -> list:
    """Lê e validate a agenda. Qualquer item inválido aborta a carga inteira."""
    path = layout.schedule(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Escreva a agenda de publicação: "
            f'{{"schedule": [{{"date": "YYYY-MM-DD", "kind": "clip|post", '
            f'"slug": "..."}}]}}'
        )
    with open(path, encoding="utf-8") as f:
        items = (json.load(f) or {}).get("schedule") or []
    if not items:
        raise ValueError(f"{path} não tem nenhum item em 'schedule'")

    # Fontes carregadas sob demanda: agenda só de posts não exige moments.json.
    clips = posts = None
    seen = set()
    for i, item in enumerate(items, start=1):
        slug = item.get("slug") or ""
        kind = item.get("kind") or ""
        where = f"item {i} da agenda ('{slug or '?'}')"
        if kind not in PLATFORMS:
            raise ValueError(f"{where}: tipo {kind!r} — use 'clip' ou 'post'")
        if not slug:
            raise ValueError(f"{where}: sem slug")
        # O slug vira name de arquivo dentro de publish/. Barra ou `..` o
        # tiram da pasta do episódio, e aí o publish encontra um mp4 de fora
        # do project, passa na pré-checagem e publica a peça errada — com o
        # texto de fora virando descrição pública. O slug do clip é digitado
        # à mão no curation.json e ninguém o validate antes daqui.
        if "/" in slug or "\\" in slug or slug.strip(". ") != slug:
            raise ValueError(
                f"{where}: slug não pode ter barra nem começar/terminar com "
                f"ponto — ele vira nome de arquivo em publish/, e assim "
                f"apontaria para fora da pasta do episódio"
            )
        # A chave é (kind, slug), não o slug: o post de citação herda o slug
        # do clip que cita (é assim que `post --cortes` o nomeia), e clip e
        # post do mesmo trecho na mesma agenda é o caso comum, não repetição.
        # Publicar/registrar já separam os dois por platform.
        if (kind, slug) in seen:
            raise ValueError(
                f"{where}: {kind} aparece duas vezes — para mudar a data, "
                f"edite o item existente em vez de repetir"
            )
        seen.add((kind, slug))
        try:
            date_of(item)
        except (TypeError, ValueError):
            raise ValueError(
                f"{where}: data {item.get('date')!r} inválida — use "
                f"YYYY-MM-DD de um dia que existe"
            )
        if kind == "clip":
            if clips is None:
                clips = {m.get("slug") for m in moments(pd)}
            if slug not in clips:
                raise ValueError(
                    f"{where}: não está em {layout.moments(pd)} — "
                    f"cortes disponíveis: {', '.join(sorted(clips))}"
                )
        else:
            if posts is None:
                posts = {p.get("slug"): p for p in post_instagram.load(pd)}
            if slug not in posts:
                raise ValueError(
                    f"{where}: não está em {layout.posts(pd)} — "
                    f"posts disponíveis: {', '.join(sorted(posts))}"
                )
            cards = posts[slug].get("cards") or []
            if len(cards) > CAROUSEL_MAX:
                raise ValueError(
                    f"post '{slug}' tem {len(cards)} cards — o carrossel do "
                    f"Instagram aceita no máximo {CAROUSEL_MAX}; quebre em "
                    f"dois posts"
                )
    return items


def pending(pd: str, day: dt.date = None, only: list = None,
             platforms: list = None) -> list:
    """Pares (item, platform) devidos até `day` e ainda não publicados.

    A unidade é (slug, platform), não o item: um clip publica em YouTube E
    Reels, e se só uma passou, o retry publica só a que faltou — pendência
    por item republicaria a que já foi.

    `only` ignora o filtro de data (antecipar, testar), mas NUNCA a trava do
    published.json — republicar é editar o registro à mão, de propósito, não
    um flag digitável por engano.

    `only=None` é "sem filtro"; `only=[]` é "filtre para nada" e devolve
    vazio. A distinção é `is not None` de propósito: o chamador que compose a
    lista a partir de uma flag vazia pediria a agenda inteira sem querer, e
    publicaria o day todo achando que tinha restringido a um slug.

    `platforms` restringe a quais platforms sair. Serve para publish
    quando só uma está configurada: um clip cobra credencial do YouTube E do
    Instagram, então sem isso ele fica inteiro parado. O que não sai continua
    pending — a trava é por (slug, platform), então o resto vai depois.

    Atrasado (data < day, não published) continua pending: esquecer de rodar
    ontem não pode perder a publicação.
    """
    day = day or today()
    if platforms is not None:
        known = {p for pls in PLATFORMS.values() for p in pls}
        unknown_platforms = sorted(set(platforms) - known)
        if unknown_platforms:
            raise ValueError(
                f"plataforma desconhecida: {', '.join(unknown_platforms)} — "
                f"use {', '.join(sorted(known))}"
            )
    items = load(pd)
    if only is not None:
        unknown_slugs = sorted(set(only) - {i["slug"] for i in items})
        if unknown_slugs:
            raise ValueError(
                f"--only: {', '.join(unknown_slugs)} não está(ão) na agenda "
                f"({layout.schedule(pd)})"
            )
        items = [i for i in items if i["slug"] in set(only)]
    else:
        items = [i for i in items if date_of(i) <= day]

    reg = published.load(pd)
    pairs = []
    for item in items:
        for pl in platforms_of(item):
            if platforms is not None and pl not in platforms:
                continue
            if not published.is_published(reg, pl, item["slug"]):
                pairs.append((item, pl))
    return pairs
