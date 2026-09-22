"""Temporary S3 hosting — the Graph API fetches the media from a public URL.

Instagram accepts no direct binary upload: the media container takes a URL and
Instagram downloads from there. The file goes up to `tmp-publish/`, the URL is
signed with a 1h validity (time for Instagram to process it) and the caller
removes it in `finally` — success or failure.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config

EXPIRY_S = 3600
PREFIX = "tmp-publish/"


def _bucket() -> str:
    bucket = os.environ.get("S3_PUBLISH_BUCKET", "")
    if not bucket:
        raise RuntimeError(
            "S3_PUBLISH_BUCKET não definido no ambiente (.env) — é o bucket "
            "temporário de onde o Instagram baixa a mídia."
        )
    return bucket


def _client():
    """S3 client, pointed at another provider when one is configured.

    Cloudflare R2, MinIO and the like speak the same S3 API — only the address
    changes. Without `S3_ENDPOINT_URL` boto3 uses AWS, which is the default;
    with it, switching provider means editing `.env`, not the code.

    The signature is pinned to SigV4: without that boto3 may sign with SigV2 and
    R2 refuses the URL with a 401. The symptom would only surface at publishing
    time, as a failing container — with nothing pointing at the signature.
    """
    return boto3.client("s3",
                        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
                        config=Config(signature_version="s3v4"))


def put(path: str) -> str:
    """Uploads the file and returns the signed URL Instagram will fetch.

    The uuid in the name avoids a collision between simultaneous publications
    of the same slug (a manual retry in another window, for instance).
    """
    s3 = _client()
    key = f"{PREFIX}{uuid.uuid4().hex}_{os.path.basename(path)}"
    s3.upload_file(path, _bucket(), key)
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=EXPIRY_S,
    )


def remove(url: str) -> None:
    """Deletes the temporary file. Best effort: a failure warns, never aborts.

    The file is not secret and the URL expires in 1h — a leftover in the bucket
    is the acceptable worst case. Bringing down a publication already made
    because the delete failed would trade a small problem for a big one.
    """
    try:
        bucket = _bucket()
        parts = urlparse(url)
        key = unquote(parts.path.lstrip("/"))
        # Where the bucket appears depends on the URL style: AWS uses
        # virtual-hosted (`bucket.host/key`) while R2/MinIO use path-style
        # (`host/bucket/key`). The HOST decides, not the path text — looking at
        # the path alone gets it wrong when the bucket is named like the PREFIX
        # ("tmp-publish"), cutting the key's real prefix. Either way the delete
        # would target a non-existent object and fail quietly, leaving the media
        # reachable by URL until it expires.
        if not parts.hostname.startswith(bucket + "."):
            if key.startswith(bucket + "/"):
                key = key[len(bucket) + 1:]
        _client().delete_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001
        print(f"[storage] !! não removi o temporário ({e}) — "
              f"resíduo em {PREFIX}, expira sozinho da URL em 1h")
