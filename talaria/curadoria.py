"""Estado da curadoria iterativa — rodadas até fechar a meta de cortes aprovados.

Regras de estado (ver spec):
- trecho rejeitado fica queimado permanentemente, não volta em nenhuma rodada;
- exclusão por SOBREPOSIÇÃO DE TEMPO, não por texto — um corte 10s adiante de
  um rejeitado é essencialmente o mesmo trecho;
- ajuste de tempo não é rejeição, é aprovação com correção.
"""
from __future__ import annotations

import json
import os
import re

from . import config, layout

NOME_ARQUIVO = "curadoria.json"

# Fração de sobreposição a partir da qual duas faixas são "o mesmo trecho".
LIMIAR_SOBREPOSICAO = 0.30


def novo_estado(meta: int = 5) -> dict:
    return {"meta": meta, "aprovados": [], "rejeitados": [], "rodadas": 0}


def sobrepoe(a: tuple, b: tuple, limiar: float = LIMIAR_SOBREPOSICAO) -> bool:
    """True se as faixas (start, end) se sobrepõem acima do limiar.

    O limiar é relativo à MENOR das duas faixas — assim um corte curto contido
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


def faixas_queimadas(estado: dict) -> list:
    """Todas as faixas (start, end) indisponíveis para novas propostas."""
    faixas = []
    for grupo in ("aprovados", "rejeitados"):
        for item in estado.get(grupo, []):
            if "start" in item and "end" in item:
                faixas.append((float(item["start"]), float(item["end"])))
    return faixas


def esta_queimado(faixa: tuple, estado: dict) -> bool:
    return any(sobrepoe(faixa, q) for q in faixas_queimadas(estado))


def vagas(estado: dict) -> int:
    return max(0, estado["meta"] - len(estado.get("aprovados", [])))


def load(project_dir: str, meta: int = 5) -> dict:
    path = layout.curadoria(project_dir)
    if not os.path.exists(path):
        return novo_estado(meta)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(project_dir: str, estado: dict) -> str:
    path = layout.garante(layout.curadoria(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    return path


# Marcadores de número aproximado — seção 6 do prompt de cortes.
# Isolado num corte, "uns 570, 580" vira afirmação categórica que a pessoa
# não fez.
RE_HESITACAO = re.compile(
    r"\b(uns|umas|aproximadamente|cerca de|por volta de|acho que|"
    r"se (?:eu )?não me engano|se eu não tiver enganado|mais ou menos)\b"
    r"[^.!?]{0,40}?\d",
    re.IGNORECASE,
)


def tem_hesitacao_numerica(texto: str) -> bool:
    """True se o texto contém número dito com aproximação ou dúvida."""
    return bool(RE_HESITACAO.search(texto or ""))


def _fronteira_valida(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t coincide com o início ou o fim de algum segmento."""
    for s in segs:
        if abs(s["start"] - t) <= tol or abs(s["end"] - t) <= tol:
            return True
    return False


# Pontuação que encerra frase. Reticências contam: a fala fica suspensa, mas
# não cortada no meio de uma palavra.
RE_FIM_DE_FRASE = re.compile(r"[.!?…]\s*$|\.\.\.\s*$")


def _fecha_frase(t: float, segs: list, tol: float = 0.5) -> bool:
    """True se t cai no fim de um segmento cujo texto encerra uma frase.

    A transcrição do YouTube quebra bloco por TEMPO, não por pontuação — um
    bloco pode acabar no meio da frase e emendar no seguinte. Casar só com o
    limite do bloco (_fronteira_valida) aceitava corte terminando em palavra
    solta; aqui a pontuação do texto é que decide.
    """
    for s in segs:
        if abs(s["end"] - t) <= tol:
            return bool(RE_FIM_DE_FRASE.search(s["text"].strip()))
    return False


def segmentos_no_corte(faixa: tuple, segs: list) -> list:
    """Segmentos que intersectam a faixa (start, end) do corte."""
    start, end = faixa
    return [s for s in segs if s["end"] > start and s["start"] < end]


def fracao_convidado(faixa: tuple, segs: list) -> float:
    """Fração do tempo do corte em que o convidado fala (seção 5).

    Lê o campo `speaker`, resolvido globalmente no parse (txt_parse.
    resolve_speakers). NÃO deduz o falante alternando um booleano dentro da
    fatia: o marcador '>>' diz QUE trocou de interlocutor, não QUEM fala, e um
    corte que começa no meio de uma resposta não tem nenhum '>>' dentro dele —
    a alternância local devolvia 0.0 justamente para os cortes 100% convidado.

    Segmentos sem `speaker` (origem vtt/Whisper, que não tem marcador de troca,
    ou dado gravado antes desta correção) são ignorados no cálculo. Se NENHUM
    segmento do corte tiver `speaker`, o protagonismo é inaferível e a função
    devolve 1.0 — o valor que não dispara o alerta em alertas_corte(). Devolver
    0.0 acusaria de "convidado fala 0%" todo corte vindo do Whisper, o mesmo
    alerta falso que esta correção existe para eliminar; quando não dá para
    medir, o julgamento fica com o prompt de cortes e o gestor.
    """
    dentro = segmentos_no_corte(faixa, segs)
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


