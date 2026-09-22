"""Publicação no Instagram via Graph API — Reels e posts do feed.

A Graph API não aceita upload binário: o container busca a mídia numa URL
pública (storage_temp). Vídeo processa assíncrono — poll com timeout, e os
finais ERROR/EXPIRED são falha explícita com o status literal na mensagem (sem
isso o comando trava para sempre num vídeo rejeitado em silêncio).
"""
from __future__ import annotations

import os
import time

import requests

from . import storage_temp

# A Meta tem DOIS fluxos para publish no Instagram, com hosts distintos:
#
#   token EAAG... (login do Facebook)  -> graph.facebook.com, account Business
#                                         vinculada a uma Página
#   token IGAA... (login do Instagram) -> graph.instagram.com, account Business
#                                         direta, sem Página no meio
#
# Os endpoints (`<account>/media`, `media_publish`, o poll de `status_code`) são
# iguais nos dois; muda só o host. Mandar o token de um para o host do outro
# devolve "Cannot parse access token", que não diz qual é o problema — daí
# escolher pelo prefixo em vez de fixar um host.
GRAPH_FACEBOOK = "https://graph.facebook.com/v21.0"
GRAPH_INSTAGRAM = "https://graph.instagram.com/v21.0"


def host_for_token(token: str) -> str:
    """O host que atende este token, pelo prefixo.

    Prefixo desconhecido cai no Facebook, que era o padrão antes de existir
    esta função: melhor a mensagem de error da API do que um palpite nosso.
    """
    return GRAPH_INSTAGRAM if (token or "").startswith("IG") else GRAPH_FACEBOOK


POLL_TIMEOUT_S = 300
POLL_INTERVAL_S = 10
TIMEOUT_HTTP_S = 60


def _credentials() -> tuple:
    token = os.environ.get("IG_PAGE_TOKEN", "")
    account = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "")
    missing = [n for n, v in (("IG_PAGE_TOKEN", token),
                             ("IG_BUSINESS_ACCOUNT_ID", account)) if not v]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} não definido no ambiente (.env). Token "
            f"expirado? Gere outro no painel do app (Instagram → Configuração "
            f"da API) e atualize IG_PAGE_TOKEN — serve tanto o token de "
            f"página (EAAG...) quanto o do login do Instagram (IGAA...)."
        )
    return token, account


def _call(method: str, path: str, **params) -> dict:
    """GET/POST na Graph API; error vira exceção com a mensagem DA API.

    O body de error do Graph vem em {"error": {"message": ...}} mesmo com
    status 200 em alguns fluxos — por isso o body decide junto do status.
    """
    fn = requests.post if method == "post" else requests.get
    host = host_for_token(params.get("access_token", ""))
    r = fn(f"{host}/{path}", params=params, timeout=TIMEOUT_HTTP_S)
    # Corpo que não é JSON (página de error de proxy num 502, response
    # truncada) não pode estourar aqui: trocaria "Graph API: 502" por um
    # JSONDecodeError que não diz o que houve, justo durante o incidente.
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {}
    if r.status_code >= 400 or "error" in body:
        msg = (body.get("error") or {}).get("message") or r.text
        raise RuntimeError(f"Graph API ({path}): {msg}")
    return body


def _wait_for_processing(container_id: str, token: str) -> None:
    """Poll até FINISHED. ERROR/EXPIRED e timeout são falha explícita."""
    start = time.monotonic()
    while True:
        body = _call("get", container_id, fields="status_code",
                       access_token=token)
        status = body.get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"container {container_id}: o Instagram terminou o "
                f"processamento com status {status}"
            )
        if time.monotonic() - start > POLL_TIMEOUT_S:
            raise RuntimeError(
                f"container {container_id}: status {status} após "
                f"{POLL_TIMEOUT_S}s — desisti de esperar"
            )
        time.sleep(POLL_INTERVAL_S)


def _publish_container(container_id: str, token: str, account: str) -> dict:
    body = _call("post", f"{account}/media_publish",
                   creation_id=container_id, access_token=token)
    media_id = body["id"]
    perma = _call("get", media_id, fields="permalink", access_token=token)
    return {"id": media_id, "permalink": perma.get("permalink", "")}


def publish_reel(video_path: str, caption: str) -> dict:
    """Sobe o vídeo, cria o container REELS, espera processar e publica."""
    token, account = _credentials()
    url = storage_temp.put(video_path)
    try:
        body = _call("post", f"{account}/media", media_type="REELS",
                       video_url=url, caption=caption or "",
                       access_token=token)
        _wait_for_processing(body["id"], token)
        return _publish_container(body["id"], token, account)
    finally:
        # Sucesso ou falha, o temporário sai do bucket.
        storage_temp.remove(url)


def publish_post(png_paths: list, caption: str) -> dict:
    """Imagem única ou carrossel (2-10), conforme o número de PNGs.

    O container de IMAGEM também processa assíncrono, ao contrário do que
    esta função presumia: o `media_publish` respondeu "Media ID is not
    available" porque o container ainda estava `IN_PROGRESS` (ficou FINISHED
    ~3s depois). Todo container espera o `_wait_for_processing` antes de
    publish, como o Reel já fazia — a diferença entre imagem e vídeo é
    quanto tempo leva, não se há espera.

    No carrossel, cada child é um container próprio e o parent é criado só
    depois de todos estarem prontos: parent montado sobre child `IN_PROGRESS`
    falha do mesmo jeito, e aí sem dizer qual dos children era.

    O limite de 10 é validado na carga da agenda (schedule.load), antes
    de chegar aqui.
    """
    token, account = _credentials()
    urls = []
    try:
        # Um append por vez, não list comprehension: a comprehension só liga
        # o name no end, então falha no meio deixaria o `finally` vendo []
        # e os temporários já subidos ficariam órfãos no bucket.
        for p in png_paths:
            urls.append(storage_temp.put(p))
        if len(urls) == 1:
            body = _call("post", f"{account}/media", image_url=urls[0],
                           caption=caption or "", access_token=token)
            _wait_for_processing(body["id"], token)
            return _publish_container(body["id"], token, account)
        children = []
        for u in urls:
            child = _call("post", f"{account}/media", image_url=u,
                           is_carousel_item="true", access_token=token)["id"]
            _wait_for_processing(child, token)
            children.append(child)
        parent = _call("post", f"{account}/media", media_type="CAROUSEL",
                     children=",".join(children), caption=caption or "",
                     access_token=token)
        _wait_for_processing(parent["id"], token)
        return _publish_container(parent["id"], token, account)
    finally:
        for u in urls:
            storage_temp.remove(u)
