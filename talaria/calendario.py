"""Agenda de publicação: que peça sai em que dia.

O calendário é decisão editorial — o gestor escreve decisoes/calendario.json
como escreve posts.json. Este módulo valida contra as fontes (momentos.json,
posts.json) ANTES de qualquer publicação: slug digitado errado publicaria o
corte errado, e isso não tem correção depois de publicado.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import config, layout, post_instagram, publicado

# Plataformas por tipo de item. Os nomes são os das pastas de publicar/ e as
# chaves do publicado.json — uma grafia só, do arquivo ao registro.
PLATAFORMAS = {
    "corte": ("youtube_shorts", "instagram_reels"),
    "post": ("instagram_posts",),
}

# O carrossel do Instagram aceita 2-10 imagens.
CARROSSEL_MAX = 10


def hoje() -> dt.date:
    """A data corrente no fuso da casa — nunca a data ingênua da máquina."""
    return dt.datetime.now(ZoneInfo(config.FUSO_PUBLICACAO)).date()


def plataformas_do(item: dict) -> tuple:
    return PLATAFORMAS[item["tipo"]]


def data_do(item: dict) -> dt.date:
    """A data do item como date. fromisoformat valida formato E dia real."""
    return dt.date.fromisoformat(item["data"])


def momentos(pd: str) -> list:
    """Os cortes exportados pela curadoria, ou erro que diz o comando."""
    path = layout.momentos(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py curar --projeto <slug> "
            f"--exportar' antes de agendar cortes."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def carrega(pd: str) -> list:
    """Lê e valida a agenda. Qualquer item inválido aborta a carga inteira."""
    path = layout.calendario(pd)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Escreva a agenda de publicação: "
            f'{{"agenda": [{{"data": "YYYY-MM-DD", "tipo": "corte|post", '
            f'"slug": "..."}}]}}'
        )
    with open(path, encoding="utf-8") as f:
        agenda = (json.load(f) or {}).get("agenda") or []
    if not agenda:
        raise ValueError(f"{path} não tem nenhum item em 'agenda'")

    # Fontes carregadas sob demanda: agenda só de posts não exige momentos.json.
    cortes = posts = None
    vistos = set()
    for i, item in enumerate(agenda, start=1):
        slug = item.get("slug") or ""
        tipo = item.get("tipo") or ""
        onde = f"item {i} da agenda ('{slug or '?'}')"
        if tipo not in PLATAFORMAS:
            raise ValueError(f"{onde}: tipo {tipo!r} — use 'corte' ou 'post'")
        if not slug:
            raise ValueError(f"{onde}: sem slug")
        # O slug vira nome de arquivo dentro de publicar/. Barra ou `..` o
        # tiram da pasta do episódio, e aí o publish encontra um mp4 de fora
        # do projeto, passa na pré-checagem e publica a peça errada — com o
        # texto de fora virando descrição pública. O slug do corte é digitado
        # à mão no curadoria.json e ninguém o valida antes daqui.
        if "/" in slug or "\\" in slug or slug.strip(". ") != slug:
            raise ValueError(
                f"{onde}: slug não pode ter barra nem começar/terminar com "
                f"ponto — ele vira nome de arquivo em publicar/, e assim "
                f"apontaria para fora da pasta do episódio"
            )
        # A chave é (tipo, slug), não o slug: o post de citação herda o slug
        # do corte que cita (é assim que `post --cortes` o nomeia), e corte e
        # post do mesmo trecho na mesma agenda é o caso comum, não repetição.
        # Publicar/registrar já separam os dois por plataforma.
        if (tipo, slug) in vistos:
            raise ValueError(
                f"{onde}: {tipo} aparece duas vezes — para mudar a data, "
                f"edite o item existente em vez de repetir"
            )
        vistos.add((tipo, slug))
        try:
            data_do(item)
        except (TypeError, ValueError):
            raise ValueError(
                f"{onde}: data {item.get('data')!r} inválida — use "
                f"YYYY-MM-DD de um dia que existe"
            )
        if tipo == "corte":
            if cortes is None:
                cortes = {m.get("slug") for m in momentos(pd)}
            if slug not in cortes:
                raise ValueError(
                    f"{onde}: não está em {layout.momentos(pd)} — "
                    f"cortes disponíveis: {', '.join(sorted(cortes))}"
                )
        else:
            if posts is None:
                posts = {p.get("slug"): p for p in post_instagram.carrega(pd)}
            if slug not in posts:
                raise ValueError(
                    f"{onde}: não está em {layout.posts(pd)} — "
                    f"posts disponíveis: {', '.join(sorted(posts))}"
                )
            cards = posts[slug].get("cards") or []
            if len(cards) > CARROSSEL_MAX:
                raise ValueError(
                    f"post '{slug}' tem {len(cards)} cards — o carrossel do "
                    f"Instagram aceita no máximo {CARROSSEL_MAX}; quebre em "
                    f"dois posts"
                )
    return agenda


def pendente(pd: str, dia: dt.date = None, only: list = None,
             plataformas: list = None) -> list:
    """Pares (item, plataforma) devidos até `dia` e ainda não publicados.

    A unidade é (slug, plataforma), não o item: um corte publica em YouTube E
    Reels, e se só uma passou, o retry publica só a que faltou (AP-06 —
    pendência por item republicaria a que já foi).

    `only` ignora o filtro de data (antecipar, testar), mas NUNCA a trava do
    publicado.json — republicar é editar o registro à mão, de propósito, não
    um flag digitável por engano.

    `only=None` é "sem filtro"; `only=[]` é "filtre para nada" e devolve
    vazio. A distinção é `is not None` de propósito: o chamador que monta a
    lista a partir de uma flag vazia pediria a agenda inteira sem querer, e
    publicaria o dia todo achando que tinha restringido a um slug.

    `plataformas` restringe a quais plataformas sair. Serve para publicar
    quando só uma está configurada: um corte cobra credencial do YouTube E do
    Instagram, então sem isso ele fica inteiro parado. O que não sai continua
    pendente — a trava é por (slug, plataforma), então o resto vai depois.

    Atrasado (data < dia, não publicado) continua pendente: esquecer de rodar
    ontem não pode perder a publicação.
    """
    dia = dia or hoje()
    if plataformas is not None:
        conhecidas = {p for pls in PLATAFORMAS.values() for p in pls}
        estranhas = sorted(set(plataformas) - conhecidas)
        if estranhas:
            raise ValueError(
                f"plataforma desconhecida: {', '.join(estranhas)} — "
                f"use {', '.join(sorted(conhecidas))}"
            )
    agenda = carrega(pd)
    if only is not None:
        desconhecidos = sorted(set(only) - {i["slug"] for i in agenda})
        if desconhecidos:
            raise ValueError(
                f"--only: {', '.join(desconhecidos)} não está(ão) na agenda "
                f"({layout.calendario(pd)})"
            )
        agenda = [i for i in agenda if i["slug"] in set(only)]
    else:
        agenda = [i for i in agenda if data_do(i) <= dia]

    reg = publicado.carrega(pd)
    pares = []
    for item in agenda:
        for pl in plataformas_do(item):
            if plataformas is not None and pl not in plataformas:
                continue
            if not publicado.ja_publicado(reg, pl, item["slug"]):
                pares.append((item, pl))
    return pares
