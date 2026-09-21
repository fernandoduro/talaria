#!/usr/bin/env python3
"""Next-Video-Shorts — orquestrador CLI.

Fluxo por vídeo (rodado por mim, Claude Code, com curadoria manual no meio):

  1. ingest     : baixa o vídeo + converte a transcrição .txt -> transcricao.json
                  (ou acquire + transcribe, quando a transcrição vem do Whisper)
  2. [episodio.json]: o gestor preenche os metadados do episódio
  3. brief      : monta o pacote de leitura (--cortes ou --materiais) p/ o Claude
  4. curar      : estado da curadoria iterativa; --exportar gera momentos.json
  5. render     : gera os cortes 9:16 com legenda p/ as plataformas escolhidas
  6. thumb      : gera a thumbnail (textos do JSON, flags sobrescrevem)
  7. post       : posts de citação p/ Instagram; --cortes monta o pacote,
                  --gerar renderiza os PNGs a partir do posts.json

Exemplos:
  python run.py acquire  --projeto ep2 --src "https://youtu.be/ZUFW4LtsPN0"
  python run.py transcribe --projeto ep2 --src "https://youtu.be/ZUFW4LtsPN0"
  python run.py render   --projeto ep2 --youtube --instagram
  python run.py ingest   --projeto ep2 --src "https://youtu.be/ZUFW4LtsPN0" \\
      --transcricao ~/Downloads/ep2.txt
  python run.py brief    --projeto ep2 --cortes
  python run.py curar    --projeto ep2 --meta 5
  python run.py thumb    --projeto ep2 --frame-at 1745       # textos do JSON
  python run.py post     --projeto ep2 --cortes 1,3
  python run.py post     --projeto ep2 --gerar

  # acquire + transcribe de uma vez (para antes da curadoria):
  python run.py prep     --projeto ep2 --src "https://youtu.be/ZUFW4LtsPN0"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from talaria import (acquire, ambiente, brief, calendario, curadoria,
                      episodio, layout, post_instagram, publicado, publish,
                      render, textos, thumbnail, transcribe, txt_parse)

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJETOS = os.path.join(ROOT, "projetos")

# O `.env` entra no ambiente antes de qualquer comando: os módulos de
# publicação leem credencial de os.environ, e sem isto o arquivo preenchido
# não chegava neles — o publish reclamava de variável faltando com a resposta
# aberta na tela do gestor.
ambiente.carrega()


def project_dir(slug: str) -> str:
    """Caminho do projeto, reorganizando o layout antigo se for o caso.

    Todo comando passa por aqui, então episódio criado antes da separação por
    natureza (fonte/decisoes/briefs/publicar) é migrado na primeira execução,
    sem o gestor pedir. `layout.migrar` é idempotente: nas vezes seguintes não
    move nada e não imprime nada.
    """
    pd = os.path.join(PROJETOS, slug)
    movidos = layout.migrar(pd)
    if movidos:
        print(f"[layout] projeto reorganizado ({len(movidos)} itens):")
        for origem, destino in movidos:
            print(f"         {origem} -> {destino}")
    return pd


def platforms_from_args(args) -> list[str]:
    p = []
    if args.youtube:
        p.append("youtube")
    if args.instagram:
        p.append("instagram")
    if not p:  # default: ambos
        p = ["youtube", "instagram"]
    return p


def cmd_acquire(args):
    pd = project_dir(args.projeto)
    acquire.acquire(args.src, pd)


def cmd_transcribe(args):
    pd = project_dir(args.projeto)
    video = layout.video(pd)
    if not os.path.exists(video):
        sys.exit(f"{video} não existe. Rode 'acquire' antes.")
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)


def cmd_prep(args):
    pd = project_dir(args.projeto)
    acquire.acquire(args.src, pd)
    video = layout.video(pd)
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)
    print(f"\n>>> Pronto para curadoria. Leia {layout.transcricao_txt(pd)} e crie "
          f"{layout.momentos(pd)}, depois rode 'render'.")


def cmd_render(args):
    pd = project_dir(args.projeto)
    if not os.path.exists(layout.momentos(pd)):
        sys.exit(f"{layout.momentos(pd)} não existe. Faça a curadoria primeiro.")
    render.render_all(pd, platforms_from_args(args),
                      only=args.only.split(",") if args.only else None)


def cmd_thumb(args):
    """Gera a thumbnail: base vem do JSON, flags explícitas sobrescrevem."""
    pd = project_dir(args.projeto)

    # Sem --frame-at, sugere instantes dentro dos cortes aprovados: é onde o
    # convidado está falando com energia. A escolha continua sendo visual.
    if args.frame_at is None:
        mpath = layout.momentos(pd)
        if os.path.exists(mpath):
            with open(mpath, encoding="utf-8") as f:
                sug = thumbnail.sugere_frames(json.load(f))
            if sug:
                print("[thumb] candidatos (dentro dos cortes aprovados): "
                      + ", ".join(f"{t:.0f}s" for t in sug))
                print("[thumb] extraia e escolha: "
                      f"python run.py thumb --projeto {args.projeto} --frame-at <s>")
        sys.exit("[thumb] informe --frame-at <segundos>")
    video = layout.video(pd)

    # O frame extraído é intermediário, não produto — vai para um temp real em
    # vez de sujar a raiz do projeto (era o `_thumb_frame.jpg` de antes).
    fd, frame = tempfile.mkstemp(suffix=".jpg", prefix="talaria_thumb_")
    os.close(fd)
    try:
        thumbnail.extract_frame(video, args.frame_at, frame)

        # Base vem do episodio.json/textos.json; flags explícitas sobrescrevem.
        try:
            base = textos.build_kwargs(pd)
        except FileNotFoundError:
            base = {"selo": "", "chamada_l1": "", "chamada_l2": "",
                    "creditos": "", "subtitulo": ""}
        for flag, campo in (("selo", "selo"), ("l1", "chamada_l1"), ("l2", "chamada_l2"),
                            ("creditos", "creditos"), ("subtitulo", "subtitulo")):
            valor = getattr(args, flag, "")
            if valor:
                base[campo] = valor

        thumbnail.build_thumbnail(frame, layout.garante(layout.thumbnail(pd)), **base)
    finally:
        if os.path.exists(frame):
            os.remove(frame)


def cmd_ingest(args):
    """Baixa o vídeo e converte a transcrição .txt em transcricao.json."""
    pd = project_dir(args.projeto)

    # Valida a transcrição ANTES de baixar: um path errado desperdiçava o
    # download inteiro do vídeo para só depois falhar no parse_txt.
    if args.transcricao and not os.path.exists(args.transcricao):
        sys.exit(f"transcrição não encontrada: {args.transcricao}")

    os.makedirs(pd, exist_ok=True)

    acquire.acquire(args.src, pd)

    if args.transcricao:
        video = layout.video(pd)
        dur = None
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", video],
                capture_output=True, text=True, check=True).stdout.strip()
            dur = float(out)
        except Exception:  # noqa: BLE001
            print("[ingest] não consegui medir a duração; último segmento estimado.")
        segs = txt_parse.parse_txt(args.transcricao, total_duration=dur)
        transcricao_path = layout.garante(layout.transcricao(pd))
        with open(transcricao_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f, ensure_ascii=False, indent=2)
        print(f"[ingest] {len(segs)} segmentos -> {transcricao_path}")
    else:
        print("[ingest] sem --transcricao; rode 'transcribe' para usar o Whisper.")

    ep_path = layout.episodio(pd)
    if not os.path.exists(ep_path):
        episodio.save(pd, episodio.template())
        print(f"[ingest] template criado -> {ep_path} (preencha antes do brief)")


def cmd_brief(args):
    """Monta o pacote de leitura (materiais ou cortes) para o Claude."""
    pd = project_dir(args.projeto)
    # --cortes e --materiais são mutuamente exclusivas (ver add_mutually_exclusive_group);
    # sem nenhuma das duas, o default é 'materiais'.
    tipo = "cortes" if args.cortes else "materiais"
    out = brief.montar(pd, tipo)
    print(f"[brief] {tipo} -> {out}")


def _segmentos(pd):
    """Segmentos da transcrição, ou [] se o projeto ainda não tem uma."""
    path = layout.transcricao(pd)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("segments", [])


def cmd_curar(args):
    """Mostra o estado da curadoria e exporta momentos.json quando fecha."""
    pd = project_dir(args.projeto)
    ja_existia = os.path.exists(layout.curadoria(pd))
    estado = curadoria.load(pd, meta=args.meta)

    # Estado já gravado manda na meta — --meta só vale ao criar a curadoria.
    # Sem este aviso, `curar --meta 8` sobre um estado com meta 5 seguia em
    # silêncio com a meta antiga.
    if ja_existia and estado["meta"] != args.meta:
        print(f"[curar] aviso: estado gravado tem meta {estado['meta']}, "
              f"ignorando --meta {args.meta}")

    if args.exportar:
        try:
            path = curadoria.salvar_momentos(pd, estado)
        except ValueError as e:   # nada aprovado ainda: erro do operador, não bug
            sys.exit(f"[curar] {e}")
        print(f"[curar] {len(estado['aprovados'])} cortes -> {path}")
        return

    # Revalida o que já está aprovado: o estado pode ter sido gravado antes de
    # uma regra nova existir (fim em frase completa, sobreposição entre
    # aprovados). Sem isto o problema só aparece no vídeo renderizado.
    segs = _segmentos(pd)
    if segs:
        if not curadoria.atribuicao_confiavel(segs):
            print("[curar] aviso: atribuição de falante inconsistente neste "
                  "episódio — protagonismo e abertura não foram checados; "
                  "confira no vídeo renderizado.")
        for c in estado.get("aprovados", []):
            ok, msgs = curadoria.valida_corte((c["start"], c["end"]), segs, {})
            if not ok:
                print(f"[curar] !! {c.get('slug')}: {'; '.join(msgs)}")
            for a in curadoria.alertas_corte((c["start"], c["end"]), segs):
                print(f"[curar] ?  {c.get('slug')}: {a}")

    comp = curadoria.composicao(estado)
    print(f"[curar] rodada {estado['rodadas']} | "
          f"{len(estado['aprovados'])}/{estado['meta']} aprovados | "
          f"{len(estado['rejeitados'])} rejeitados")
    print("[curar] composição: " + ", ".join(f"{t}={n}" for t, n in comp.items()))
    ausentes = curadoria.tipos_ausentes(estado)
    if ausentes:
        print(f"[curar] tipos ausentes: {', '.join(ausentes)}")
    ms = curadoria.motivos(estado)
    if ms:
        print(f"[curar] motivos de rejeição acumulados: {'; '.join(ms)}")
    if curadoria.fechado(estado):
        print("[curar] meta atingida — rode com --exportar para gerar momentos.json")
    else:
        print(f"[curar] faltam {curadoria.vagas(estado)} cortes")
    curadoria.save(pd, estado)


def cmd_post(args):
    """Dois passos: --cortes monta o pacote de leitura, --gerar renderiza."""
    pd = project_dir(args.projeto)

    if args.gerar:
        try:
            gerados = post_instagram.gerar(pd)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(str(e))
        print(f"\n{len(gerados)} imagem(ns) em {layout.posts_png(pd)}/")
        return

    momentos_path = layout.momentos(pd)
    if not os.path.exists(momentos_path):
        sys.exit(f"{momentos_path} não existe. Rode 'curar --exportar' antes.")
    with open(momentos_path, encoding="utf-8") as f:
        momentos = json.load(f)

    if args.cortes:
        try:
            querido = {int(n) for n in args.cortes.split(",") if n.strip()}
        except ValueError:
            sys.exit(f"--cortes aceita números separados por vírgula "
                     f"(ex.: 1,3) — recebido {args.cortes!r}")
        escolhidos = [m for i, m in enumerate(momentos, start=1) if i in querido]
        if not escolhidos:
            sys.exit(f"nenhum corte com os números {sorted(querido)} "
                     f"(o episódio tem {len(momentos)})")
    else:
        escolhidos = momentos

    out = brief.montar_posts(pd, escolhidos)
    print(f"\n>>> Leia {out}, escolha as citações comigo e grave "
          f"{layout.posts(pd)}. Depois rode 'post --gerar'.")


def cmd_publish(args):
    """Publica o que o calendário manda para hoje (ou --only, fora da data)."""
    pd = project_dir(args.projeto)
    only = ([s.strip() for s in args.only.split(",") if s.strip()]
            if args.only else None)
    plataformas = ([s.strip() for s in args.plataforma.split(",") if s.strip()]
                   if args.plataforma else None)
    try:
        resultados = publish.executar(pd, only=only, plataformas=plataformas)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))

    if not resultados:
        print(f"[publish] nada agendado para hoje "
              f"({calendario.hoje().isoformat()})")
        return

    hoje = calendario.hoje().isoformat()
    for r in resultados:
        if r["data"] < hoje:
            # Mostra a data ORIGINAL: o gestor precisa ver que atrasou.
            print(f"[publish]    ({r['slug']} estava agendado para {r['data']})")
    for pl in ("youtube_shorts", "instagram_reels", "instagram_posts"):
        do_pl = [r for r in resultados if r["plataforma"] == pl]
        if not do_pl:
            continue
        ok = [r for r in do_pl if r["ok"]]
        ruim = [r for r in do_pl if not r["ok"]]
        linha = f"[publish] {pl}: {len(ok)} ok, {len(ruim)} falhou"
        if ruim:
            linha += " (" + "; ".join(f"{r['slug']}: {r['erro']}"
                                      for r in ruim) + ")"
        print(linha)

    # Peça no ar cujo registro falhou: o publicado.json não sabe dela, então
    # o próximo publish a mandaria de novo. É o aviso mais importante da
    # execução e sai por último, onde o gestor olha.
    sem_registro = [r for r in resultados if r.get("registro_falhou")]
    if sem_registro:
        print(f"\n[publish] !! {len(sem_registro)} peça(s) NO AR e fora do "
              f"{layout.publicado(pd)}:")
        for r in sem_registro:
            print(f"[publish]    {r['plataforma']} {r['slug']} -> id {r['id']}"
                  f" ({r['url'] or 'sem url'})")
        print("[publish]    Acrescente esses ids ao publicado.json ANTES de "
              "rodar publish de novo, ou as peças saem duplicadas.")

    if any(not r["ok"] for r in resultados) or sem_registro:
        sys.exit(1)


def cmd_agenda(args):
    """Mostra a agenda com o status de cada item, sem publicar nada."""
    pd = project_dir(args.projeto)
    try:
        agenda = calendario.carrega(pd)
        reg = publicado.carrega(pd)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))
    hoje = calendario.hoje()
    for item in agenda:
        pls = calendario.plataformas_do(item)
        feitos = [pl for pl in pls
                  if publicado.ja_publicado(reg, pl, item["slug"])]
        d = calendario.data_do(item)
        if len(feitos) == len(pls):
            status = "✓ publicado"
        elif feitos:
            faltam = [p for p in pls if p not in feitos]
            status = f"parcial — falta {', '.join(faltam)}"
        elif d < hoje:
            status = "ATRASADO"
        elif d == hoje:
            status = "pendente hoje"
        else:
            status = "futuro"
        print(f"  {item['data']}  {item['tipo']:<5}  "
              f"{item['slug']:<32}  {status}")


def main():
    p = argparse.ArgumentParser(description="Next-Video-Shorts pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--projeto", required=True, help="slug do projeto (pasta em projetos/)")

    sp = sub.add_parser("acquire", help="baixa/copia o vídeo")
    add_common(sp); sp.add_argument("--src", required=True); sp.set_defaults(func=cmd_acquire)

    sp = sub.add_parser("transcribe", help="transcreve (legenda YT ou Whisper)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("prep", help="acquire + transcribe (para antes da curadoria)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_prep)

    sp = sub.add_parser("render", help="renderiza os cortes de momentos.json")
    add_common(sp)
    sp.add_argument("--youtube", action="store_true", help="gera YouTube Shorts")
    sp.add_argument("--instagram", action="store_true", help="gera Instagram Reels")
    sp.add_argument("--only", default=None, help="renderiza só estes slugs (vírgula)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("thumb", help="gera a thumbnail do YouTube")
    add_common(sp)
    sp.add_argument("--frame-at", type=float,
                    help="segundo do frame de fundo; sem ele, sugere candidatos")
    sp.add_argument("--selo", default="")
    sp.add_argument("--l1", default="", help="1ª linha da chamada (branca)")
    sp.add_argument("--l2", default="", help="2ª linha da chamada (laranja)")
    sp.add_argument("--creditos", default="")
    sp.add_argument("--subtitulo", default="")
    sp.set_defaults(func=cmd_thumb)

    sp = sub.add_parser("ingest", help="baixa o vídeo + converte a transcrição .txt")
    add_common(sp)
    sp.add_argument("--src", required=True, help="link do arquivo no Drive ou path local")
    sp.add_argument("--transcricao", default=None, help="path do .txt com timestamps")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("brief", help="monta o pacote de leitura para o Claude")
    add_common(sp)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--materiais", action="store_true",
                   help="prompt de título/descrição (default)")
    g.add_argument("--cortes", action="store_true", help="prompt de seleção de cortes")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("curar", help="estado da curadoria iterativa")
    add_common(sp)
    sp.add_argument("--meta", type=int, default=5, help="quantos cortes aprovar")
    sp.add_argument("--exportar", action="store_true", help="gera momentos.json")
    sp.set_defaults(func=cmd_curar)

    sp = sub.add_parser("post", help="posts de citação para Instagram")
    add_common(sp)
    sp.add_argument("--cortes", default="",
                    help="números dos cortes, ex.: 1,3 (vazio = todos)")
    sp.add_argument("--gerar", action="store_true",
                    help="renderiza a partir do posts.json")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("publish",
                        help="publica o que o calendário manda para hoje")
    add_common(sp)
    sp.add_argument("--only", default="",
                    help="slugs específicos, fora da data agendada "
                         "(ex.: corte1,cit_x) — não republica o que já foi")
    sp.add_argument("--plataforma", default="",
                    help="publica só nestas plataformas (ex.: youtube_shorts) "
                         "— o resto do corte segue pendente para depois")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("agenda", help="mostra a agenda e o status de cada item")
    add_common(sp)
    sp.set_defaults(func=cmd_agenda)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
