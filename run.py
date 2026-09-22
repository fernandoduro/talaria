#!/usr/bin/env python3
"""Talaria — orquestrador CLI.

Fluxo por vídeo (rodado por um modelo de linguagem, com curation manual):

  1. ingest     : baixa o vídeo + converte a transcrição .txt -> transcript.json
                  (ou acquire + transcribe, quando a transcrição vem do Whisper)
  2. [episode.json]: o gestor preenche os metadados do episódio
  3. brief      : compose o pacote de leitura (--cortes ou --materiais) p/ o modelo
  4. curate      : estado da curation iterativa; --export gera moments.json
  5. render     : gera os cortes 9:16 com legenda p/ as plataformas escolhidas
  6. thumb      : gera a thumbnail (texts do JSON, flags sobrescrevem)
  7. post       : posts de citação p/ Instagram; --cortes compose o pacote,
                  --generate renderiza os PNGs a partir do posts.json

Exemplos:
  python run.py acquire  --project ep2 --src "https://youtu.be/VIDEO_ID"
  python run.py transcribe --project ep2 --src "https://youtu.be/VIDEO_ID"
  python run.py render   --project ep2 --youtube --instagram
  python run.py ingest   --project ep2 --src "https://youtu.be/VIDEO_ID" \\
      --transcript ~/Downloads/ep2.txt
  python run.py brief    --project ep2 --cortes
  python run.py curate    --project ep2 --target 5
  python run.py thumb    --project ep2 --frame-at 1745       # texts do JSON
  python run.py post     --project ep2 --cortes 1,3
  python run.py post     --project ep2 --generate

  # acquire + transcribe de uma vez (para antes da curation):
  python run.py prep     --project ep2 --src "https://youtu.be/VIDEO_ID"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from talaria import (acquire, environment, brief, schedule, curation,
                      episode, layout, post_instagram, published, publish,
                      render, texts, thumbnail, transcribe, txt_parse)

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.join(ROOT, "projects")

# O `.env` entra no environment antes de qualquer comando: os módulos de
# publicação leem credencial de os.environ, e sem isto o arquivo preenchido
# não chegava neles — o publish reclamava de variável faltando com a resposta
# aberta na tela do gestor.
environment.load()


def project_dir(slug: str) -> str:
    """Caminho do project, reorganizando o layout antigo se for o caso.

    Todo comando passa por aqui, então episódio criado antes da separação por
    natureza (fonte/decisions/briefs/publish) é migrado na primeira execução,
    sem o gestor pedir. `layout.migrate` é idempotente: nas vezes seguintes não
    move nada e não imprime nada.
    """
    pd = os.path.join(PROJECTS, slug)
    movidos = layout.migrate(pd)
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
    pd = project_dir(args.project)
    acquire.acquire(args.src, pd)


def cmd_transcribe(args):
    pd = project_dir(args.project)
    video = layout.video(pd)
    if not os.path.exists(video):
        sys.exit(f"{video} não existe. Rode 'acquire' antes.")
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)


def cmd_prep(args):
    pd = project_dir(args.project)
    acquire.acquire(args.src, pd)
    video = layout.video(pd)
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)
    print(f"\n>>> Pronto para curadoria. Leia {layout.transcript_txt(pd)} e crie "
          f"{layout.moments(pd)}, depois rode 'render'.")


def cmd_render(args):
    pd = project_dir(args.project)
    if not os.path.exists(layout.moments(pd)):
        sys.exit(f"{layout.moments(pd)} não existe. Faça a curadoria primeiro.")
    render.render_all(pd, platforms_from_args(args),
                      only=args.only.split(",") if args.only else None)


def cmd_thumb(args):
    """Gera a thumbnail: base vem do JSON, flags explícitas sobrescrevem."""
    pd = project_dir(args.project)

    # Sem --frame-at, sugere instantes dentro dos cortes approved: é onde o
    # convidado está falando com energia. A escolha continua sendo visual.
    if args.frame_at is None:
        mpath = layout.moments(pd)
        if os.path.exists(mpath):
            with open(mpath, encoding="utf-8") as f:
                sug = thumbnail.suggest_frames(json.load(f))
            if sug:
                print("[thumb] candidatos (dentro dos cortes aprovados): "
                      + ", ".join(f"{t:.0f}s" for t in sug))
                print("[thumb] extraia e escolha: "
                      f"python run.py thumb --project {args.project} --frame-at <s>")
        sys.exit("[thumb] informe --frame-at <segundos>")
    video = layout.video(pd)

    # O frame extraído é intermediário, não produto — vai para um temp real em
    # vez de sujar a raiz do project (era o `_thumb_frame.jpg` de antes).
    fd, frame = tempfile.mkstemp(suffix=".jpg", prefix="talaria_thumb_")
    os.close(fd)
    try:
        thumbnail.extract_frame(video, args.frame_at, frame)

        # Base vem do episode.json/texts.json; flags explícitas sobrescrevem.
        try:
            base = texts.build_kwargs(pd)
        except FileNotFoundError:
            base = {"badge": "", "headline_l1": "", "headline_l2": "",
                    "credits": "", "subtitle": ""}
        for flag, campo in (("badge", "badge"), ("l1", "headline_l1"), ("l2", "headline_l2"),
                            ("credits", "credits"), ("subtitle", "subtitle")):
            valor = getattr(args, flag, "")
            if valor:
                base[campo] = valor

        thumbnail.build_thumbnail(frame, layout.ensure_dir(layout.thumbnail(pd)), **base)
    finally:
        if os.path.exists(frame):
            os.remove(frame)


def cmd_ingest(args):
    """Baixa o vídeo e converte a transcrição .txt em transcript.json."""
    pd = project_dir(args.project)

    # Valida a transcrição ANTES de baixar: um path errado desperdiçava o
    # download inteiro do vídeo para só depois falhar no parse_txt.
    if args.transcript and not os.path.exists(args.transcript):
        sys.exit(f"transcrição não encontrada: {args.transcript}")

    os.makedirs(pd, exist_ok=True)

    acquire.acquire(args.src, pd)

    if args.transcript:
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
        segs = txt_parse.parse_txt(args.transcript, total_duration=dur)
        transcricao_path = layout.ensure_dir(layout.transcript(pd))
        with open(transcricao_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f, ensure_ascii=False, indent=2)
        print(f"[ingest] {len(segs)} segmentos -> {transcricao_path}")
    else:
        print("[ingest] sem --transcript; rode 'transcribe' para usar o Whisper.")

    ep_path = layout.episode(pd)
    if not os.path.exists(ep_path):
        episode.save(pd, episode.template())
        print(f"[ingest] template criado -> {ep_path} (preencha antes do brief)")


def cmd_brief(args):
    """Monta o pacote de leitura (materiais ou cortes) para o modelo."""
    pd = project_dir(args.project)
    # --cortes e --materiais são mutuamente exclusivas (ver add_mutually_exclusive_group);
    # sem nenhuma das duas, o default é 'materiais'.
    kind = "clips" if args.clips else "materials"
    out = brief.build(pd, kind)
    print(f"[brief] {kind} -> {out}")


def _segments(pd):
    """Segmentos da transcrição, ou [] se o project ainda não tem uma."""
    path = layout.transcript(pd)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("segments", [])


def cmd_curate(args):
    """Mostra o estado da curation e exporta moments.json quando fecha."""
    pd = project_dir(args.project)
    ja_existia = os.path.exists(layout.curation(pd))
    estado = curation.load(pd, target=args.target)

    # Estado já gravado manda na target — --target só vale ao criar a curation.
    # Sem este aviso, `curate --target 8` sobre um estado com target 5 seguia em
    # silêncio com a target antiga.
    if ja_existia and estado["target"] != args.target:
        print(f"[curate] aviso: estado gravado tem target {estado['target']}, "
              f"ignorando --target {args.target}")

    if args.export:
        try:
            path = curation.save_moments(pd, estado)
        except ValueError as e:   # nada aprovado ainda: error do operador, não bug
            sys.exit(f"[curate] {e}")
        print(f"[curate] {len(estado['approved'])} cortes -> {path}")
        return

    # Revalida o que já está aprovado: o estado pode ter sido gravado antes de
    # uma regra nova existir (fim em frase completa, sobreposição entre
    # approved). Sem isto o problema só aparece no vídeo renderizado.
    segs = _segments(pd)
    if segs:
        if not curation.attribution_trustworthy(segs):
            print("[curate] aviso: atribuição de falante inconsistente neste "
                  "episódio — protagonismo e abertura não foram checados; "
                  "confira no vídeo renderizado.")
        for c in estado.get("approved", []):
            ok, msgs = curation.validate_clip((c["start"], c["end"]), segs, {})
            if not ok:
                print(f"[curate] !! {c.get('slug')}: {'; '.join(msgs)}")
            for a in curation.clip_warnings((c["start"], c["end"]), segs):
                print(f"[curate] ?  {c.get('slug')}: {a}")

    comp = curation.composition(estado)
    print(f"[curate] rodada {estado['rounds']} | "
          f"{len(estado['approved'])}/{estado['target']} aprovados | "
          f"{len(estado['rejected'])} rejeitados")
    print("[curate] composição: " + ", ".join(f"{t}={n}" for t, n in comp.items()))
    ausentes = curation.missing_kinds(estado)
    if ausentes:
        print(f"[curate] tipos ausentes: {', '.join(ausentes)}")
    ms = curation.reasons(estado)
    if ms:
        print(f"[curate] motivos de rejeição acumulados: {'; '.join(ms)}")
    if curation.is_closed(estado):
        print("[curate] target atingida — rode com --export para gerar moments.json")
    else:
        print(f"[curate] faltam {curation.slots_left(estado)} cortes")
    curation.save(pd, estado)


def cmd_post(args):
    """Dois passos: --cortes compose o pacote de leitura, --generate renderiza."""
    pd = project_dir(args.project)

    if args.generate:
        try:
            gerados = post_instagram.generate(pd)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(str(e))
        print(f"\n{len(gerados)} imagem(ns) em {layout.posts_png(pd)}/")
        return

    momentos_path = layout.moments(pd)
    if not os.path.exists(momentos_path):
        sys.exit(f"{momentos_path} não existe. Rode 'curate --export' antes.")
    with open(momentos_path, encoding="utf-8") as f:
        moments = json.load(f)

    if args.clips:
        try:
            querido = {int(n) for n in args.clips.split(",") if n.strip()}
        except ValueError:
            sys.exit(f"--clips aceita números separados por vírgula "
                     f"(ex.: 1,3) — recebido {args.clips!r}")
        escolhidos = [m for i, m in enumerate(moments, start=1) if i in querido]
        if not escolhidos:
            sys.exit(f"nenhum corte com os números {sorted(querido)} "
                     f"(o episódio tem {len(moments)})")
    else:
        escolhidos = moments

    out = brief.build_posts(pd, escolhidos)
    print(f"\n>>> Leia {out}, escolha as citações comigo e grave "
          f"{layout.posts(pd)}. Depois rode 'post --generate'.")


def cmd_publish(args):
    """Publica o que o calendário manda para hoje (ou --only, fora da data)."""
    pd = project_dir(args.project)
    only = ([s.strip() for s in args.only.split(",") if s.strip()]
            if args.only else None)
    plataformas = ([s.strip() for s in args.platform.split(",") if s.strip()]
                   if args.platform else None)
    try:
        resultados = publish.execute(pd, only=only, plataformas=plataformas)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))

    if not resultados:
        print(f"[publish] nada agendado para hoje "
              f"({schedule.today().isoformat()})")
        return

    today = schedule.today().isoformat()
    for r in resultados:
        if r["date"] < today:
            # Mostra a data ORIGINAL: o gestor precisa ver que atrasou.
            print(f"[publish]    ({r['slug']} estava agendado para {r['date']})")
    for pl in ("youtube_shorts", "instagram_reels", "instagram_posts"):
        do_pl = [r for r in resultados if r["platform"] == pl]
        if not do_pl:
            continue
        ok = [r for r in do_pl if r["ok"]]
        ruim = [r for r in do_pl if not r["ok"]]
        linha = f"[publish] {pl}: {len(ok)} ok, {len(ruim)} falhou"
        if ruim:
            linha += " (" + "; ".join(f"{r['slug']}: {r['error']}"
                                      for r in ruim) + ")"
        print(linha)

    # Peça no ar cujo registro falhou: o published.json não sabe dela, então
    # o próximo publish a mandaria de novo. É o aviso mais importante da
    # execução e sai por último, onde o gestor olha.
    sem_registro = [r for r in resultados if r.get("record_failed")]
    if sem_registro:
        print(f"\n[publish] !! {len(sem_registro)} peça(s) NO AR e fora do "
              f"{layout.published(pd)}:")
        for r in sem_registro:
            print(f"[publish]    {r['platform']} {r['slug']} -> id {r['id']}"
                  f" ({r['url'] or 'sem url'})")
        print("[publish]    Acrescente esses ids ao published.json ANTES de "
              "rodar publish de novo, ou as peças saem duplicadas.")

    if any(not r["ok"] for r in resultados) or sem_registro:
        sys.exit(1)


def cmd_schedule(args):
    """Mostra a agenda com o status de cada item, sem publish nada."""
    pd = project_dir(args.project)
    try:
        items = schedule.load(pd)
        reg = published.load(pd)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))
    today = schedule.today()
    for item in items:
        pls = schedule.platforms_of(item)
        feitos = [pl for pl in pls
                  if published.is_published(reg, pl, item["slug"])]
        d = schedule.date_of(item)
        if len(feitos) == len(pls):
            status = "✓ publicado"
        elif feitos:
            faltam = [p for p in pls if p not in feitos]
            status = f"parcial — falta {', '.join(faltam)}"
        elif d < today:
            status = "ATRASADO"
        elif d == today:
            status = "pendente hoje"
        else:
            status = "futuro"
        print(f"  {item['date']}  {item['kind']:<5}  "
              f"{item['slug']:<32}  {status}")


def main():
    p = argparse.ArgumentParser(description="Talaria — pipeline de cortes verticais")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--project", required=True, help="slug do projeto (pasta em projects/)")

    sp = sub.add_parser("acquire", help="baixa/copia o vídeo")
    add_common(sp); sp.add_argument("--src", required=True); sp.set_defaults(func=cmd_acquire)

    sp = sub.add_parser("transcribe", help="transcreve (legenda YT ou Whisper)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("prep", help="acquire + transcribe (para antes da curadoria)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_prep)

    sp = sub.add_parser("render", help="renderiza os cortes de moments.json")
    add_common(sp)
    sp.add_argument("--youtube", action="store_true", help="gera YouTube Shorts")
    sp.add_argument("--instagram", action="store_true", help="gera Instagram Reels")
    sp.add_argument("--only", default=None, help="renderiza só estes slugs (vírgula)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("thumb", help="gera a thumbnail do YouTube")
    add_common(sp)
    sp.add_argument("--frame-at", type=float,
                    help="segundo do frame de fundo; sem ele, sugere candidatos")
    sp.add_argument("--badge", default="")
    sp.add_argument("--l1", default="", help="1ª linha da chamada (branca)")
    sp.add_argument("--l2", default="", help="2ª linha da chamada (laranja)")
    sp.add_argument("--credits", default="")
    sp.add_argument("--subtitle", default="")
    sp.set_defaults(func=cmd_thumb)

    sp = sub.add_parser("ingest", help="baixa o vídeo + converte a transcrição .txt")
    add_common(sp)
    sp.add_argument("--src", required=True, help="link do arquivo no Drive ou path local")
    sp.add_argument("--transcript", default=None, help="path do .txt com timestamps")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("brief", help="monta o pacote de leitura para o modelo")
    add_common(sp)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--materials", action="store_true",
                   help="prompt de título/descrição (default)")
    g.add_argument("--clips", action="store_true", help="prompt de seleção de cortes")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("curate", help="estado da curadoria iterativa")
    add_common(sp)
    sp.add_argument("--target", type=int, default=5, help="quantos cortes aprovar")
    sp.add_argument("--export", action="store_true", help="gera moments.json")
    sp.set_defaults(func=cmd_curate)

    sp = sub.add_parser("post", help="posts de citação para Instagram")
    add_common(sp)
    sp.add_argument("--clips", default="",
                    help="números dos cortes, ex.: 1,3 (vazio = todos)")
    sp.add_argument("--generate", action="store_true",
                    help="renderiza a partir do posts.json")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("publish",
                        help="publica o que o calendário manda para hoje")
    add_common(sp)
    sp.add_argument("--only", default="",
                    help="slugs específicos, fora da data agendada "
                         "(ex.: corte1,cit_x) — não republica o que já foi")
    sp.add_argument("--platform", default="",
                    help="publica só nestas plataformas (ex.: youtube_shorts) "
                         "— o resto do corte segue pendente para depois")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("schedule", help="mostra a agenda e o status de cada item")
    add_common(sp)
    sp.set_defaults(func=cmd_schedule)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
