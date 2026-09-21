"""Orquestrador da publicação: o que a agenda manda pro dia, nas plataformas.

Pré-checagem completa ANTES do primeiro upload — o mesmo contrato do
post_instagram.gerar(), pelo mesmo motivo: descobrir no item 3 que faltou
renderizar, com os itens 1-2 já no ar, é o estado que este módulo proíbe.

Cada sucesso é registrado NA HORA em publicado.json; falha numa
plataforma não trava as outras — o resumo final conta o que foi e o que não.
"""
from __future__ import annotations

import os
import re

from . import (calendario, caption, layout, post_instagram, publicado,
               publish_instagram, publish_youtube)

# Limites das plataformas: validados aqui, antes de chamar a API.
YT_TITULO_MAX = 100
YT_DESCRICAO_MAX = 5000
IG_LEGENDA_MAX = 2200

# Credenciais exigidas por plataforma — a pré-checagem só cobra as das
# plataformas que o dia realmente usa.
_CREDENCIAIS = {
    "youtube_shorts": ("YT_CLIENT_SECRET_PATH", "YT_REFRESH_TOKEN"),
    "instagram_reels": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
    "instagram_posts": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
}

_SUFIXO_MP4 = {"youtube_shorts": "_short.mp4", "instagram_reels": "_reel.mp4"}


def _mp4(pd: str, plataforma: str, slug: str) -> str:
    """Caminho do corte renderizado, com o slug saneado.

    O `calendario.carrega` já recusa slug com barra, mas o saneamento fica
    aqui também: é o mesmo tratamento que os PNGs de post recebem, e a
    consequência de um slug escapando da pasta é publicar arquivo de fora do
    projeto — cara demais para depender de uma única barreira.
    """
    return os.path.join(layout.plataforma(pd, plataforma),
                        post_instagram.slug_de_arquivo(slug)
                        + _SUFIXO_MP4[plataforma])


