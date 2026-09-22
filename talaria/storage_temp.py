"""Hospedagem temporária no S3 — a Graph API busca a mídia numa URL pública.

O Instagram não aceita upload binário direto: o container de mídia recebe uma
URL e o Instagram baixa de lá. O arquivo sobe pra `tmp-publish/`, a URL é
assinada com validade de 1h (tempo de o Instagram processar) e o chamador
remove no `finally` — sucesso ou falha.
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
    """Cliente S3, apontando para outro provedor quando configurado.

    Cloudflare R2, MinIO e afins falam a mesma API do S3 — só mudam de
    endereço. Sem `S3_ENDPOINT_URL` o boto3 usa a AWS, que é o padrão; com
    ele, trocar de provedor é editar o `.env`, não o código.

    A assinatura é fixada em SigV4: sem isso o boto3 pode assinar em SigV2, e
    o R2 recusa a URL com 401. O sintoma apareceria só na publicação, como
    container que falha — sem nada apontando para a assinatura.
    """
    return boto3.client("s3",
                        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
                        config=Config(signature_version="s3v4"))


def put(path: str) -> str:
    """Sobe o arquivo e devolve a URL assinada que o Instagram vai buscar.

    O uuid no name evita colisão entre publicações simultâneas do mesmo slug
    (retry manual em outra janela, por exemplo).
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
    """Apaga o temporário. Melhor esforço: falha aqui só avisa, não aborta.

    O arquivo não é segredo e a URL expira em 1h — um resíduo no bucket é o
    pior caso aceitável. Derrubar uma publicação já feita porque o delete
    falhou seria trocar um problema pequeno por um grande.
    """
    try:
        bucket = _bucket()
        partes = urlparse(url)
        key = unquote(partes.path.lstrip("/"))
        # Onde o bucket aparece depende do estilo da URL: a AWS usa
        # virtual-hosted (`bucket.host/key`) e o R2/MinIO usam path-style
        # (`host/bucket/key`). Quem decide é o HOST, não o texto do path —
        # olhar só o path erra quando o bucket se chama como o PREFIX
        # ("tmp-publish"), cortando o prefixo real da key. Nos dois casos o
        # delete miraria objeto inexistente e falharia calado, deixando a
        # mídia acessível pela URL até expirar.
        if not partes.hostname.startswith(bucket + "."):
            if key.startswith(bucket + "/"):
                key = key[len(bucket) + 1:]
        _client().delete_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001
        print(f"[storage] !! não removi o temporário ({e}) — "
              f"resíduo em {PREFIX}, expira sozinho da URL em 1h")
