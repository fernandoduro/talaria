"""Description hashtags — a deterministic rule, not editorial judgement.

Hashtags take neither spaces nor accents: "São Bento" -> #SaoBento.
Three are fixed in every episode; city and company vary.
"""
from __future__ import annotations

import re
import unicodedata

# Hashtags present in every episode — channel identity. Swap in your own:
# the rest of the rule (city, company) does not depend on these values.
CHANNEL_TAGS = ["#MeuPodcast", "#Empreendedorismo", "#Startups"]


def slug(text: str) -> str:
    """'Ribeirão Açaí' -> 'RibeiraoAcai'. Strips accents and non-alphanumerics."""
    if not text:
        return ""
    unaccented = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    words = re.findall(r"[A-Za-z0-9]+", unaccented)
    return "".join(p[0].upper() + p[1:] if p else "" for p in words)


def build(city: str, company: str, fallback_topic: str = "") -> list:
    """The hashtag list: the three fixed ones + city + company (or topic)."""
    tags = list(CHANNEL_TAGS)
    for value in (city, company or fallback_topic):
        s = slug(value)
        if s and f"#{s}" not in tags:
            tags.append(f"#{s}")
    return tags


def format_line(city: str, company: str, fallback_topic: str = "") -> str:
    """A line ready for the description."""
    return " ".join(build(city, company, fallback_topic))
