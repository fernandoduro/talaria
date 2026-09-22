"""Orquestrador da publicação: o que a agenda manda pro dia, nas plataformas.

Pré-checagem completa ANTES do primeiro upload — o mesmo contrato do
post_instagram.generate(), pelo mesmo reason: descobrir no item 3 que faltou
renderizar, com os itens 1-2 já no ar, é o estado que este módulo proíbe.

Cada sucesso é registrado NA HORA em published.json; falha numa
platform não trava as outras — o summary final conta o que foi e o que não.
"""
from __future__ import annotations

import os
import re

from . import (schedule, caption, layout, post_instagram, published,
               publish_instagram, publish_youtube)

# Limites das plataformas: validados aqui, antes de chamar a API.
YT_TITLE_MAX = 100
YT_DESCRIPTION_MAX = 5000
IG_CAPTION_MAX = 2200

# Credenciais exigidas por platform — a pré-checagem só cobra as das
# plataformas que o dia realmente usa.
_CREDENTIALS = {
    "youtube_shorts": ("YT_CLIENT_SECRET_PATH", "YT_REFRESH_TOKEN"),
    "instagram_reels": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
    "instagram_posts": ("IG_PAGE_TOKEN", "IG_BUSINESS_ACCOUNT_ID",
                        "S3_PUBLISH_BUCKET"),
}

_MP4_SUFFIX = {"youtube_shorts": "_short.mp4", "instagram_reels": "_reel.mp4"}


def _mp4(pd: str, platform: str, slug: str) -> str:
    """Caminho do clip renderizado, com o slug saneado.

    O `schedule.carrega` já recusa slug com barra, mas o saneamento fica
    aqui também: é o mesmo tratamento que os PNGs de post recebem, e a
    consequência de um slug escapando da pasta é publish arquivo de fora do
    project — cara demais para depender de uma única barreira.
    """
    return os.path.join(layout.platform(pd, platform),
                        post_instagram.file_slug(slug)
                        + _MP4_SUFFIX[platform])


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _moments_by_slug(pd: str) -> dict:
    return {m.get("slug"): m for m in schedule.moments(pd)}


def _post_pngs(pd: str, slug: str) -> list:
    """Os PNGs de um post, na ordem do carrossel (numérica, não alfabética)."""
    arq = post_instagram.file_slug(slug)
    pasta = layout.posts_png(pd)
    unico = os.path.join(pasta, f"post_{arq}.png")
    if os.path.exists(unico):
        return [unico]
    if not os.path.isdir(pasta):
        return []
    padrao = re.compile(rf"^post_{re.escape(arq)}_(\d+)\.png$")
    numerados = []
    for name in os.listdir(pasta):
        m = padrao.match(name)
        if m:
            numerados.append((int(m.group(1)), name))
    numerados.sort()
    return [os.path.join(pasta, n) for _, n in numerados]


def _post_txt(pd: str, slug: str) -> str:
    arq = post_instagram.file_slug(slug)
    return os.path.join(layout.posts_png(pd), f"post_{arq}.txt")


def precheck(pd: str, pares: list) -> list:
    """Erros que impediriam publish QUALQUER item do dia. Lista vazia = ok.

    Roda antes do primeiro upload: arquivo faltando, título ausente/longo,
    legenda acima do limite, credencial não definida. A mensagem sempre diz
    qual comando ou arquivo resolve.
    """
    erros = []
    tem_corte = any(item["kind"] == "clip" for item, _ in pares)
    moments = _moments_by_slug(pd) if tem_corte else {}

    for item, pl in pares:
        slug = item["slug"]
        if item["kind"] == "clip":
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
            texto = _read(txt)
            if pl == "youtube_shorts":
                title = (moments.get(slug) or {}).get("title") or ""
                if not title.strip():
                    erros.append(
                        f"{slug}: sem 'title' no moments.json — o YouTube "
                        f"exige título; preencha o campo no curation.json e "
                        f"rode 'curate --export'")
                elif len(title) > YT_TITLE_MAX:
                    erros.append(f"{slug}: titulo com {len(title)} chars — "
                                 f"o YouTube aceita {YT_TITLE_MAX}")
                if len(texto) > YT_DESCRIPTION_MAX:
                    erros.append(f"{slug}: descrição com {len(texto)} chars — "
                                 f"o YouTube aceita {YT_DESCRIPTION_MAX}")
            elif len(texto) > IG_CAPTION_MAX:
                erros.append(f"{slug} ({pl}): legenda com {len(texto)} chars "
                             f"— o Instagram aceita {IG_CAPTION_MAX}")
        else:
            pngs = _post_pngs(pd, slug)
            if not pngs:
                erros.append(f"{slug} (instagram_posts): nenhum PNG em "
                             f"{layout.posts_png(pd)} — rode 'post --generate' "
                             f"antes")
                continue
            txt = _post_txt(pd, slug)
            if not os.path.exists(txt):
                erros.append(f"{slug} (instagram_posts): {txt} não existe — "
                             f"regere com 'post --generate'")
            elif len(_read(txt)) > IG_CAPTION_MAX:
                erros.append(f"{slug} (instagram_posts): legenda acima de "
                             f"{IG_CAPTION_MAX} chars")

    envs = set()
    for _, pl in pares:
        envs.update(_CREDENTIALS[pl])
    for name in sorted(envs):
        if not os.environ.get(name):
            erros.append(f"variável {name} não definida no ambiente (.env)")

    # Privacidade errada só apareceria depois do upload, com o vídeo já no ar
    # sob a privacy que não se pediu.
    if any(pl == "youtube_shorts" for _, pl in pares):
        try:
            publish_youtube.privacy()
        except ValueError as e:
            erros.append(str(e))
    return erros


