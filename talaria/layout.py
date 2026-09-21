"""Onde cada arquivo do projeto mora. Autoridade única sobre os caminhos.

Antes disto cada módulo montava o seu com string literal
(`os.path.join(project_dir, "momentos.json")` aparecia em 5 arquivos), e o
resultado era uma dúzia de arquivos soltos na raiz do episódio, de naturezas
diferentes misturadas.

A pasta é organizada por NATUREZA:

    <slug>/episodio.json     o gestor preenche à mão — fica na raiz de
                             propósito, para não esconder a única tarefa manual
    <slug>/fonte/            entrada: vídeo e transcrição
    <slug>/decisoes/         o que o gestor e o modelo decidiram
    <slug>/briefs/           pacotes de leitura, regeneráveis
    <slug>/publicar/         o que vai ao ar
"""
from __future__ import annotations

import os

FONTE = "fonte"
DECISOES = "decisoes"
BRIEFS = "briefs"
PUBLICAR = "publicar"


def garante(caminho: str) -> str:
    """Cria a pasta do arquivo, se preciso. Devolve o próprio caminho."""
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    return caminho


def episodio(pd: str) -> str:
    return os.path.join(pd, "episodio.json")


def video(pd: str) -> str:
    return os.path.join(pd, FONTE, "video.mp4")


def transcricao(pd: str) -> str:
    return os.path.join(pd, FONTE, "transcricao.json")


def transcricao_txt(pd: str) -> str:
    return os.path.join(pd, FONTE, "transcricao.txt")


def pasta_fonte(pd: str) -> str:
    return os.path.join(pd, FONTE)


def curadoria(pd: str) -> str:
    return os.path.join(pd, DECISOES, "curadoria.json")


def momentos(pd: str) -> str:
    return os.path.join(pd, DECISOES, "momentos.json")


def textos(pd: str) -> str:
    return os.path.join(pd, DECISOES, "textos.json")


def posts(pd: str) -> str:
    return os.path.join(pd, DECISOES, "posts.json")


def calendario(pd: str) -> str:
    """Agenda de publicação: que peça sai em que dia. Decisão editorial."""
    return os.path.join(pd, DECISOES, "calendario.json")


def publicado(pd: str) -> str:
    """Registro do que já foi ao ar — a trava contra post duplicado."""
    return os.path.join(pd, DECISOES, "publicado.json")


def brief(pd: str, tipo: str) -> str:
    """tipo: 'materiais' | 'cortes' | 'posts'."""
    return os.path.join(pd, BRIEFS, f"{tipo}.md")


def thumbnail(pd: str) -> str:
    return os.path.join(pd, PUBLICAR, "thumbnail.jpg")


def card_encerramento(pd: str) -> str:
    """Card de encerramento cacheado — igual em todo corte do episódio.

    Fica na raiz de `publicar/`, como a thumbnail: artefato do episódio, não
    de uma peça, e nunca é commitado (`projetos/` inteiro é git-ignored).
    """
    return os.path.join(pd, PUBLICAR, "_card_encerramento.mp4")


def episodio_txt(pd: str) -> str:
    """Título e descrição do episódio, prontos para colar no YouTube.

    Fica na raiz de `publicar/`, ao lado da thumbnail: os dois são do episódio
    inteiro, não de uma peça — por isso não entram nas pastas de plataforma.
    """
    return os.path.join(pd, PUBLICAR, "episodio.txt")


def plataforma(pd: str, nome: str) -> str:
    """Pasta de saída de uma plataforma de vídeo (youtube_shorts, ...)."""
    return os.path.join(pd, PUBLICAR, nome)


def posts_png(pd: str) -> str:
    return os.path.join(pd, PUBLICAR, "instagram_posts")


