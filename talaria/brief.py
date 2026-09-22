"""Monta os pacotes de leitura que um modelo de linguagem consome em sessão.

Junta prompt versionado + metadados do episódio + transcrição num arquivo
único, substituindo a colagem manual a cada episódio.
"""
from __future__ import annotations

import json
import os

from . import curation as cur
from . import episode, layout, utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(ROOT, "prompts")


def readable_transcript(project_dir: str) -> str:
    """Transcrição com [mm:ss] por segmento, para localizar cortes."""
    path = layout.transcript(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]
    lines = []
    for s in segs:
        marca = ">> " if s.get("turn") else ""
        lines.append(f"[{utils.mmss(s['start'])}] {marca}{s['text']}")
    return "\n".join(lines)


def readable_metadata(project_dir: str) -> str:
    """Bloco de metadados do prompt, preenchido a partir do episode.json."""
    ep = episode.load(project_dir)
    guests = ep.get("guests") or []
    nomes = "; ".join(
        f"{c.get('name','')} ({c.get('role','')})" for c in guests if c.get("name")
    )
    links = "; ".join(c.get("linkedin", "") for c in guests if c.get("linkedin"))
    topics = ", ".join(ep.get("topics") or [])
    return (
        f"- Temporada: {ep['season']}\n"
        f"- Número do episódio: {int(ep['episode']):02d}\n"
        f"- Código: {episode.code(ep)}\n"
        f"- Convidado(s) e role: {nomes}\n"
        f"- Empresa ou instituição: {ep['company']}\n"
        f"- Cidade/UF da gravação: {ep['cidade']}/{ep['uf']}\n"
        f"- LinkedIn do(s) convidado(s): {links}\n"
        f"- Temas da conversa: {topics}\n"
    )


def preencher(template: str, transcript: str, metadados: str,
              curation: str = "", cortes: str = "") -> str:
    """Substitui os placeholders do prompt pelo conteúdo do episódio."""
    return (template
            .replace("{{TRANSCRICAO}}", transcript)
            .replace("{{METADADOS}}", metadados)
            .replace("{{CURADORIA}}", curation)
            .replace("{{CORTES}}", cortes))


def readable_curation(estado: dict) -> str:
    """Estado da curation em texto, injetado no prompt de cortes."""
    approved = estado.get("approved", [])
    rejected = estado.get("rejected", [])

    if not approved and not rejected:
        return ("PRIMEIRA RODADA — nenhum clip avaliado ainda.\n"
                "Proponha 10 trechos, ordenados do mais forte para o mais fraco.")

    lines = [
        f"Rodada: {estado.get('rounds', 0)}",
        f"Meta: {estado['meta']} cortes",
        f"Aprovados: {len(approved)}",
        f"VAGAS RESTANTES: {cur.slots_left(estado)} — proponha exatamente este número.",
        "",
        "COMPOSIÇÃO POR TIPO:",
    ]
    for kind, n in cur.composition(estado).items():
        lines.append(f"  {kind}: {n}")
    ausentes = cur.missing_kinds(estado)
    if ausentes:
        lines.append(f"  KINDS AUSENTES (priorize): {', '.join(ausentes)}")

    lines.append("")
    lines.append("FAIXAS QUEIMADAS — não proponha nada que se sobreponha a elas:")
    for c in approved:
        lines.append(f"  [{utils.mmss(c['start'])}-{utils.mmss(c['end'])}] "
                      f"APROVADO: {c.get('screen_text', c.get('slug', ''))}")
    for r in rejected:
        lines.append(f"  [{utils.mmss(r['start'])}-{utils.mmss(r['end'])}] "
                      f"REJEITADO ({r.get('reason', '')}): {r.get('summary', '')}")

    ms = cur.reasons(estado)
    if ms:
        lines.append("")
        lines.append("MOTIVOS DE REJEIÇÃO ACUMULADOS — aplique como filtro:")
        for m in ms:
            lines.append(f"  - {m}")

    return "\n".join(lines)


def _read_prompt(name: str) -> str:
    """Lê um prompt versionado do diretório prompts/."""
    path = os.path.join(PROMPTS_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"prompt não encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def montar(project_dir: str, kind: str) -> str:
    """kind: 'materiais' ou 'cortes'. Retorna o caminho do arquivo gerado."""
    if kind not in ("materiais", "cortes"):
        raise ValueError("kind deve ser 'materiais' ou 'cortes'")
    template = _read_prompt(f"{kind}.md")
    estado_txt = ""
    if kind == "cortes":
        estado_txt = readable_curation(cur.load(project_dir))
    conteudo = preencher(
        template,
        transcript=readable_transcript(project_dir),
        metadados=readable_metadata(project_dir),
        curation=estado_txt,
    )
    out = layout.ensure_dir(layout.brief(project_dir, kind))
    with open(out, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return out


def clip_speech(project_dir: str, clip: dict) -> str:
    """A fala literal do clip, para escolher a citação.

    Inclui todo segmento que SOBREPÕE a janela, aparando o texto na fronteira —
    a mesma regra do `render._segments_in_cut`, para que o pacote mostre a fala
    que virou vídeo.

    Exigir contenção total escondia a última frase de todo clip, porque
    a transcrição tem blocos de ~8s e a fronteira quase nunca coincide com eles.
    Era justamente onde costuma estar a frase de impacto: num clip o pacote
    terminava em "chegou lá na fábrica, você não" enquanto o vídeo seguia.

    O texto vem CRU (sem `clean_caption`): a escolha do recorte é feita sobre o
    que a pessoa falou. A limpeza entra depois, no `post --generate`.
    """
    from .render import _trim_text

    path = layout.transcript(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]

    partes = []
    for s in segs:
        ini, fim = s["start"], s["end"]
        if fim <= clip["start"] or ini >= clip["end"]:
            continue
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        if ini < clip["start"] or fim > clip["end"]:
            dur = fim - ini
            if dur > 0:
                txt = _trim_text(
                    txt,
                    (max(ini, clip["start"]) - ini) / dur,
                    (min(fim, clip["end"]) - ini) / dur,
                )
        if txt:
            partes.append(txt)
    return " ".join(partes).strip()


def readable_clips(project_dir: str, cortes: list) -> str:
    """Bloco com a fala de cada clip selecionado, para a sessão de curation."""
    partes = []
    for c in cortes:
        partes.append(
            f"### {c['slug']}  [{utils.mmss(c['start'])}–{utils.mmss(c['end'])}]\n\n"
            f"- Tipo: {c.get('kind', '')}\n"
            f"- Texto de tela do vídeo: {c.get('screen_text', '')}\n\n"
            f"Fala literal:\n\n{clip_speech(project_dir, c)}\n"
        )
    return "\n".join(partes)


def build_posts(project_dir: str, cortes: list) -> str:
    """Escreve brief_posts.md com o prompt e a fala dos cortes escolhidos.

    Função separada de `montar()` porque o pacote de posts não recebe a
    transcrição inteira: a citação sai de cortes já approved, e mandar o
    episódio todo convidaria a escolher fala que nunca virou vídeo.
    """
    from . import config
    limite = (
        f"Máximo de {config.POST_QUOTE_MAX_LINES} lines por card, cerca de "
        f"100 caracteres. A citação de referência tem 96.\n"
    )
    conteudo = preencher(
        _read_prompt("posts.md"),
        transcript="",
        metadados=readable_metadata(project_dir) + "\n" + limite,
        cortes=readable_clips(project_dir, cortes),
    )
    out = layout.ensure_dir(layout.brief(project_dir, "posts"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return out
