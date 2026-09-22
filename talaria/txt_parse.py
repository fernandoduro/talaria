"""Parser de transcrição .txt com timestamps (formato YouTube "copiar transcrição").

Formato expected — timestamp sozinho numa linha, texto nas lines seguintes:

    0:10
    E aí, pessoal, hoje a gravação é aqui em Ribeirão Açaí...
    0:15
    Vamos conversar um pouco sobre a Zarvik e a trajetória dela, né...

O marcador ">>" indica troca de interlocutor e é preservado como flag no
segmento (turn=True), útil na curation: clip que começa em troca de turno
tende a ter fronteira natural.

Atenção: ">>" diz QUE trocou de interlocutor, não QUEM passou a falar. Por
isso a identity é resolvida uma única vez, sobre o episódio inteiro
(resolve_speakers), e gravada em cada segmento como speaker="host" ou
"convidado". Deduzir o falante dentro da fatia de um clip não funciona: o
clip que começa no meio de uma response não tem nenhum ">>" para se orientar.

Saída: [{start, end, text, turn, speaker}]. Os três primeiros campos são
idênticos aos do vtt_parse/whisper, para o resto do pipeline não distinguir a
origin; `speaker` é exclusivo desta origin, porque só a transcrição do YouTube
traz o marcador de troca.
"""
from __future__ import annotations

import re

from . import utils

# "0:10", "10:00", "1:02:03" — sozinho na linha
RE_TS_LINE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _ts_to_sec(m: re.Match) -> float:
    a, b, c = m.group(1), m.group(2), m.group(3)
    if c is None:            # M:SS  -> minuto:segundo
        return int(a) * 60 + int(b)
    return int(a) * 3600 + int(b) * 60 + int(c)   # H:MM:SS


def parse_txt(path: str, total_duration: float | None = None) -> list:
    """Lê o .txt e retorna segmentos [{start, end, text, turn, speaker}].

    O end de cada bloco é o início do próximo (a transcrição não marca end).
    O último bloco usa total_duration, quando informada; senão estima pelo
    ritmo de fala (config.WORDS_PER_MINUTE).
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    blocks = []   # (start, [lines de texto])
    cur_start, buf = None, []
    for raw in lines:
        line = raw.strip()
        m = RE_TS_LINE.match(line)
        if m:
            if cur_start is not None:
                blocks.append((cur_start, buf))
            cur_start, buf = _ts_to_sec(m), []
        elif line and cur_start is not None:
            buf.append(line)
    if cur_start is not None:
        blocks.append((cur_start, buf))

    raw = []
    for i, (start, buf) in enumerate(blocks):
        text = " ".join(buf).strip()
        if not text:
            continue
        turn = text.startswith(">>")
        text = utils.strip_markup(text.lstrip("> ").strip())
        if not text:
            continue
        if i + 1 < len(blocks):
            end = float(blocks[i + 1][0])
        elif total_duration:
            end = float(total_duration)
        else:
            end = start + max(1.0, len(text.split()) / 145 * 60)
        raw.append({"start": float(start), "end": round(end, 3),
                    "text": text, "turn": turn})
    return resolve_speakers(regroup_into_sentences(raw))


def regroup_into_sentences(blocks: list) -> list:
    """Reagrupa blocos de ~5s em segmentos de FRASE.

    A transcrição do YouTube quebra a cada ~5s, no meio da frase ("...o meu
    co-host aqui, o" / "Fulano, fazendo..."). Isso quebra duas coisas:
    a legenda queimada (texto cortado na tela) e a validação de fronteira de
    clip (que exige início/end em frase completa).

    Junta blocos até encontrar pontuação final, troca de interlocutor (>>),
    ou os limites de duração/tamanho de config.
    """
    from . import config

    segs, cur = [], None
    for b in blocks:
        if cur is None:
            cur = dict(b)
            continue
        ends = cur["text"].rstrip().endswith((".", "?", "!"))
        too_long = (b["end"] - cur["start"]) > config.SEG_MAX_DUR * 2
        too_big = len(cur["text"]) > config.SEG_MAX_CHARS * 2
        if ends or b["turn"] or too_long or too_big:
            segs.append(cur)
            cur = dict(b)
        else:
            cur["text"] = (cur["text"] + " " + b["text"]).strip()
            cur["end"] = b["end"]
    if cur:
        segs.append(cur)
    return segs


# Rótulos de falante gravados em cada segmento.
HOST = "host"
GUEST = "guest"


def resolve_speakers(segs: list) -> list:
    """Atribui speaker="host"/"convidado" a cada segmento, olhando o episódio.

    O episódio abre com os apresentadores introduzindo o tema e o convidado —
    logo, o primeiro segmento é sempre host. Cada turn=True (marcador ">>") alterna o falante a partir dali.

    A resolução é GLOBAL de propósito. Feita dentro da fatia de um clip, ela
    erra: um clip que começa no meio de uma response não contém nenhum ">>" e
    seria atribuído todo ao host, zerando a fração de fala do convidado — o
    oposto da realidade. Resolvendo aqui, cada segmento carrega a atribuição
    absoluta e qualquer fatia posterior a herda correta.

    Muta e devolve a mesma lista.
    """
    current = HOST
    for i, s in enumerate(segs):
        # O primeiro segmento é host mesmo que venha marcado com ">>" — o
        # marcador ali só indica que a transcrição abriu num bloco de fala.
        if i > 0 and s.get("turn"):
            current = GUEST if current == HOST else HOST
        s["speaker"] = current
    return segs
