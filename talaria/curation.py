"""Estado da curation iterativa — rounds até fechar a meta de cortes approved.

Regras de estado:
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

# Fração de sobreposição a partir da qual duas faixas são "o mesmo trecho".
OVERLAP_THRESHOLD = 0.30


def new_state(meta: int = 5) -> dict:
    return {"meta": meta, "approved": [], "rejected": [], "rounds": 0}


def overlaps(a: tuple, b: tuple, limiar: float = OVERLAP_THRESHOLD) -> bool:
    """True se as faixas (start, end) se sobrepõem acima do limiar.

    O limiar é relativo à MENOR das duas faixas — assim um clip curto contido
    num rejeitado longo conta como sobreposição.
    """
    inicio = max(a[0], b[0])
    fim = min(a[1], b[1])
    overlap = fim - inicio
    if overlap <= 0:
        return False
    menor = min(a[1] - a[0], b[1] - b[0])
    if menor <= 0:
        return False
    return (overlap / menor) >= limiar


def burned_spans(estado: dict) -> list:
    """Todas as faixas (start, end) indisponíveis para novas propostas."""
    faixas = []
    for grupo in ("approved", "rejected"):
        for item in estado.get(grupo, []):
            if "start" in item and "end" in item:
                faixas.append((float(item["start"]), float(item["end"])))
    return faixas


def is_burned(faixa: tuple, estado: dict) -> bool:
    return any(overlaps(faixa, q) for q in burned_spans(estado))


def slots_left(estado: dict) -> int:
    return max(0, estado["meta"] - len(estado.get("approved", [])))


def load(project_dir: str, meta: int = 5) -> dict:
    path = layout.curation(project_dir)
    if not os.path.exists(path):
        return new_state(meta)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, estado: dict) -> str:
    path = layout.ensure_dir(layout.curation(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    return path


# Marcadores de número aproximado.
# Isolado num clip, "uns 570, 580" vira afirmação categórica que a pessoa
# não fez.
RE_HEDGED_NUMBER = re.compile(
    r"\b(uns|umas|aproximadamente|cerca de|por volta de|acho que|"
    r"se (?:eu )?não me engano|se eu não tiver enganado|mais ou menos)\b"
    r"[^.!?]{0,40}?\d",
    re.IGNORECASE,
)


def has_hedged_number(texto: str) -> bool:
    """True se o texto contém número dito com aproximação ou dúvida."""
    return bool(RE_HEDGED_NUMBER.search(texto or ""))


def _valid_boundary(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t coincide com o início ou o fim de algum segmento."""
    for s in segs:
        if abs(s["start"] - t) <= tol or abs(s["end"] - t) <= tol:
            return True
    return False


# Pontuação que encerra frase. Reticências contam: a fala fica suspensa, mas
# não cortada no meio de uma palavra.
RE_SENTENCE_END = re.compile(r"[.!?…]\s*$|\.\.\.\s*$")


