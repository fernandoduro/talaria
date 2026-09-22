"""Estado da curation iterativa — rounds até fechar a target de cortes approved.

Regras de state:
- trecho rejeitado fica queimado permanentemente, não volta em nenhuma rodada;
- exclusão por SOBREPOSIÇÃO DE TEMPO, não por texto — um clip 10s adiante de
  um rejeitado é essencialmente o mesmo trecho;
- ajuste de tempo não é rejeição, é aprovação com correção.
"""
from __future__ import annotations

import json
import os
import re

from . import config, layout

FILE_NAME = "curation.json"

# Fração de sobreposição a partir da qual duas spans são "o mesmo trecho".
OVERLAP_THRESHOLD = 0.30


def new_state(target: int = 5) -> dict:
    return {"target": target, "approved": [], "rejected": [], "rounds": 0}


def overlaps(a: tuple, b: tuple, threshold: float = OVERLAP_THRESHOLD) -> bool:
    """True se as spans (start, end) se sobrepõem acima do threshold.

    O threshold é relativo à MENOR das duas spans — assim um clip curto contido
    num rejeitado longo account como sobreposição.
    """
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    overlap = end - start
    if overlap <= 0:
        return False
    smaller = min(a[1] - a[0], b[1] - b[0])
    if smaller <= 0:
        return False
    return (overlap / smaller) >= threshold


def burned_spans(state: dict) -> list:
    """Todas as spans (start, end) indisponíveis para novas propostas."""
    spans = []
    for group in ("approved", "rejected"):
        for item in state.get(group, []):
            if "start" in item and "end" in item:
                spans.append((float(item["start"]), float(item["end"])))
    return spans


def is_burned(span: tuple, state: dict) -> bool:
    return any(overlaps(span, q) for q in burned_spans(state))


def slots_left(state: dict) -> int:
    return max(0, state["target"] - len(state.get("approved", [])))


