"""Monta os pacotes de leitura que o Claude consome em sessão.

Junta prompt versionado + metadados do episódio + transcrição num arquivo
único, substituindo a colagem manual a cada episódio.
"""
from __future__ import annotations

import json
import os

from . import curadoria as cur
from . import episodio, layout, utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(ROOT, "prompts")


def transcricao_legivel(project_dir: str) -> str:
    """Transcrição com [mm:ss] por segmento, para localizar cortes."""
    path = layout.transcricao(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]
    linhas = []
    for s in segs:
        marca = ">> " if s.get("turn") else ""
        linhas.append(f"[{utils.mmss(s['start'])}] {marca}{s['text']}")
    return "\n".join(linhas)


def metadados_legiveis(project_dir: str) -> str:
    """Seção 7 do prompt de materiais, preenchida a partir do episodio.json."""
    ep = episodio.load(project_dir)
    convidados = ep.get("convidados") or []
    nomes = "; ".join(
        f"{c.get('nome','')} ({c.get('cargo','')})" for c in convidados if c.get("nome")
    )
    links = "; ".join(c.get("linkedin", "") for c in convidados if c.get("linkedin"))
    temas = ", ".join(ep.get("temas") or [])
    return (
        f"- Temporada: {ep['temporada']}\n"
        f"- Número do episódio: {int(ep['episodio']):02d}\n"
        f"- Código: {episodio.codigo(ep)}\n"
        f"- Convidado(s) e cargo: {nomes}\n"
        f"- Empresa ou instituição: {ep['empresa']}\n"
        f"- Cidade/UF da gravação: {ep['cidade']}/{ep['uf']}\n"
        f"- LinkedIn do(s) convidado(s): {links}\n"
        f"- Temas da conversa: {temas}\n"
    )


def preencher(template: str, transcricao: str, metadados: str,
              curadoria: str = "", cortes: str = "") -> str:
    """Substitui os placeholders do prompt pelo conteúdo do episódio."""
    return (template
            .replace("{{TRANSCRICAO}}", transcricao)
            .replace("{{METADADOS}}", metadados)
            .replace("{{CURADORIA}}", curadoria)
            .replace("{{CORTES}}", cortes))


def curadoria_legivel(estado: dict) -> str:
    """Estado da curadoria em texto, injetado na seção 10 do prompt de cortes."""
    aprovados = estado.get("aprovados", [])
    rejeitados = estado.get("rejeitados", [])

    if not aprovados and not rejeitados:
        return ("PRIMEIRA RODADA — nenhum corte avaliado ainda.\n"
                "Proponha 10 trechos, ordenados do mais forte para o mais fraco.")

    linhas = [
        f"Rodada: {estado.get('rodadas', 0)}",
        f"Meta: {estado['meta']} cortes",
        f"Aprovados: {len(aprovados)}",
        f"VAGAS RESTANTES: {cur.vagas(estado)} — proponha exatamente este número.",
        "",
        "COMPOSIÇÃO POR TIPO:",
    ]
    for tipo, n in cur.composicao(estado).items():
        linhas.append(f"  {tipo}: {n}")
    ausentes = cur.tipos_ausentes(estado)
    if ausentes:
        linhas.append(f"  TIPOS AUSENTES (priorize): {', '.join(ausentes)}")

    linhas.append("")
    linhas.append("FAIXAS QUEIMADAS — não proponha nada que se sobreponha a elas:")
    for c in aprovados:
        linhas.append(f"  [{utils.mmss(c['start'])}-{utils.mmss(c['end'])}] "
                      f"APROVADO: {c.get('texto_tela', c.get('slug', ''))}")
    for r in rejeitados:
        linhas.append(f"  [{utils.mmss(r['start'])}-{utils.mmss(r['end'])}] "
                      f"REJEITADO ({r.get('motivo', '')}): {r.get('resumo', '')}")

    ms = cur.motivos(estado)
    if ms:
        linhas.append("")
        linhas.append("MOTIVOS DE REJEIÇÃO ACUMULADOS — aplique como filtro:")
        for m in ms:
            linhas.append(f"  - {m}")

    return "\n".join(linhas)