# Posição antiga -> nova. O prefixo do nome antigo era necessário quando tudo
# ficava na mesma pasta; dentro da subpasta ele vira redundância.
_MIGRACAO = [
    ("fonte.mp4", video),
    ("transcricao.json", transcricao),
    ("transcricao.txt", transcricao_txt),
    ("curadoria.json", curadoria),
    ("momentos.json", momentos),
    ("textos.json", textos),
    ("posts.json", posts),
    ("brief_materiais.md", lambda pd: brief(pd, "materiais")),
    ("brief_cortes.md", lambda pd: brief(pd, "cortes")),
    ("brief_posts.md", lambda pd: brief(pd, "posts")),
    ("thumbnail.jpg", thumbnail),
]

# Pastas de saída que só mudam de lugar, sem renomear o conteúdo.
# Nome da pasta de cada plataforma. Nomeadas porque não são só diretório: o
# `render` distingue por elas qual caption recebe a chamada do episódio (a
# do YouTube), já que o mp4 das duas é idêntico e só o diretório difere.
YOUTUBE_SHORTS = "youtube_shorts"
INSTAGRAM_REELS = "instagram_reels"
INSTAGRAM_POSTS = "instagram_posts"

_PASTAS_PUBLICAR = (YOUTUBE_SHORTS, INSTAGRAM_REELS, INSTAGRAM_POSTS)

# Temporários que vazaram para a raiz em versões anteriores.
_LIXO = ("_thumb_frame.jpg",)


def _confere_pastas(pd: str) -> None:
    """Recusa migrar se um nome de pasta estiver ocupado por um arquivo.

    Sem isto o `shutil.move` explode no meio com um FileExistsError cru, que
    não diz ao gestor o que ele precisa resolver — e deixa o projeto meio
    migrado.
    """
    for nome in (FONTE, DECISOES, BRIEFS, PUBLICAR):
        caminho = os.path.join(pd, nome)
        if os.path.exists(caminho) and not os.path.isdir(caminho):
            raise RuntimeError(
                f"'{nome}' precisa ser uma pasta, mas é um arquivo em {pd}. "
                f"Renomeie ou remova esse arquivo e rode de novo."
            )


def migrar(pd: str) -> list:
    """Move um projeto da estrutura antiga (tudo solto) para a nova.

    Idempotente: roda no início de todo comando e não faz nada quando o projeto
    já está organizado. Devolve a lista de (origem, destino) do que moveu.

    Quando o arquivo existe nas DUAS posições, a nova vence — é o que os
    comandos vêm escrevendo desde a migração. A antiga NÃO é apagada: vira
    `.bak` e entra no relatório. O gestor pode ter copiado um backup para a
    raiz de propósito, e apagar o trabalho dele em silêncio seria pior que
    deixar um arquivo sobrando.

    Move item a item, sem estado intermediário: interrupção no meio deixa o
    projeto parcialmente migrado, e rodar de novo termina o serviço.
    """
    import shutil

    if not os.path.isdir(pd):
        return []

    _confere_pastas(pd)
    movidos = []

    for antigo, destino_de in _MIGRACAO:
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
        garante(destino)
        shutil.move(origem, destino)
        movidos.append((antigo, os.path.relpath(destino, pd)))

    for nome in _PASTAS_PUBLICAR:
        origem = os.path.join(pd, nome)
        if not os.path.isdir(origem):
            continue
        destino = os.path.join(pd, PUBLICAR, nome)

        if not os.path.isdir(destino):
            os.makedirs(os.path.join(pd, PUBLICAR), exist_ok=True)
            shutil.move(origem, destino)
            movidos.append((nome + "/", os.path.relpath(destino, pd) + "/"))
            continue

        # As duas existem: traz o que só está na antiga e some com ela. Pular
        # deixaria corte já renderizado fora da estrutura documentada, sem
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
                movidos.append((f"{nome}/{arquivo}",
                                os.path.relpath(bak, pd) + " (duplicata)"))
                continue
            shutil.move(atual, alvo)
            movidos.append((f"{nome}/{arquivo}", os.path.relpath(alvo, pd)))
        if not os.listdir(origem):
            os.rmdir(origem)

    for nome in _LIXO:
        caminho = os.path.join(pd, nome)
        if os.path.exists(caminho):
            os.remove(caminho)
            movidos.append((nome, "(removido)"))

    return movidos
