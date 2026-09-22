"""Registro do que já foi published — a trava contra post duplicado.

A unidade do registro é (platform, slug): um clip publica em YouTube E
Reels, e se só uma das duas passou, o retry do dia seguinte publica só a que
faltou: pendência por item republicaria a que já foi.

Cada sucesso grava NA HORA, atomicamente. Registrar só no fim do lote deixa
uma janela: processo morto no meio e a próxima execução duplica o que já
tinha saído — post duplicado não tem correção depois de published.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import config, layout


def load(pd: str) -> dict:
    """Lê o registro. Arquivo corrompido ABORTA — fail closed.

    JSON inválido nunca é tratado como "nada published ainda": isso
    republicaria o histórico inteiro. `projects/` é git-ignored, então não há
    backup no git — a mensagem manda conferir os perfis das plataformas antes
    de recriar o arquivo.
    """
    path = layout.published(pd)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"{path} está corrompido ({e}). Não vou assumir 'nada "
                f"publicado' — isso republicaria tudo. Confira o que já está "
                f"no ar nos perfis das plataformas e recrie o arquivo à mão."
            )


def is_published(reg: dict, platform: str, slug: str) -> bool:
    return any(r.get("slug") == slug for r in reg.get(platform, []))


def record(pd: str, platform: str, slug: str, id_post: str,
             url: str) -> str:
    """Acrescenta UMA publicação e grava na hora, atomicamente.

    temp + os.replace no mesmo filesystem: ou o arquivo novo inteiro, ou o
    antigo intacto — nunca um JSON pela metade (que o `load` recusaria).
    """
    reg = load(pd)
    reg.setdefault(platform, []).append({
        "slug": slug,
        "id": id_post,
        "url": url,
        "published_at": dt.datetime.now(
            ZoneInfo(config.PUBLISH_TZ)).isoformat(timespec="seconds"),
    })
    path = layout.ensure_dir(layout.published(pd))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path