def _ends_sentence(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t cai no fim de um segmento cujo texto encerra uma frase.

    A transcrição do YouTube quebra bloco por TEMPO, não por pontuação — um
    bloco pode acabar no meio da frase e emendar no seguinte. Casar só com o
    limite do bloco (_valid_boundary) aceitava clip terminando em palavra
    solta; aqui a pontuação do texto é que decide.
    """
    for s in segs:
        if abs(s["end"] - t) <= tol:
            return bool(RE_SENTENCE_END.search(s["text"].strip()))
    return False


def segments_in_clip(faixa: tuple, segs: list) -> list:
    """Segmentos que intersectam a faixa (start, end) do clip."""
    start, end = faixa
    return [s for s in segs if s["end"] > start and s["start"] < end]


def guest_speech_fraction(faixa: tuple, segs: list) -> float:
    """Fração do tempo do clip em que o convidado fala.

    Lê o campo `speaker`, resolvido globalmente no parse (txt_parse.
    resolve_speakers). NÃO deduz o falante alternando um booleano dentro da
    fatia: o marcador '>>' diz QUE trocou de interlocutor, não QUEM fala, e um
    clip que começa no meio de uma resposta não tem nenhum '>>' dentro dele —
    a alternância local devolvia 0.0 justamente para os cortes 100% convidado.

    Segmentos sem `speaker` (origem vtt/Whisper, que não tem marcador de troca,
    ou dado gravado antes desta correção) são ignorados no cálculo. Se NENHUM
    segmento do clip tiver `speaker`, o protagonismo é inaferível e a função
    devolve 1.0 — o valor que não dispara o alerta em clip_warnings(). Devolver
    0.0 acusaria de "convidado fala 0%" todo clip vindo do Whisper, o mesmo
    alerta falso que esta correção existe para eliminar; quando não dá para
    medir, o julgamento fica com o prompt de cortes e o gestor.
    """
    dentro = segments_in_clip(faixa, segs)
    if not dentro:
        return 0.0
    total = convidado = 0.0
    for s in dentro:
        speaker = s.get("speaker")
        if speaker is None:
            continue
        dur = min(s["end"], faixa[1]) - max(s["start"], faixa[0])
        if dur <= 0:
            continue
        total += dur
        if speaker == "convidado":
            convidado += dur
    if not total:
        return 1.0        # inaferível: não alerta
    return convidado / total


def sentence_ends(segs: list, inicio: float, lo: float, hi: float) -> list:
    """Fins de frase entre `lo` e `hi` que dão clip de duração válida.

    Devolve [(instante, duracao, contexto)] ordenado por instante. Serve para
    escolher onde terminar um clip sem cortar a fala no meio — o trabalho que
    nesta sessão foi feito à mão, procurando pontuação no texto.

    O instante é interpolado pela posição do caractere dentro do bloco: a
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
            d = inst - inicio
            if config.CLIP_MIN_S <= d <= config.CLIP_MAX_S:
                out.append((round(inst, 2), round(d, 1),
                            txt[max(0, m.end() - 50):m.end()].strip()))
    return sorted(out)


def validate_clip(faixa: tuple, segs: list, estado: dict) -> tuple:
    """Valida uma proposta de clip. Retorna (ok, [mensagens]).

    Checa o que é verificável em código; o julgamento editorial fica com o
    prompt de cortes e o gestor.
    """
    msgs = []
    start, end = faixa
    dur = end - start

    if dur < config.CLIP_MIN_S:
        msgs.append(f"duração {dur:.0f}s abaixo do mínimo de {config.CLIP_MIN_S}s")
    elif dur > config.CLIP_MAX_S:
        msgs.append(f"duração {dur:.0f}s acima do máximo de {config.CLIP_MAX_S}s")

    # O clip não pode começar NEM terminar no meio de uma frase.
    # O fim já foi só alerta, na suposição de que a cauda seria "aparada no
    # render" — o render corta no tempo exato, então nada era aparado e o
    # vídeo saía com a última frase pela metade.
    if segs and not _valid_boundary(start, segs):
        msgs.append(f"início {start:.1f}s não cai em fronteira de frase")

    # Só exige pontuação final quando o fim coincide com o fim de um bloco.
    # Fim no MEIO de um bloco é caso legítimo (o gestor apara a cauda onde a
    # frase acaba, mesmo que o bloco siga) e não deve ser bloqueado aqui.
    if segs and _valid_boundary(end, segs) and not _ends_sentence(end, segs):
        msgs.append(f"fim {end:.1f}s não fecha frase (corta a fala no meio)")

    if estado and is_burned(faixa, estado):
        msgs.append("sobrepõe faixa já queimada (aprovada ou rejeitada)")

    return (not msgs), msgs


# Marcas de who fala da PRÓPRIA company em 1ª pessoa. Se o segmento marcado
# como "host" está cheio delas, who fala ali é o convidado e a atribuição
# escorregou.
RE_FIRST_PERSON = re.compile(
    r"\b(a gente|nosso|nossa|nossos|nossas|eu vim|meu sócio|minha company)\b",
    re.IGNORECASE,
)

# Acima desta fração, a atribuição não merece confiança. Metade do tempo do
# host falando da própria company não acontece num episódio bem atribuído.
SUSPECT_ATTRIBUTION_THRESHOLD = 0.30


def attribution_trustworthy(segs: list) -> bool:
    """False quando o campo `speaker` parece trocado no episódio inteiro.

    O parser resolve o falante uma vez, sobre o episódio todo; um backchannel
    curto do host pode desalinhar tudo dali em diante (trechos 100% do
    convidado saíram como "host"). Alertas que leem `speaker` mentiriam, e
    alerta que mente treina o operador a ignorar a saída — melhor calar.
    """
    host_total = primeira_pessoa = 0.0
    for s in segs or []:
        if s.get("speaker") != "host":
            continue
        dur = s["end"] - s["start"]
        host_total += dur
        if RE_FIRST_PERSON.search(s.get("text") or ""):
            primeira_pessoa += dur
    if host_total <= 0:
        return True
    return (primeira_pessoa / host_total) < SUSPECT_ATTRIBUTION_THRESHOLD


# Segundos de host na abertura a partir dos quais o clip vira pergunta com
# resposta em vez de resposta. Um clip abria com 47s de pergunta.
HOST_OPENING_MAX_S = 8.0


def host_opening(faixa: tuple, segs: list) -> float:
    """Quantos segundos de fala do host abrem o clip, antes do convidado.

    Zero quando o clip já abre no convidado ou quando não dá para saber who
    fala (`speaker` ausente) — o alerta não deve disparar no escuro.
    """
    dentro = segments_in_clip(faixa, segs)
    total = 0.0
    for s in dentro:
        speaker = s.get("speaker")
        if speaker is None:
            return 0.0
        if speaker != "host":
            break
        total += min(s["end"], faixa[1]) - max(s["start"], faixa[0])
    return total


def clip_warnings(faixa: tuple, segs: list) -> list:
    """Avisos que não invalidam o clip, mas exigem conferência."""
    alertas = []
    dentro = segments_in_clip(faixa, segs)
    for s in dentro:
        if has_hedged_number(s["text"]):
            alertas.append(f"número aproximado em {s['start']:.0f}s: \"{s['text'][:60]}\"")
    # Os dois alertas abaixo leem `speaker`; sem atribuição confiável eles
    # acusariam clip bom. Avisa uma vez que a checagem não rodou.
    if not attribution_trustworthy(segs):
        return alertas       # avisado uma vez por episódio, em cmd_curate

    frac = guest_speech_fraction(faixa, segs)
    if frac < config.GUEST_SPEECH_MIN:
        alertas.append(f"convidado fala só {frac*100:.0f}% do clip")

    seg_host = host_opening(faixa, segs)
    if seg_host >= HOST_OPENING_MAX_S:
        alertas.append(
            f"clip abre com {seg_host:.0f}s de fala do host — o espectador frio "
            "desiste antes do convidado falar"
        )
    return alertas


# Tipos de clip, em ordem de preferência.
KINDS = ["story", "thesis", "advice", "pessoal"]


def approve(estado: dict, clip: dict) -> dict:
    """Registra um clip aprovado. Ajuste de tempo não é rejeição.

    Recusa clip que se sobreponha a outro JÁ APROVADO: dois vídeos com o mesmo
    trecho competem entre si na distribuição. Dois approved dividiam 74s
    porque nada checava isso aqui — `validate_clip` olha faixa queimada, que
    inclui approved, mas who chama `approve()` direto escapava da checagem.

    Reaprovar o MESMO slug é ajuste de tempo, não duplicata: substitui.
    """
    faixa = (float(clip["start"]), float(clip["end"]))
    for i, ja in enumerate(estado["approved"]):
        if ja.get("slug") == clip.get("slug"):
            estado["approved"][i] = clip      # ajuste de tempo
            return estado
        # Limiar zero: entre APROVADOS qualquer sobreposição já significa
        # trecho de vídeo repetido em dois cortes. O OVERLAP_THRESHOLD de 30%
        # existe para decidir se uma proposta é "o mesmo trecho" de algo
        # queimado — pergunta diferente, tolerância diferente.
        if overlaps(faixa, (float(ja["start"]), float(ja["end"])), limiar=0.0):
            raise ValueError(
                f"clip {clip.get('slug')} sobrepõe o aprovado "
                f"{ja.get('slug')} ({ja['start']:.0f}-{ja['end']:.0f}s)"
            )
    if len(estado["approved"]) >= estado["meta"]:
        raise ValueError(f"meta de {estado['meta']} cortes já atingida")
    estado["approved"].append(clip)
    return estado


def reject(estado: dict, clip: dict, reason: str) -> dict:
    """Queima o trecho permanentemente, com o reason em texto livre."""
    estado["rejected"].append({
        "start": float(clip["start"]),
        "end": float(clip["end"]),
        "summary": clip.get("summary", clip.get("screen_text", "")),
        "reason": reason,
    })
    return estado


def composition(estado: dict) -> dict:
    """Quantos cortes approved de cada kind (diversidade)."""
    comp = {t: 0 for t in KINDS}
    for c in estado["approved"]:
        t = c.get("kind")
        if t in comp:
            comp[t] += 1
    return comp


def missing_kinds(estado: dict) -> list:
    """Tipos sem nenhum clip aprovado — alimenta o aviso de diversidade."""
    return [t for t, n in composition(estado).items() if n == 0]


def reasons(estado: dict) -> list:
    """Motivos de rejeição sem repetição — contexto para a próxima rodada."""
    vistos, out = set(), []
    for r in estado.get("rejected", []):
        m = (r.get("reason") or "").strip()
        if m and m not in vistos:
            vistos.add(m)
            out.append(m)
    return out


def is_closed(estado: dict) -> bool:
    """True quando a meta de cortes approved foi atingida."""
    return len(estado.get("approved", [])) >= estado["meta"]


def to_moments(estado: dict) -> list:
    """Converte os approved no moments.json que o render consome.

    O render usa só slug/start/end; os demais campos são conteúdo de produção
    que precisa sobreviver até a publicação.
    """
    if not estado.get("approved"):
        raise ValueError("nenhum clip aprovado — nada a export")
    return [dict(c) for c in estado["approved"]]


def save_moments(project_dir: str, estado: dict) -> str:
    """Grava moments.json no diretório do project e devolve o caminho."""
    moments = to_moments(estado)
    path = layout.ensure_dir(layout.moments(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(moments, f, ensure_ascii=False, indent=2)
    return path