def fins_de_frase(segs: list, inicio: float, lo: float, hi: float) -> list:
    """Fins de frase entre `lo` e `hi` que dão corte de duração válida.

    Devolve [(instante, duracao, contexto)] ordenado por instante. Serve para
    escolher onde terminar um corte sem cortar a fala no meio — o trabalho que
    nesta sessão foi feito à mão, procurando pontuação no texto.

    O instante é interpolado pela posição do caractere dentro do bloco: a
    transcrição não traz tempo por palavra. Confira com `audio.vale_antes()`
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
            if config.CORTE_MIN_S <= d <= config.CORTE_MAX_S:
                out.append((round(inst, 2), round(d, 1),
                            txt[max(0, m.end() - 50):m.end()].strip()))
    return sorted(out)


def valida_corte(faixa: tuple, segs: list, estado: dict) -> tuple:
    """Valida uma proposta de corte. Retorna (ok, [mensagens]).

    Checa o que é verificável em código; o julgamento editorial fica com o
    prompt de cortes e o gestor.
    """
    msgs = []
    start, end = faixa
    dur = end - start

    if dur < config.CORTE_MIN_S:
        msgs.append(f"duração {dur:.0f}s abaixo do mínimo de {config.CORTE_MIN_S}s")
    elif dur > config.CORTE_MAX_S:
        msgs.append(f"duração {dur:.0f}s acima do máximo de {config.CORTE_MAX_S}s")

    # Seção 7: o corte não pode começar NEM terminar no meio de uma frase.
    # O fim já foi só alerta, na suposição de que a cauda seria "aparada no
    # render" — o render corta no tempo exato, então nada era aparado e o
    # vídeo saía com a última frase pela metade (corte do mar azul).
    if segs and not _fronteira_valida(start, segs):
        msgs.append(f"início {start:.1f}s não cai em fronteira de frase")

    # Só exige pontuação final quando o fim coincide com o fim de um bloco.
    # Fim no MEIO de um bloco é caso legítimo (o gestor apara a cauda onde a
    # frase acaba, mesmo que o bloco siga) e não deve ser bloqueado aqui.
    if segs and _fronteira_valida(end, segs) and not _fecha_frase(end, segs):
        msgs.append(f"fim {end:.1f}s não fecha frase (corta a fala no meio)")

    if estado and esta_queimado(faixa, estado):
        msgs.append("sobrepõe faixa já queimada (aprovada ou rejeitada)")

    return (not msgs), msgs


# Marcas de quem fala da PRÓPRIA empresa em 1ª pessoa. Se o segmento marcado
# como "host" está cheio delas, quem fala ali é o convidado e a atribuição
# escorregou.
RE_PRIMEIRA_PESSOA = re.compile(
    r"\b(a gente|nosso|nossa|nossos|nossas|eu vim|meu sócio|minha empresa)\b",
    re.IGNORECASE,
)

# Acima desta fração, a atribuição não merece confiança. Metade do tempo do
# host falando da própria empresa não acontece num episódio bem atribuído.
LIMIAR_ATRIBUICAO_SUSPEITA = 0.30


def atribuicao_confiavel(segs: list) -> bool:
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
        if RE_PRIMEIRA_PESSOA.search(s.get("text") or ""):
            primeira_pessoa += dur
    if host_total <= 0:
        return True
    return (primeira_pessoa / host_total) < LIMIAR_ATRIBUICAO_SUSPEITA


# Segundos de host na abertura a partir dos quais o corte vira pergunta com
# resposta em vez de resposta. Um corte abria com 47s de pergunta.
ABERTURA_HOST_MAX_S = 8.0


def abertura_do_host(faixa: tuple, segs: list) -> float:
    """Quantos segundos de fala do host abrem o corte, antes do convidado.

    Zero quando o corte já abre no convidado ou quando não dá para saber quem
    fala (`speaker` ausente) — o alerta não deve disparar no escuro.
    """
    dentro = segmentos_no_corte(faixa, segs)
    total = 0.0
    for s in dentro:
        speaker = s.get("speaker")
        if speaker is None:
            return 0.0
        if speaker != "host":
            break
        total += min(s["end"], faixa[1]) - max(s["start"], faixa[0])
    return total


def alertas_corte(faixa: tuple, segs: list) -> list:
    """Avisos que não invalidam o corte, mas exigem conferência."""
    alertas = []
    dentro = segmentos_no_corte(faixa, segs)
    for s in dentro:
        if tem_hesitacao_numerica(s["text"]):
            alertas.append(f"número aproximado em {s['start']:.0f}s: \"{s['text'][:60]}\"")
    # Os dois alertas abaixo leem `speaker`; sem atribuição confiável eles
    # acusariam corte bom. Avisa uma vez que a checagem não rodou.
    if not atribuicao_confiavel(segs):
        return alertas       # avisado uma vez por episódio, em cmd_curar

    frac = fracao_convidado(faixa, segs)
    if frac < config.FALA_CONVIDADO_MIN:
        alertas.append(f"convidado fala só {frac*100:.0f}% do corte")

    seg_host = abertura_do_host(faixa, segs)
    if seg_host >= ABERTURA_HOST_MAX_S:
        alertas.append(
            f"corte abre com {seg_host:.0f}s de fala do host — o espectador frio "
            f"desiste antes do convidado falar (seção 1 do prompt)"
        )
    return alertas


# Tipos de corte, em ordem de preferência (seção 4 do prompt de cortes).
TIPOS = ["historia", "tese", "conselho", "pessoal"]


def aprovar(estado: dict, corte: dict) -> dict:
    """Registra um corte aprovado. Ajuste de tempo não é rejeição.

    Recusa corte que se sobreponha a outro JÁ APROVADO: dois vídeos com o mesmo
    trecho competem entre si na distribuição. Dois aprovados dividiam 74s
    porque nada checava isso aqui — `valida_corte` olha faixa queimada, que
    inclui aprovados, mas quem chama `aprovar()` direto escapava da checagem.

    Reaprovar o MESMO slug é ajuste de tempo, não duplicata: substitui.
    """
    faixa = (float(corte["start"]), float(corte["end"]))
    for i, ja in enumerate(estado["aprovados"]):
        if ja.get("slug") == corte.get("slug"):
            estado["aprovados"][i] = corte      # ajuste de tempo
            return estado
        # Limiar zero: entre APROVADOS qualquer sobreposição já significa
        # trecho de vídeo repetido em dois cortes. O LIMIAR_SOBREPOSICAO de 30%
        # existe para decidir se uma proposta é "o mesmo trecho" de algo
        # queimado — pergunta diferente, tolerância diferente.
        if sobrepoe(faixa, (float(ja["start"]), float(ja["end"])), limiar=0.0):
            raise ValueError(
                f"corte {corte.get('slug')} sobrepõe o aprovado "
                f"{ja.get('slug')} ({ja['start']:.0f}-{ja['end']:.0f}s)"
            )
    if len(estado["aprovados"]) >= estado["meta"]:
        raise ValueError(f"meta de {estado['meta']} cortes já atingida")
    estado["aprovados"].append(corte)
    return estado


def rejeitar(estado: dict, corte: dict, motivo: str) -> dict:
    """Queima o trecho permanentemente, com o motivo em texto livre."""
    estado["rejeitados"].append({
        "start": float(corte["start"]),
        "end": float(corte["end"]),
        "resumo": corte.get("resumo", corte.get("texto_tela", "")),
        "motivo": motivo,
    })
    return estado


def composicao(estado: dict) -> dict:
    """Quantos cortes aprovados de cada tipo (seção 5 — diversidade)."""
    comp = {t: 0 for t in TIPOS}
    for c in estado["aprovados"]:
        t = c.get("tipo")
        if t in comp:
            comp[t] += 1
    return comp


def tipos_ausentes(estado: dict) -> list:
    """Tipos sem nenhum corte aprovado — alimenta o aviso de diversidade."""
    return [t for t, n in composicao(estado).items() if n == 0]


def motivos(estado: dict) -> list:
    """Motivos de rejeição sem repetição — contexto para a próxima rodada."""
    vistos, out = set(), []
    for r in estado.get("rejeitados", []):
        m = (r.get("motivo") or "").strip()
        if m and m not in vistos:
            vistos.add(m)
            out.append(m)
    return out


def fechado(estado: dict) -> bool:
    """True quando a meta de cortes aprovados foi atingida."""
    return len(estado.get("aprovados", [])) >= estado["meta"]


def para_momentos(estado: dict) -> list:
    """Converte os aprovados no momentos.json que o render consome.

    O render usa só slug/start/end; os demais campos são conteúdo de produção
    (seção 8 do prompt) que precisa sobreviver até a publicação.
    """
    if not estado.get("aprovados"):
        raise ValueError("nenhum corte aprovado — nada a exportar")
    return [dict(c) for c in estado["aprovados"]]


def salvar_momentos(project_dir: str, estado: dict) -> str:
    """Grava momentos.json no diretório do projeto e devolve o caminho."""
    momentos = para_momentos(estado)
    path = layout.garante(layout.momentos(project_dir))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(momentos, f, ensure_ascii=False, indent=2)
    return path