def load(project_dir: str, target: int = 5) -> dict:
    path = layout.curation(project_dir)
    if not os.path.exists(path):
        return new_state(target)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, state: dict) -> str:
    path = layout.ensure_dir(layout.curation(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


# Approximate-figure markers. Lifted into a clip on its own, "roughly 570,
# 580" reads as a categorical claim the speaker never made. The digit must
# follow within the same sentence, so the 40-character window stops before
# sentence-ending punctuation.
RE_HEDGED_NUMBER = re.compile(
    r"\b(about|around|approximately|roughly|some|maybe|I think|"
    r"if I remember|more or less|or so|give or take)\b"
    r"[^.!?]{0,40}?\d",
    re.IGNORECASE,
)


def has_hedged_number(text: str) -> bool:
    """True se o texto contém número dito com aproximação ou dúvida."""
    return bool(RE_HEDGED_NUMBER.search(text or ""))


def _valid_boundary(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t coincide com o início ou o end de algum segmento."""
    for s in segs:
        if abs(s["start"] - t) <= tol or abs(s["end"] - t) <= tol:
            return True
    return False


# Pontuação que encerra frase. Reticências contam: a fala fica suspensa, mas
# não cortada no meio de uma palavra.
RE_SENTENCE_END = re.compile(r"[.!?…]\s*$|\.\.\.\s*$")


def _ends_sentence(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t cai no end de um segmento cujo texto encerra uma frase.

    A transcrição do YouTube quebra bloco por TEMPO, não por pontuação — um
    bloco pode acabar no meio da frase e emendar no seguinte. Casar só com o
    limite do bloco (_valid_boundary) aceitava clip terminando em palavra
    solta; aqui a pontuação do texto é que decide.
    """
    for s in segs:
        if abs(s["end"] - t) <= tol:
            return bool(RE_SENTENCE_END.search(s["text"].strip()))
    return False


def segments_in_clip(span: tuple, segs: list) -> list:
    """Segmentos que intersectam a span (start, end) do clip."""
    start, end = span
    return [s for s in segs if s["end"] > start and s["start"] < end]


def guest_speech_fraction(span: tuple, segs: list) -> float:
    """Fração do tempo do clip em que o convidado fala.

    Lê o campo `speaker`, resolvido globalmente no parse (txt_parse.
    resolve_speakers). NÃO deduz o falante alternando um booleano inside da
    fatia: o marcador '>>' diz QUE trocou de interlocutor, não QUEM fala, e um
    clip que começa no meio de uma response não tem nenhum '>>' inside dele —
    a alternância local devolvia 0.0 justamente para os cortes 100% convidado.

    Segmentos sem `speaker` (origin vtt/Whisper, que não tem marcador de troca,
    ou dado gravado antes desta correção) são ignorados no cálculo. Se NENHUM
    segmento do clip tiver `speaker`, o protagonismo é inaferível e a função
    devolve 1.0 — o valor que não dispara o alerta em clip_warnings(). Devolver
    0.0 acusaria de "convidado fala 0%" todo clip vindo do Whisper, o mesmo
    alerta falso que esta correção existe para eliminar; quando não dá para
    medir, o julgamento fica com o prompt de cortes e o gestor.
    """
    inside = segments_in_clip(span, segs)
    if not inside:
        return 0.0
    total = guest_dur = 0.0
    for s in inside:
        speaker = s.get("speaker")
        if speaker is None:
            continue
        dur = min(s["end"], span[1]) - max(s["start"], span[0])
        if dur <= 0:
            continue
        total += dur
        if speaker == "guest":
            guest_dur += dur
    if not total:
        return 1.0        # inaferível: não alerta
    return guest_dur / total


def sentence_ends(segs: list, start: float, lo: float, hi: float) -> list:
    """Fins de frase entre `lo` e `hi` que dão clip de duração válida.

    Devolve [(instante, duration, contexto)] ordenado por instante. Serve para
    escolher onde terminar um clip sem cortar a fala no meio — o trabalho que
    nesta sessão foi feito à mão, procurando pontuação no texto.

    O instante é interpolado pela posição do caractere inside do bloco: a
    transcrição não traz tempo por palavra. Confira com `audio.valley_before()`
    antes de fechar, porque a interpolação erra algumas dezenas de ms.
    """
    out = []
    for s in segs:
        if s["end"] < lo or s["start"] > hi:
            continue
        txt = s["text"]
        if not txt:
            continue
        dur = s["end"] - s["start"]
        for m in re.finditer(r"[.!?…]", txt):
            inst = s["start"] + dur * (m.end() / len(txt))
            if not (lo <= inst <= hi):
                continue
            d = inst - start
            if config.CLIP_MIN_S <= d <= config.CLIP_MAX_S:
                out.append((round(inst, 2), round(d, 1),
                            txt[max(0, m.end() - 50):m.end()].strip()))
    return sorted(out)


def validate_clip(span: tuple, segs: list, state: dict) -> tuple:
    """Valida uma proposta de clip. Retorna (ok, [mensagens]).

    Checa o que é verificável em código; o julgamento editorial fica com o
    prompt de cortes e o gestor.
    """
    msgs = []
    start, end = span
    dur = end - start

    if dur < config.CLIP_MIN_S:
        msgs.append(f"duração {dur:.0f}s abaixo do mínimo de {config.CLIP_MIN_S}s")
    elif dur > config.CLIP_MAX_S:
        msgs.append(f"duração {dur:.0f}s acima do máximo de {config.CLIP_MAX_S}s")

    # O clip não pode começar NEM terminar no meio de uma frase.
    # O end já foi só alerta, na suposição de que a cauda seria "aparada no
    # render" — o render corta no tempo exato, então nada era aparado e o
    # vídeo saía com a última frase pela metade.
    if segs and not _valid_boundary(start, segs):
        msgs.append(f"início {start:.1f}s não cai em fronteira de frase")

    # Só exige pontuação final quando o end coincide com o end de um bloco.
    # Fim no MEIO de um bloco é caso legítimo (o gestor apara a cauda onde a
    # frase acaba, mesmo que o bloco siga) e não deve ser bloqueado aqui.
    if segs and _valid_boundary(end, segs) and not _ends_sentence(end, segs):
        msgs.append(f"fim {end:.1f}s não fecha frase (corta a fala no meio)")

    if state and is_burned(span, state):
        msgs.append("sobrepõe faixa já queimada (aprovada ou rejeitada)")

    return (not msgs), msgs


# Marcas de quem fala da PRÓPRIA company em 1ª pessoa. Se o segmento marcado
# como "host" está cheio delas, quem fala ali é o convidado e a atribuição
# escorregou.
RE_FIRST_PERSON = re.compile(
    r"\b(we|our|us|my company|my co-?founder|I joined|I started)\b",
    re.IGNORECASE,
)

# Above this fraction the attribution does not deserve trust.
#
# OPEN QUESTION: 0.30 was tuned against Portuguese, where the markers were
# "a gente" and "nosso". The English alternation includes bare we/our/us,
# which host register uses constantly ("tell us about", "we talked about"),
# so a well-attributed episode can now score far above 0.30 and the warning
# would fire on every episode. Re-deriving the fraction needs a real English
# transcript with known-good speaker labels to measure the base rate on;
# there is none in this repo, so the number is left as it was rather than
# replaced by a guess. Narrowing the marker set to own-company phrases is
# the other candidate fix.
SUSPECT_ATTRIBUTION_THRESHOLD = 0.30


def attribution_trustworthy(segs: list) -> bool:
    """False quando o campo `speaker` parece trocado no episódio inteiro.

    O parser resolve o falante uma vez, sobre o episódio todo; um backchannel
    curto do host pode desalinhar tudo dali em diante (trechos 100% do
    convidado saíram como "host"). Alertas que leem `speaker` mentiriam, e
    alerta que mente treina o operador a ignorar a saída — melhor calar.
    """
    host_total = first_person = 0.0
    for s in segs or []:
        if s.get("speaker") != "host":
            continue
        dur = s["end"] - s["start"]
        host_total += dur
        if RE_FIRST_PERSON.search(s.get("text") or ""):
            first_person += dur
    if host_total <= 0:
        return True
    return (first_person / host_total) < SUSPECT_ATTRIBUTION_THRESHOLD


# Segundos de host na abertura a partir dos quais o clip vira pergunta com
# response em vez de response. Um clip abria com 47s de pergunta.
HOST_OPENING_MAX_S = 8.0


def host_opening(span: tuple, segs: list) -> float:
    """Quantos segundos de fala do host abrem o clip, antes do convidado.

    Zero quando o clip já abre no convidado ou quando não dá para saber quem
    fala (`speaker` ausente) — o alerta não deve disparar no escuro.
    """
    inside = segments_in_clip(span, segs)
    total = 0.0
    for s in inside:
        speaker = s.get("speaker")
        if speaker is None:
            return 0.0
        if speaker != "host":
            break
        total += min(s["end"], span[1]) - max(s["start"], span[0])
    return total


def clip_warnings(span: tuple, segs: list) -> list:
    """Avisos que não invalidam o clip, mas exigem conferência."""
    alerts = []
    inside = segments_in_clip(span, segs)
    for s in inside:
        if has_hedged_number(s["text"]):
            alerts.append(f"número aproximado em {s['start']:.0f}s: \"{s['text'][:60]}\"")
    # Os dois alerts abaixo leem `speaker`; sem atribuição confiável eles
    # acusariam clip bom. Avisa uma vez que a checagem não rodou.
    if not attribution_trustworthy(segs):
        return alerts       # avisado uma vez por episódio, em cmd_curate

    frac = guest_speech_fraction(span, segs)
    if frac < config.GUEST_SPEECH_MIN:
        alerts.append(f"convidado fala só {frac*100:.0f}% do corte")

    seg_host = host_opening(span, segs)
    if seg_host >= HOST_OPENING_MAX_S:
        alerts.append(
            f"corte abre com {seg_host:.0f}s de fala do host — o espectador frio "
            "desiste antes do convidado falar"
        )
    return alerts


# Tipos de clip, em ordem de preferência.
KINDS = ["story", "thesis", "advice", "personal"]


def approve(state: dict, clip: dict) -> dict:
    """Registra um clip aprovado. Ajuste de tempo não é rejeição.

    Recusa clip que se sobreponha a outro JÁ APROVADO: dois vídeos com o mesmo
    trecho competem entre si na distribuição. Dois approved dividiam 74s
    porque nada checava isso aqui — `validate_clip` olha span queimada, que
    inclui approved, mas quem chama `approve()` direto escapava da checagem.

    Reaprovar o MESMO slug é ajuste de tempo, não duplicata: substitui.
    """
    span = (float(clip["start"]), float(clip["end"]))
    for i, ja in enumerate(state["approved"]):
        if ja.get("slug") == clip.get("slug"):
            state["approved"][i] = clip      # ajuste de tempo
            return state
        # Limiar zero: entre APROVADOS qualquer sobreposição já significa
        # trecho de vídeo repetido em dois cortes. O OVERLAP_THRESHOLD de 30%
        # existe para decidir se uma proposta é "o mesmo trecho" de algo
        # queimado — pergunta diferente, tolerância diferente.
        if overlaps(span, (float(ja["start"]), float(ja["end"])), threshold=0.0):
            raise ValueError(
                f"corte {clip.get('slug')} sobrepõe o aprovado "
                f"{ja.get('slug')} ({ja['start']:.0f}-{ja['end']:.0f}s)"
            )
    if len(state["approved"]) >= state["target"]:
        raise ValueError(f"target de {state['target']} cortes já atingida")
    state["approved"].append(clip)
    return state


def reject(state: dict, clip: dict, reason: str) -> dict:
    """Queima o trecho permanentemente, com o reason em texto livre."""
    state["rejected"].append({
        "start": float(clip["start"]),
        "end": float(clip["end"]),
        "summary": clip.get("summary", clip.get("screen_text", "")),
        "reason": reason,
    })
    return state


def composition(state: dict) -> dict:
    """Quantos cortes approved de cada kind (diversidade)."""
    comp = {t: 0 for t in KINDS}
    for c in state["approved"]:
        t = c.get("kind")
        if t in comp:
            comp[t] += 1
    return comp


def missing_kinds(state: dict) -> list:
    """Tipos sem nenhum clip aprovado — alimenta o aviso de diversidade."""
    return [t for t, n in composition(state).items() if n == 0]


def reasons(state: dict) -> list:
    """Motivos de rejeição sem repetição — contexto para a próxima rodada."""
    seen, out = set(), []
    for r in state.get("rejected", []):
        m = (r.get("reason") or "").strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def is_closed(state: dict) -> bool:
    """True quando a target de cortes approved foi atingida."""
    return len(state.get("approved", [])) >= state["target"]


def to_moments(state: dict) -> list:
    """Converte os approved no moments.json que o render consome.

    O render usa só slug/start/end; os demais campos são conteúdo de produção
    que precisa sobreviver até a publicação.
    """
    if not state.get("approved"):
        raise ValueError("nenhum corte aprovado — nada a exportar")
    return [dict(c) for c in state["approved"]]


def save_moments(project_dir: str, state: dict) -> str:
    """Grava moments.json no diretório do project e devolve o path."""
    moments = to_moments(state)
    path = layout.ensure_dir(layout.moments(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(moments, f, ensure_ascii=False, indent=2)
    return path