def _ler_prompt(nome: str) -> str:
    """Lê um prompt versionado do diretório prompts/."""
    path = os.path.join(PROMPTS_DIR, nome)
    if not os.path.exists(path):
        raise FileNotFoundError(f"prompt não encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def montar(project_dir: str, tipo: str) -> str:
    """tipo: 'materiais' ou 'cortes'. Retorna o caminho do arquivo gerado."""
    if tipo not in ("materiais", "cortes"):
        raise ValueError("tipo deve ser 'materiais' ou 'cortes'")
    template = _ler_prompt(f"{tipo}.md")
    estado_txt = ""
    if tipo == "cortes":
        estado_txt = curadoria_legivel(cur.load(project_dir))
    conteudo = preencher(
        template,
        transcricao=transcricao_legivel(project_dir),
        metadados=metadados_legiveis(project_dir),
        curadoria=estado_txt,
    )
    out = layout.garante(layout.brief(project_dir, tipo))
    with open(out, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return out


def fala_do_corte(project_dir: str, corte: dict) -> str:
    """A fala literal do corte, para escolher a citação.

    Inclui todo segmento que SOBREPÕE a janela, aparando o texto na fronteira —
    a mesma regra do `render._segments_in_cut`, para que o pacote mostre a fala
    que virou vídeo.

    Exigir contenção total escondia a última frase de todo corte do EP8, porque
    a transcrição tem blocos de ~8s e a fronteira quase nunca coincide com eles.
    Era justamente onde costuma estar a frase de impacto: no corte1 o pacote
    terminava em "chegou lá na fábrica, você não" enquanto o vídeo seguia.

    O texto vem CRU (sem `clean_caption`): a escolha do recorte é feita sobre o
    que a pessoa falou. A limpeza entra depois, no `post --gerar`.
    """
    from .render import _apara_texto

    path = layout.transcricao(project_dir)
    with open(path, encoding="utf-8") as f:
        segs = json.load(f)["segments"]

    partes = []
    for s in segs:
        ini, fim = s["start"], s["end"]
        if fim <= corte["start"] or ini >= corte["end"]:
            continue
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        if ini < corte["start"] or fim > corte["end"]:
            dur = fim - ini
            if dur > 0:
                txt = _apara_texto(
                    txt,
                    (max(ini, corte["start"]) - ini) / dur,
                    (min(fim, corte["end"]) - ini) / dur,
                )
        if txt:
            partes.append(txt)
    return " ".join(partes).strip()


def cortes_legiveis(project_dir: str, cortes: list) -> str:
    """Bloco com a fala de cada corte selecionado, para a sessão de curadoria."""
    partes = []
    for c in cortes:
        partes.append(
            f"### {c['slug']}  [{utils.mmss(c['start'])}–{utils.mmss(c['end'])}]\n\n"
            f"- Tipo: {c.get('tipo', '')}\n"
            f"- Texto de tela do vídeo: {c.get('texto_tela', '')}\n\n"
            f"Fala literal:\n\n{fala_do_corte(project_dir, c)}\n"
        )
    return "\n".join(partes)


def montar_posts(project_dir: str, cortes: list) -> str:
    """Escreve brief_posts.md com o prompt e a fala dos cortes escolhidos.

    Função separada de `montar()` porque o pacote de posts não recebe a
    transcrição inteira: a citação sai de cortes já aprovados, e mandar o
    episódio todo convidaria a escolher fala que nunca virou vídeo.
    """
    from . import config
    limite = (
        f"Máximo de {config.POST_CIT_MAX_LINHAS} linhas por card, cerca de "
        f"100 caracteres. O exemplo aprovado do design tem 97.\n"
    )
    conteudo = preencher(
        _ler_prompt("posts.md"),
        transcricao="",
        metadados=metadados_legiveis(project_dir) + "\n" + limite,
        cortes=cortes_legiveis(project_dir, cortes),
    )
    out = layout.garante(layout.brief(project_dir, "posts"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return out
