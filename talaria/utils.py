"""Utilitários compartilhados: timestamps, regex de VTT, limpeza e agrupamento de texto.

Consolida lógica que estava duplicada em transcribe/vtt_to_segments/
clean_transcript/render_cortes.
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
    """Segundos -> 'mm:ss' (rótulo curto p/ curadoria)."""
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
RE_SOM = re.compile(
    r"\[\s*(m[úu]sica|risos?|risadas?|aplausos?|palmas|"
    r"ru[íi]do|sil[êe]ncio|inaud[íi]vel|music|laughter|applause)\s*\]",
    re.IGNORECASE,
)


def strip_markup(txt: str) -> str:
    """Remove entidades HTML e marcações de som ([música], [risadas], ...)."""
    t = (txt.replace("&gt;", "").replace("&lt;", "").replace("&amp;", "&"))
    t = RE_SOM.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# Contrações da fala -> forma plena na legenda. A legenda queimada é lida como
# texto, não ouvida: "tá" na tela parece erro de digitação, ainda que seja
# transcrição fiel do que foi dito. Só formas em que a expansão é inequívoca —
# gíria e escolha de palavra ficam como estão, para não reescrever a fala.
_CONTRACOES = [
    (r"t[áa]", "está"),
    (r"t[ôo]", "estou"),
    (r"t[ãa]o", None),      # sentinela: 'tão' NÃO é contração (ver _expande)
    # 'pra'/'pro' expandem só para 'para': a contração carrega o artigo, mas
    # nem sempre ("vim pra junto do Gustavo" não vira "para a junto"). Inserir
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


def _expande_contracoes(t: str) -> str:
    """Troca contrações por forma plena, respeitando fronteira de palavra.

    Preserva a maiúscula inicial: "Tá bom" -> "Está bom".
    """
    # Protege as locuções antes de mexer nas contrações; devolve no fim.
    reservas = []

    def _guarda(m):
        reservas.append(m.group(0))
        return f"\x00{len(reservas) - 1}\x00"

    t = RE_PRO_LATIM.sub(_guarda, t)

    for pat, alvo in _CONTRACOES:
        if alvo is None:      # na lista só para documentar a exclusão
            continue

        def _sub(m, alvo=alvo):
            orig = m.group(0)
            return alvo.capitalize() if orig[0].isupper() else alvo

        t = re.sub(rf"\b{pat}\b", _sub, t, flags=re.IGNORECASE)

    for i, orig in enumerate(reservas):
        t = t.replace(f"\x00{i}\x00", orig)
    return t


# Trocas fonéticas que a transcrição automática faz em nome próprio. A mesma
# empresa sai como Zarvik, Zarvic, Zarvyk e Ilzarvik — varia na vogal interna,
# no y/i, e no `l` que a transcrição insere.
_EQUIV_FONETICA = [
    ("y", "[yieu]"),
    ("i", "[yieu]"),
    ("e", "[yiea]"),
    ("o", "[oua]"),
    ("u", "[oua]"),
    ("s", "[sz]"),
    ("z", "[sz]"),
    ("c", "[ckq]"),
    ("k", "[ckq]"),
]


def _padrao_fonetico(nome: str) -> str:
    """Regex que casa o nome e suas variantes de transcrição.

    Só as letras internas viram classe de caractere; consoante fora da tabela
    entra literal, para o padrão não ficar frouxo a ponto de casar palavra
    comum ("zarpa" não pode virar "Zarvik").
    """
    partes = []
    for ch in nome.lower():
        for letra, classe in _EQUIV_FONETICA:
            if ch == letra:
                partes.append(classe)
                break
        else:
            partes.append(re.escape(ch))
    # 'l' extra no meio ("Ilzarvik" para "Zarvik") é erro comum de transcrição.
    return partes[0] + "l?" + "".join(partes[1:])


# Nomes de empresa que também são palavra do português. Reescrever a caixa
# deles estraga a frase, então ficam de fora da correção. Lista curta e
# explícita: adivinhar "é palavra comum?" sem dicionário erra mais do que
# acerta, e um nome faltando aqui só perde a capitalização automática.
_PALAVRAS_COMUNS = {
    "matriz", "acho", "praia", "ponte", "campo", "norte", "sul", "vida",
    "casa", "porto", "rede", "ideia", "meta", "alma", "onda", "raiz",
}


def _e_palavra_comum(nome: str) -> bool:
    return nome.strip().lower() in _PALAVRAS_COMUNS


def corrige_nomes(txt: str, nomes: list) -> str:
    """Reescreve nome próprio na grafia oficial vinda do episodio.json.

    A transcrição erra nome próprio e a legenda é queimada no vídeo — sem isto
    o erro vai ao ar (Zarvic/Ilzarvik no lugar de Zarvik).

    Só entra nome INVENTADO: quando a empresa se chama "Matriz" ou "Acho", a
    transcrição acerta sozinha e reescrever estragaria a frase ("a matriz de
    risco" viraria "a Matriz de risco"). O teste é a própria grafia oficial
    aparecer no texto — aí o padrão fonético não tem o que consertar e só faria
    estrago.
    """
    for nome in nomes or []:
        nome = str(nome).strip()
        if len(nome) < 4:
            continue
        pat = re.compile(rf"\b{_padrao_fonetico(nome)}\b", re.IGNORECASE)

        def _sub(m, nome=nome):
            # Grafia já correta (ou só diferindo por caixa): não mexe.
            return nome if m.group(0).lower() != nome.lower() else m.group(0)

        achados = pat.findall(txt)
        # Nenhuma variante errada: só o próprio nome, talvez em caixa baixa.
        # Aí a única coisa a fazer é acertar a caixa — e mesmo isso fica de
        # fora quando o nome é palavra do idioma ("a matriz de risco"), que a
        # transcrição escreveu certo e virar "a Matriz" estragaria.
        if achados and all(a.lower() == nome.lower() for a in achados):
            if not _e_palavra_comum(nome):
                txt = re.sub(rf"\b{re.escape(nome)}\b", nome, txt,
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
    t = _expande_contracoes(t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.?!])", r"\1", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Agrupamento de palavras (t, palavra) -> segmentos {start, end, text}
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
