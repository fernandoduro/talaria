"""Hashtags da descrição — regra determinística, não julgamento editorial.

Hashtags não aceitam espaço nem acento: "São Bento" -> #SaoBento.
Três são fixas em todo episódio; city e company variam.
"""
from __future__ import annotations

import re
import unicodedata

# Hashtags presentes em todo episódio — identidade do canal. Troque pelas
# suas: o resto da regra (city, company) não depende destes valores.
CHANNEL_TAGS = ["#MeuPodcast", "#Empreendedorismo", "#Startups"]


def slug(texto: str) -> str:
    """'Ribeirão Açaí' -> 'RibeiraoAcai'. Remove acento e não-alfanumérico."""
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    palavras = re.findall(r"[A-Za-z0-9]+", sem_acento)
    return "".join(p[0].upper() + p[1:] if p else "" for p in palavras)


def build(city: str, company: str, fallback_tema: str = "") -> list:
    """Lista de hashtags: as três fixas + city + company (ou tema)."""
    tags = list(CHANNEL_TAGS)
    for valor in (city, company or fallback_tema):
        s = slug(valor)
        if s and f"#{s}" not in tags:
            tags.append(f"#{s}")
    return tags


def format_line(city: str, company: str, fallback_tema: str = "") -> str:
    """Linha pronta para a descrição."""
    return " ".join(build(city, company, fallback_tema))