def _le(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _momentos_por_slug(pd: str) -> dict:
    return {m.get("slug"): m for m in calendario.momentos(pd)}


def _pngs_do_post(pd: str, slug: str) -> list:
    """Os PNGs de um post, na ordem do carrossel (numérica, não alfabética)."""
    arq = post_instagram.slug_de_arquivo(slug)
    pasta = layout.posts_png(pd)
    unico = os.path.join(pasta, f"post_{arq}.png")
    if os.path.exists(unico):
        return [unico]
    if not os.path.isdir(pasta):
        return []
    padrao = re.compile(rf"^post_{re.escape(arq)}_(\d+)\.png$")
    numerados = []
    for nome in os.listdir(pasta):
        m = padrao.match(nome)
        if m:
            numerados.append((int(m.group(1)), nome))
    numerados.sort()
    return [os.path.join(pasta, n) for _, n in numerados]


def _txt_do_post(pd: str, slug: str) -> str:
    arq = post_instagram.slug_de_arquivo(slug)
    return os.path.join(layout.posts_png(pd), f"post_{arq}.txt")


def pre_checa(pd: str, pares: list) -> list:
    """Erros que impediriam publicar QUALQUER item do dia. Lista vazia = ok.

    Roda antes do primeiro upload: arquivo faltando, título ausente/longo,
    legenda acima do limite, credencial não definida. A mensagem sempre diz
    qual comando ou arquivo resolve.
    """
    erros = []
    tem_corte = any(item["tipo"] == "corte" for item, _ in pares)
    momentos = _momentos_por_slug(pd) if tem_corte else {}

    for item, pl in pares:
        slug = item["slug"]
        if item["tipo"] == "corte":
            video = _mp4(pd, pl, slug)
            if not os.path.exists(video):
                erros.append(f"{slug} ({pl}): {video} não existe — "
                             f"rode 'render' antes")
                continue
            txt = caption.caminho(video)
            if not os.path.exists(txt):
                erros.append(f"{slug} ({pl}): {txt} não existe — "
                             f"regere o corte com 'render'")
                continue
            texto = _le(txt)
            if pl == "youtube_shorts":
                titulo = (momentos.get(slug) or {}).get("titulo") or ""
                if not titulo.strip():
                    erros.append(
                        f"{slug}: sem 'titulo' no momentos.json — o YouTube "
                        f"exige título; preencha o campo no curadoria.json e "
                        f"rode 'curar --exportar'")
                elif len(titulo) > YT_TITULO_MAX:
                    erros.append(f"{slug}: titulo com {len(titulo)} chars — "
                                 f"o YouTube aceita {YT_TITULO_MAX}")
                if len(texto) > YT_DESCRICAO_MAX:
                    erros.append(f"{slug}: descrição com {len(texto)} chars — "
                                 f"o YouTube aceita {YT_DESCRICAO_MAX}")
            elif len(texto) > IG_LEGENDA_MAX:
                erros.append(f"{slug} ({pl}): legenda com {len(texto)} chars "
                             f"— o Instagram aceita {IG_LEGENDA_MAX}")
        else:
            pngs = _pngs_do_post(pd, slug)
            if not pngs:
                erros.append(f"{slug} (instagram_posts): nenhum PNG em "
                             f"{layout.posts_png(pd)} — rode 'post --gerar' "
                             f"antes")
                continue
            txt = _txt_do_post(pd, slug)
            if not os.path.exists(txt):
                erros.append(f"{slug} (instagram_posts): {txt} não existe — "
                             f"regere com 'post --gerar'")
            elif len(_le(txt)) > IG_LEGENDA_MAX:
                erros.append(f"{slug} (instagram_posts): legenda acima de "
                             f"{IG_LEGENDA_MAX} chars")

    envs = set()
    for _, pl in pares:
        envs.update(_CREDENCIAIS[pl])
    for nome in sorted(envs):
        if not os.environ.get(nome):
            erros.append(f"variável {nome} não definida no ambiente (.env)")

    # Privacidade errada só apareceria depois do upload, com o vídeo já no ar
    # sob a privacidade que não se pediu.
    if any(pl == "youtube_shorts" for _, pl in pares):
        try:
            publish_youtube.privacidade()
        except ValueError as e:
            erros.append(str(e))
    return erros


def _publica_par(pd: str, item: dict, pl: str, momentos: dict) -> dict:
    """Publica UM par (item, plataforma). Devolve {"id", "url"}."""
    slug = item["slug"]
    if pl == "youtube_shorts":
        video = _mp4(pd, pl, slug)
        m = momentos[slug]
        return publish_youtube.upload(video, m["titulo"],
                                      _le(caption.caminho(video)))
    if pl == "instagram_reels":
        video = _mp4(pd, pl, slug)
        r = publish_instagram.publica_reel(video, _le(caption.caminho(video)))
        return {"id": r["id"], "url": r.get("permalink", "")}
    pngs = _pngs_do_post(pd, slug)
    r = publish_instagram.publica_post(pngs, _le(_txt_do_post(pd, slug)))
    return {"id": r["id"], "url": r.get("permalink", "")}


def executar(pd: str, only: list = None, dia=None,
             plataformas: list = None) -> list:
    """Publica os pares pendentes do dia. Devolve um resultado por par.

    Pré-checagem reprovada aborta TUDO antes do primeiro upload. Depois dela,
    cada par é independente: falha num não trava os outros (a exceção vira
    resultado com ok=False), e cada sucesso registra em publicado.json NA
    HORA — processo morto no meio do lote não duplica nada amanhã.

    São três desfechos, não dois. Publicar e registrar são passos separados,
    e o que acontece entre eles importa:

    - `ok=False`             — não foi ao ar; volta na fila de amanhã.
    - `ok=True`              — foi ao ar e ficou registrado.
    - `ok=True` +
      `registro_falhou=True` — FOI AO AR e o registro falhou. Sai como
                               publicado de propósito: marcar falha mandaria
                               o par pra fila de amanhã e publicaria a peça
                               de novo. O `id` vem no resultado para o gestor
                               acrescentar ao publicado.json à mão.
    """
    pares = calendario.pendente(pd, dia=dia, only=only,
                                plataformas=plataformas)
    if not pares:
        return []

    erros = pre_checa(pd, pares)
    if erros:
        raise ValueError("pré-checagem reprovou — nada foi publicado:\n- "
                         + "\n- ".join(erros))

    tem_corte = any(item["tipo"] == "corte" for item, _ in pares)
    momentos = _momentos_por_slug(pd) if tem_corte else {}
    resultados = []
    for item, pl in pares:
        slug = item["slug"]
        base = {"slug": slug, "plataforma": pl, "data": item["data"]}
        try:
            r = _publica_par(pd, item, pl, momentos)
        except Exception as e:  # noqa: BLE001 — falha de UM par não trava o resto
            resultados.append({**base, "ok": False, "erro": str(e)})
            print(f"[publish] !! {pl}: {slug}: {e}")
            continue

        url = r.get("url", "")
        # Daqui pra baixo a peça JÁ ESTÁ NO AR. Falha do registro não pode
        # virar ok=False: a pendência sai da ausência no publicado.json, então
        # o par voltaria amanhã e publicaria de novo — a duplicata que não tem
        # correção. Sai como publicado, com o id à mão para o conserto.
        try:
            publicado.registra(pd, pl, slug, r["id"], url)
        except Exception as e:  # noqa: BLE001
            resultados.append({**base, "ok": True, "url": url, "id": r["id"],
                               "registro_falhou": True, "erro": str(e)})
            print(f"[publish] !! {pl}: {slug} FOI PUBLICADO ({url or r['id']}) "
                  f"mas não entrou no publicado.json: {e}")
            print(f"[publish]    NÃO rode publish de novo antes de acrescentar "
                  f"este id à mão — ou o {pl} publica a peça duas vezes.")
            continue

        resultados.append({**base, "ok": True, "url": url})
        print(f"[publish] ok {pl}: {slug} -> {url or r['id']}")
    return resultados