def _publish_pair(pd: str, item: dict, pl: str, moments: dict) -> dict:
    """Publica UM par (item, platform). Devolve {"id", "url"}."""
    slug = item["slug"]
    if pl == "youtube_shorts":
        video = _mp4(pd, pl, slug)
        m = moments[slug]
        return publish_youtube.upload(video, m["title"],
                                      _read(caption.caminho(video)))
    if pl == "instagram_reels":
        video = _mp4(pd, pl, slug)
        r = publish_instagram.publish_reel(video, _read(caption.caminho(video)))
        return {"id": r["id"], "url": r.get("permalink", "")}
    pngs = _post_pngs(pd, slug)
    r = publish_instagram.publish_post(pngs, _read(_post_txt(pd, slug)))
    return {"id": r["id"], "url": r.get("permalink", "")}


def execute(pd: str, only: list = None, dia=None,
             plataformas: list = None) -> list:
    """Publica os pares pendentes do dia. Devolve um resultado por par.

    Pré-checagem reprovada aborta TUDO antes do primeiro upload. Depois dela,
    cada par é independente: falha num não trava os outros (a exceção vira
    resultado com ok=False), e cada sucesso record em published.json NA
    HORA — processo morto no meio do lote não duplica nada amanhã.

    São três desfechos, não dois. Publicar e registrar são passos separados,
    e o que acontece entre eles importa:

    - `ok=False`             — não foi ao ar; volta na fila de amanhã.
    - `ok=True`              — foi ao ar e ficou registrado.
    - `ok=True` +
      `record_failed=True` — FOI AO AR e o registro falhou. Sai como
                               published de propósito: marcar falha mandaria
                               o par pra fila de amanhã e publicaria a peça
                               de novo. O `id` vem no resultado para o gestor
                               acrescentar ao published.json à mão.
    """
    pares = schedule.pending(pd, dia=dia, only=only,
                                plataformas=plataformas)
    if not pares:
        return []

    erros = precheck(pd, pares)
    if erros:
        raise ValueError("pré-checagem reprovou — nada foi publicado:\n- "
                         + "\n- ".join(erros))

    tem_corte = any(item["kind"] == "clip" for item, _ in pares)
    moments = _moments_by_slug(pd) if tem_corte else {}
    resultados = []
    for item, pl in pares:
        slug = item["slug"]
        base = {"slug": slug, "platform": pl, "data": item["data"]}
        try:
            r = _publish_pair(pd, item, pl, moments)
        except Exception as e:  # noqa: BLE001 — falha de UM par não trava o resto
            resultados.append({**base, "ok": False, "error": str(e)})
            print(f"[publish] !! {pl}: {slug}: {e}")
            continue

        url = r.get("url", "")
        # Daqui pra baixo a peça JÁ ESTÁ NO AR. Falha do registro não pode
        # virar ok=False: a pendência sai da ausência no published.json, então
        # o par voltaria amanhã e publicaria de novo — a duplicata que não tem
        # correção. Sai como published, com o id à mão para o conserto.
        try:
            published.record(pd, pl, slug, r["id"], url)
        except Exception as e:  # noqa: BLE001
            resultados.append({**base, "ok": True, "url": url, "id": r["id"],
                               "record_failed": True, "error": str(e)})
            print(f"[publish] !! {pl}: {slug} FOI PUBLICADO ({url or r['id']}) "
                  f"mas não entrou no published.json: {e}")
            print(f"[publish]    NÃO rode publish de novo antes de acrescentar "
                  f"este id à mão — ou o {pl} publica a peça duas vezes.")
            continue

        resultados.append({**base, "ok": True, "url": url})
        print(f"[publish] ok {pl}: {slug} -> {url or r['id']}")
    return resultados
