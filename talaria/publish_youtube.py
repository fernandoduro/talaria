"""Uploading Shorts through the YouTube Data API v3.

OAuth2 with a refresh token: authorisation (the channel owner's consent) is
manual and one-off, via scripts/youtube_auth.py — the pipeline never opens a
browser. An upload costs ~1600 units of the 10k daily quota; at the typical
volume (a few Shorts a week) that nowhere near touches the limit.
"""
from __future__ import annotations

import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Category "People & Blogs" — YouTube requires one; it is the videocast one.
CATEGORY_ID = "22"

# Privacy values YouTube accepts. `unlisted` serves to check the Short on the
# channel before opening it up — useful at a premiere and when testing a schedule.
PRIVACY_VALUES = ("public", "unlisted", "private")
DEFAULT_PRIVACY = "public"


def privacy() -> str:
    """The Short's privacy, from `.env`. Without the variable, public.

    An invalid value ABORTS rather than falling back to the default: a typo in
    `YT_PRIVACY=unlised` would publish openly at exactly the moment the
    opposite was asked for, and a public video cannot be unpublished unseen.
    """
    value = (os.environ.get("YT_PRIVACY") or "").strip().lower()
    if not value:
        return DEFAULT_PRIVACY
    if value not in PRIVACY_VALUES:
        raise ValueError(
            f"YT_PRIVACY={value!r} is not valid — use "
            f"{', '.join(PRIVACY_VALUES)}."
        )
    return value


def _credentials() -> Credentials:
    path = os.environ.get("YT_CLIENT_SECRET_PATH", "")
    refresh = os.environ.get("YT_REFRESH_TOKEN", "")
    missing = [n for n, v in (("YT_CLIENT_SECRET_PATH", path),
                             ("YT_REFRESH_TOKEN", refresh)) if not v]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} not defined in the environment (.env). Run "
            f"'python scripts/youtube_auth.py <client_secret.json>' once to "
            f"generate the refresh token."
        )
    with open(path, encoding="utf-8") as f:
        cs = json.load(f)["installed"]
    return Credentials(None, refresh_token=refresh,
                       token_uri=cs["token_uri"], client_id=cs["client_id"],
                       client_secret=cs["client_secret"], scopes=SCOPES)


def upload(video_path: str, title: str, description: str) -> dict:
    """Uploads the video (resumable) and returns the Short's id and URL."""
    service = build("youtube", "v3", credentials=_credentials())
    body = {
        "snippet": {"title": title, "description": description,
                    "categoryId": CATEGORY_ID},
        "status": {"privacyStatus": privacy(),
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    req = service.videos().insert(part="snippet,status", body=body,
                                  media_body=media)
    response = None
    while response is None:
        _, response = req.next_chunk()
    vid = response["id"]
    return {"id": vid, "url": f"https://www.youtube.com/shorts/{vid}"}
