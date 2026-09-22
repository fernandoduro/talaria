"""Onde cada arquivo do project mora. Autoridade única sobre os caminhos.

Antes disto cada módulo montava o seu com string literal
(`os.path.join(project_dir, "moments.json")` aparecia em 5 arquivos), e o
resultado era uma dúzia de arquivos soltos na raiz do episódio, de naturezas
diferentes misturadas.

A pasta é organizada por NATUREZA:

    <slug>/episode.json     o gestor preenche à mão — fica na raiz de
                             propósito, para não esconder a única tarefa manual
    <slug>/fonte/            entrada: vídeo e transcrição
    <slug>/decisions/         o que o gestor e o modelo decidiram
    <slug>/briefs/           pacotes de leitura, regeneráveis
    <slug>/publish/         o que vai ao ar
"""
from __future__ import annotations

import os

SOURCE = "source"
DECISIONS = "decisions"
BRIEFS = "briefs"
PUBLISH = "publish"


def ensure_dir(path: str) -> str:
    """Cria a pasta do arquivo, se preciso. Devolve o próprio path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def episode(pd: str) -> str:
    return os.path.join(pd, "episode.json")


def video(pd: str) -> str:
    return os.path.join(pd, SOURCE, "video.mp4")


def transcript(pd: str) -> str:
    return os.path.join(pd, SOURCE, "transcript.json")


def transcript_txt(pd: str) -> str:
    return os.path.join(pd, SOURCE, "transcript.txt")


def source_dir(pd: str) -> str:
    return os.path.join(pd, SOURCE)


def curation(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "curation.json")


def moments(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "moments.json")


def texts(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "texts.json")


def posts(pd: str) -> str:
    return os.path.join(pd, DECISIONS, "posts.json")


def schedule(pd: str) -> str:
    """Agenda de publicação: que peça sai em que dia. Decisão editorial."""
    return os.path.join(pd, DECISIONS, "schedule.json")


def published(pd: str) -> str:
    """Registro do que já foi ao ar — a trava contra post duplicado."""
    return os.path.join(pd, DECISIONS, "published.json")


def brief(pd: str, kind: str) -> str:
    """kind: 'materials' | 'clips' | 'posts'."""
    return os.path.join(pd, BRIEFS, f"{kind}.md")


def thumbnail(pd: str) -> str:
    return os.path.join(pd, PUBLISH, "thumbnail.jpg")


def end_card_mp4(pd: str) -> str:
    """Card de end_card cacheado — igual em todo clip do episódio.

    Fica na raiz de `publish/`, como a thumbnail: artefato do episódio, não
    de uma peça, e nunca é commitado (`projects/` inteiro é git-ignored).
    """
    return os.path.join(pd, PUBLISH, "_end_card.mp4")


def episode_txt(pd: str) -> str:
    """Título e descrição do episódio, prontos para colar no YouTube.

    Fica na raiz de `publish/`, ao lado da thumbnail: os dois são do episódio
    inteiro, não de uma peça — por isso não entram nas pastas de platform.
    """
    return os.path.join(pd, PUBLISH, "episode.txt")


def platform(pd: str, name: str) -> str:
    """Pasta de saída de uma platform de vídeo (youtube_shorts, ...)."""
    return os.path.join(pd, PUBLISH, name)


def posts_png(pd: str) -> str:
    return os.path.join(pd, PUBLISH, "instagram_posts")


# Posição antiga -> nova. O prefixo do name antigo era necessário quando tudo
# ficava na mesma pasta; dentro da subpasta ele vira redundância.
_MIGRATION = [
    ("source.mp4", video),
    ("transcript.json", transcript),
    ("transcript.txt", transcript_txt),
    ("curation.json", curation),
    ("moments.json", moments),
    ("texts.json", texts),
    ("posts.json", posts),
    ("brief_materiais.md", lambda pd: brief(pd, "materials")),
    ("brief_cortes.md", lambda pd: brief(pd, "clips")),
    ("brief_posts.md", lambda pd: brief(pd, "posts")),
    ("thumbnail.jpg", thumbnail),
]

# Pastas de saída que só mudam de lugar, sem renomear o conteúdo.
# Nome da pasta de cada platform. Nomeadas porque não são só diretório: o
# `render` distingue por elas qual caption recebe a chamada do episódio (a
# do YouTube), já que o mp4 das duas é idêntico e só o diretório difere.
YOUTUBE_SHORTS = "youtube_shorts"
INSTAGRAM_REELS = "instagram_reels"
INSTAGRAM_POSTS = "instagram_posts"

_PUBLISH_DIRS = (YOUTUBE_SHORTS, INSTAGRAM_REELS, INSTAGRAM_POSTS)

# Temporários que vazaram para a raiz em versões anteriores.
_JUNK = ("_thumb_frame.jpg",)


def _check_dirs(pd: str) -> None:
    """Recusa migrate se um name de pasta estiver ocupado por um arquivo.

    Sem isto o `shutil.move` explode no meio com um FileExistsError cru, que
    não diz ao gestor o que ele precisa resolver — e deixa o project meio
    migrado.
    """
    for name in (SOURCE, DECISIONS, BRIEFS, PUBLISH):
        path = os.path.join(pd, name)
        if os.path.exists(path) and not os.path.isdir(path):
            raise RuntimeError(
                f"'{name}' precisa ser uma pasta, mas é um arquivo em {pd}. "
                f"Renomeie ou remova esse arquivo e rode de novo."
            )


def migrate(pd: str) -> list:
    """Move um project da estrutura antiga (tudo solto) para a nova.

    Idempotente: roda no início de todo comando e não faz nada quando o project
    já está organizado. Devolve a lista de (origem, destino) do que moveu.

    Quando o arquivo existe nas DUAS posições, a nova vence — é o que os
    comandos vêm escrevendo desde a migração. A antiga NÃO é apagada: vira
    `.bak` e entra no relatório. O gestor pode ter copiado um backup para a
    raiz de propósito, e apagar o trabalho dele em silêncio seria pior que
    deixar um arquivo sobrando.

    Move item a item, sem estado intermediário: interrupção no meio deixa o
    project parcialmente migrado, e rodar de novo termina o serviço.
    """
    import shutil

    if not os.path.isdir(pd):
        return []

    _check_dirs(pd)
    movidos = []

    for antigo, destino_de in _MIGRATION:
        origem = os.path.join(pd, antigo)
        if not os.path.exists(origem):
            continue
        destino = destino_de(pd)
        if os.path.exists(destino):
            bak = origem + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
            os.rename(origem, bak)
            nota = "(duplicata)"
            # Sinaliza quando o descartado é maior que o ativo: pode ser um
            # arquivo pela metade na posição nova (escrita interrompida) que
            # passaria a valer sem ninguém notar. O tamanho não decide nada —
            # JSON menor é normal —, mas o gestor precisa ver para conferir.
            try:
                if os.path.getsize(bak) > os.path.getsize(destino):
                    nota = "(duplicata — o .bak é MAIOR, confira qual vale)"
            except OSError:
                pass
            movidos.append((antigo, os.path.basename(bak) + " " + nota))
            continue
        ensure_dir(destino)
        shutil.move(origem, destino)
        movidos.append((antigo, os.path.relpath(destino, pd)))

    for name in _PUBLISH_DIRS:
        origem = os.path.join(pd, name)
        if not os.path.isdir(origem):
            continue
        destino = os.path.join(pd, PUBLISH, name)

        if not os.path.isdir(destino):
            os.makedirs(os.path.join(pd, PUBLISH), exist_ok=True)
            shutil.move(origem, destino)
            movidos.append((name + "/", os.path.relpath(destino, pd) + "/"))
            continue

        # As duas existem: traz o que só está na antiga e some com ela. Pular
        # deixaria clip já renderizado fora da estrutura documentada, sem
        # aviso — e ele sumiria na próxima limpeza da pasta do episódio.
        for arquivo in sorted(os.listdir(origem)):
            alvo = os.path.join(destino, arquivo)
            atual = os.path.join(origem, arquivo)
            if os.path.exists(alvo):
                # O da posição nova vale; o antigo vira .bak ao lado dele, pela
                # mesma razão dos arquivos soltos: não destruir em silêncio.
                bak = alvo + ".bak"
                if os.path.exists(bak):
                    os.remove(bak)
                shutil.move(atual, bak)
                movidos.append((f"{name}/{arquivo}",
                                os.path.relpath(bak, pd) + " (duplicata)"))
                continue
            shutil.move(atual, alvo)
            movidos.append((f"{name}/{arquivo}", os.path.relpath(alvo, pd)))
        if not os.listdir(origem):
            os.rmdir(origem)

    for name in _JUNK:
        path = os.path.join(pd, name)
        if os.path.exists(path):
            os.remove(path)
            movidos.append((name, "(removido)"))

    return movidos
