"""Utilitários compartilhados: timestamps, regex de VTT, limpeza e agrupamento de texto.
"""
import re

from . import config

# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------
def srt_ts(seconds: float) -> str:
    """Segundos -> 'hh:mm:ss,ms' (formato SRT)."""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def mmss(seconds: float) -> str:
    """Segundos -> 'mm:ss' (rótulo curto p/ curation)."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# VTT (legenda automática de rolagem do YouTube)
# ---------------------------------------------------------------------------
RE_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})")
RE_CUE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})")
RE_INLINE = re.compile(r"<(\d{2}:\d{2}:\d{2}\.\d{3})><c>(.*?)</c>")


def vtt_ts_to_sec(ts: str) -> float:
    h, m, s, ms = RE_TS.match(ts).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ---------------------------------------------------------------------------
# Limpeza de texto
# ---------------------------------------------------------------------------
# Marcações de som do YouTube. A lista original era case-sensitive e deixava
# passar [Risadas], [MÚSICA] e [Palmas] — que iam queimadas na legenda do vídeo.
RE_SOUND_TAG = re.compile(
    r"\[\s*(m[úu]sica|risos?|risadas?|aplausos?|palmas|"
    r"ru[íi]do|sil[êe]ncio|inaud[íi]vel|music|laughter|applause)\s*\]",
    re.IGNORECASE,
)


def strip_markup(txt: str) -> str:
    """Remove entidades HTML e marcações de som ([música], [risadas], ...)."""
    t = (txt.replace("&gt;", "").replace("&lt;", "").replace("&amp;", "&"))
    t = RE_SOUND_TAG.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# Contrações da fala -> forma plena na legenda. A legenda queimada é lida como
# texto, não ouvida: "tá" na tela parece error de digitação, ainda que seja
# transcrição fiel do que foi dito. Só formas em que a expansão é inequívoca —
# gíria e escolha de palavra ficam como estão, para não reescrever a fala.
_CONTRACTIONS = [
    (r"t[áa]", "está"),
    (r"t[ôo]", "estou"),
    (r"t[ãa]o", None),      # sentinela: 'tão' NÃO é contração (ver _expande)
    # 'pra'/'pro' expandem só para 'para': a contração carrega o artigo, mas
    # nem sempre ("vim pra junto do Rafael" não vira "para a junto"). Inserir
    # artigo exigiria analisar o que vem depois; 'para' está sempre correto.
    (r"pra", "para"),
    (r"pro", "para"),
    (r"c[êe]", "você"),
]

# 'né' como muleta: some junto com a vírgula que o cerca. Quando encerra a
# frase ("é isso, né?"), o ponto final entra no lugar da interrogação, porque
# a pergunta era retórica.
RE_NE_FIM = re.compile(r",?\s*n[ée]\s*\?", re.IGNORECASE)
RE_NE_MEIO = re.compile(r",\s*n[ée]\s*,", re.IGNORECASE)


# Locuções em que 'pro' é latim, não contração de "para o".
RE_PRO_LATIM = re.compile(r"\bpro\s+(labore|rata|forma|bono|indiviso)\b", re.IGNORECASE)


def _expand_contractions(t: str) -> str:
    """Troca contrações por forma plena, respeitando fronteira de palavra.

    Preserva a maiúscula inicial: "Tá bom" -> "Está bom".
    """
    # Protege as locuções antes de mexer nas contrações; devolve no end.
    reserved = []

    def _reserve(m):
        reserved.append(m.group(0))
        return f"\x00{len(reserved) - 1}\x00"

    t = RE_PRO_LATIM.sub(_reserve, t)

    for pat, target in _CONTRACTIONS:
        if target is None:      # na lista só para documentar a exclusão
            continue

        def _sub(m, target=target):
            orig = m.group(0)
            return target.capitalize() if orig[0].isupper() else target

        t = re.sub(rf"\b{pat}\b", _sub, t, flags=re.IGNORECASE)

    for i, orig in enumerate(reserved):
        t = t.replace(f"\x00{i}\x00", orig)
    return t


# Phonetic swaps automatic transcription makes on proper nouns. The same
# company comes back as Kestril, Cestril, Kestryl and Keztril — c/k, s/z,
# f/ph and i/y are the axes that actually vary in English.
_PHONETIC_EQUIVALENTS = [
    ("c", "[ck]"),
    ("k", "[ck]"),
    ("q", "[ckq]"),
    ("s", "[sz]"),
    ("z", "[sz]"),
    ("f", "(?:f|ph)"),
    ("i", "[iy]"),
    ("y", "[iy]"),
]


def _phonetic_pattern(name: str) -> str:
    """Regex matching the name and its transcription variants.

    Only table letters become character classes; every other letter stays
    literal, so the pattern cannot loosen far enough to swallow a real word
    ("kestrel" must not become "Kestril").
    """
    parts = []
    for ch in name.lower():
        for letter, char_class in _PHONETIC_EQUIVALENTS:
            if ch == letter:
                parts.append(char_class)
                break
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


# Company names that are also ordinary English words. Recasing them damages
# the sentence, so they stay out of the correction. Short and explicit list:
# guessing "is this a common word?" without a dictionary errs more often than
# it helps, and a name missing here only loses automatic capitalisation.
_COMMON_WORDS = {
    "apple", "orange", "amazon", "oracle", "square", "stripe", "slack",
    "meta", "shell", "sun", "gap", "target", "chase", "visa", "delta",
    "arc", "bolt", "lime",
}


def _is_common_word(name: str) -> bool:
    return name.strip().lower() in _COMMON_WORDS


def fix_proper_nouns(txt: str, names: list) -> str:
    """Rewrite proper nouns to the official spelling from episode.json.

    Transcription errs on proper nouns and the caption is burned into the
    video, so an uncorrected name ships (Cestril/Kestryl for Kestril).

    Only INVENTED names are corrected: a company called "Delta" or "Shell" is
    already transcribed right, and recasing it would damage the sentence ("the
    delta of the risk" turning into "the Delta of the risk").
    """
    for name in names or []:
        name = str(name).strip()
        if len(name) < 4:
            continue
        pat = re.compile(rf"\b{_phonetic_pattern(name)}\b", re.IGNORECASE)

        def _sub(m, name=name):
            # Already the official spelling apart from case: leave it.
            return name if m.group(0).lower() != name.lower() else m.group(0)

        matches = pat.findall(txt)
        # No wrong variant, only the name itself, perhaps lowercase: the case
        # is all there is to fix, and even that stays out when the name is an
        # ordinary word ("a shell company").
        if matches and all(a.lower() == name.lower() for a in matches):
            if not _is_common_word(name):
                txt = re.sub(rf"\b{re.escape(name)}\b", name, txt,
                             flags=re.IGNORECASE)
            continue
        txt = pat.sub(_sub, txt)
    return txt


def clean_caption(txt: str) -> str:
    """Limpa a legenda para exibição: remove repetição, muletas e contrações.

    Ex.: 'eu eu gosto' -> 'eu gosto'; remove 'eh/ah/uhum/hã' e 'né';
    'tá' -> 'está'. (Não altera o áudio — só o texto que aparece na tela.)
    """
    t = " " + txt.strip() + " "
    # duas passadas p/ pegar triplas ('a a a')
    t = re.sub(r"\b(\w{1,5})\s+\1\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\w{1,5})\s+\1\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+(eh|ah|uhum|hã)\s*,?\s*", " ", t, flags=re.IGNORECASE)
    # 'né' antes das contrações: RE_NE_* casa a forma falada, não a expandida.
    t = RE_NE_FIM.sub(".", t)
    t = RE_NE_MEIO.sub(", ", t)
    t = _expand_contractions(t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.?!])", r"\1", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Agrupamento de words (t, palavra) -> segmentos {start, end, text}
# ---------------------------------------------------------------------------
def group_words_into_segments(words):
    """Agrupa uma lista de (tempo, palavra) em segmentos de frase.

    Quebra por pausa (SEG_MAX_GAP), duração (SEG_MAX_DUR), tamanho
    (SEG_MAX_CHARS) ou pontuação final.
    """
    segs = []
    cur = []
    for t, w in words:
        w = strip_markup(w)
        if not w:
            continue
        if not cur:
            cur = [(t, w)]
            continue
        prev = cur[-1][0]
        text = " ".join(x[1] for x in cur)
        ends = cur[-1][1].endswith((".", "?", "!"))
        too_long = (t - cur[0][0]) > config.SEG_MAX_DUR or len(text) > config.SEG_MAX_CHARS
        if (t - prev) > config.SEG_MAX_GAP or ends or too_long:
            segs.append({"start": round(cur[0][0], 3),
                         "end": round(prev + config.SEG_END_PAD, 3),
                         "text": text})
            cur = [(t, w)]
        else:
            cur.append((t, w))
    if cur:
        segs.append({"start": round(cur[0][0], 3),
                     "end": round(cur[-1][0] + config.SEG_END_PAD, 3),
                     "text": " ".join(x[1] for x in cur)})
    return segs
