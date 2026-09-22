"""Publishing to Instagram through the Graph API — Reels and feed posts.

The Graph API accepts no binary upload: the container fetches the media from a
public URL (storage_temp). Video processes asynchronously — poll with a timeout,
and the ERROR/EXPIRED terminal states are an explicit failure carrying the
literal status (without that the command hangs forever on a silently rejected
video).
"""
from __future__ import annotations

import os
import time

import requests

from . import storage_temp

# Meta has TWO flows for publishing to Instagram, on distinct hosts:
#
#   EAAG... token (Facebook login)  -> graph.facebook.com, Business account
#                                      linked to a Page
#   IGAA... token (Instagram login) -> graph.instagram.com, Business account
#                                      directly, with no Page in between
#
# The endpoints (`<account>/media`, `media_publish`, the `status_code` poll) are
# the same on both; only the host changes. Sending one flow's token to the other
# flow's host returns "Cannot parse access token", which does not say what the
# problem is — hence choosing by prefix instead of pinning one host.
GRAPH_FACEBOOK = "https://graph.facebook.com/v21.0"
GRAPH_INSTAGRAM = "https://graph.instagram.com/v21.0"


def host_for_token(token: str) -> str:
    """The host that serves this token, chosen by prefix.

    An unknown prefix falls back to Facebook, which was the default before this
    function existed: the API's own error message beats a guess of ours.
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
    """GET/POST on the Graph API; an error becomes an exception with the API's
    own message.

    The Graph error body arrives as {"error": {"message": ...}} even with a 200
    status in some flows — which is why the body decides alongside the status.
    """
    fn = requests.post if method == "post" else requests.get
    host = host_for_token(params.get("access_token", ""))
    r = fn(f"{host}/{path}", params=params, timeout=TIMEOUT_HTTP_S)
    # A non-JSON body (a proxy error page on a 502, a truncated response) must
    # not blow up here: it would trade "Graph API: 502" for a JSONDecodeError
    # that says nothing about what happened, right in the middle of the incident.
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {}
    if r.status_code >= 400 or "error" in body:
        msg = (body.get("error") or {}).get("message") or r.text
        raise RuntimeError(f"Graph API ({path}): {msg}")
    return body


def _wait_for_processing(container_id: str, token: str) -> None:
    """Polls until FINISHED. ERROR/EXPIRED and timeout are explicit failures."""
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
    """Uploads the video, creates the REELS container, waits, and publishes."""
    token, account = _credentials()
    url = storage_temp.put(video_path)
    try:
        body = _call("post", f"{account}/media", media_type="REELS",
                       video_url=url, caption=caption or "",
                       access_token=token)
        _wait_for_processing(body["id"], token)
        return _publish_container(body["id"], token, account)
    finally:
        # Success or failure, the temporary file leaves the bucket.
        storage_temp.remove(url)


def publish_post(png_paths: list, caption: str) -> dict:
    """Single image or carousel (2-10), according to the number of PNGs.

    The IMAGE container also processes asynchronously, contrary to what this
    function assumed: `media_publish` answered "Media ID is not available"
    because the container was still `IN_PROGRESS` (it turned FINISHED ~3s
    later). Every container waits on `_wait_for_processing` before publishing,
    as the Reel already did — the difference between image and video is how
    long it takes, not whether there is a wait.

    In a carousel each child is its own container and the parent is only created
    once all of them are ready: a parent built over an `IN_PROGRESS` child fails
    the same way, and then without saying which child it was.

    The limit of 10 is validated when the schedule loads (schedule.load), before
    reaching here.
    """
    token, account = _credentials()
    urls = []
    try:
        # One append at a time, not a list comprehension: the comprehension
        # only binds the name at the end, so a failure partway would leave
        # `finally` seeing [] and already-uploaded temporaries orphaned.
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
