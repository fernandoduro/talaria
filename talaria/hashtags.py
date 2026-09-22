"""Hashtags da descrição — regra determinística, não julgamento editorial.

Hashtags não aceitam espaço nem acento: "São Bento" -> #SaoBento.
Três são fixas em todo episódio; city e company variam.
"""
from __future__ import annotations

import re
import unicodedata

# Hashtags presentes em todo episódio — identity do canal. Troque pelas
# suas: o resto da regra (city, company) não depende destes valores.
CHANNEL_TAGS = ["#MeuPodcast", "#Empreendedorismo", "#Startups"]


def slug(text: str) -> str:
    """'Ribeirão Açaí' -> 'RibeiraoAcai'. Remove acento e não-alfanumérico."""
    if not text:
        return ""
    unaccented = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    words = re.findall(r"[A-Za-z0-9]+", unaccented)
    return "".join(p[0].upper() + p[1:] if p else "" for p in words)


def build(city: str, company: str, fallback_topic: str = "") -> list:
    """Lista de hashtags: as três fixas + city + company (ou tema)."""
    tags = list(CHANNEL_TAGS)
    for value in (city, company or fallback_topic):
        s = slug(value)
        if s and f"#{s}" not in tags:
            tags.append(f"#{s}")
    return tags


def format_line(city: str, company: str, fallback_topic: str = "") -> str:
    """Linha pronta para a descrição."""
    return " ".join(build(city, company, fallback_topic))
