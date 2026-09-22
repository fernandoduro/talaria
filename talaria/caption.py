"""Caption de publicação: o texto que acompanha cada peça na hora de publish.

Um `.txt` ao lado de cada `.mp4`/`.png`, com o mesmo name base — o gestor abre,
copia e cola no campo de legenda do Instagram ou do YouTube.

A descrição vem de quem chama (`post_caption` do clip, `legenda` do post) e as
hashtags do `texts.json`, que valem para o episódio inteiro. Montar isso aqui,
e não em cada chamador, é o mesmo reason do `layout.py` ser a autoridade única
sobre path: `render` e `post_instagram` precisam do formato idêntico, e duas
cópias divergem na primeira mudança.

O único bloco que difere por platform é a chamada para o episódio completo:
ela entra na descrição do Short e não na legenda do Reels (ver `compose`). A
divergência é um parâmetro desta função, não um segundo montador — o resto do
formato tem que continuar idêntico nas duas pontas.
"""
from __future__ import annotations

import os

# Descrição e hashtags são blocos separados por linha em branco: é como o
# Instagram e o YouTube renderizam parágrafo, e deixa a linha de hashtags
# destacada para quem revisa antes de publish.
SEPARATOR = "\n\n"

# O canal não usa travessão em legenda: sai com cara de texto de IA, e mesmo
# assim já escapou até um clip estar no ar — por isso a regra também vive
# aqui, onde toda legenda passa.
EM_DASH = "\u2014"


def validate(field: str, value, piece: str) -> None:
    """Recusa descrição que não seja texto, dizendo qual peça e qual campo.

    Os dois campos de descrição (`post_caption` no clip, `legenda` no post)
    são digitados à mão no JSON. Sem esta checagem, um valor de outro kind só
    aparece lá adiante como `AttributeError: 'int' object has no attribute
    'strip'`, que não diz ao gestor onde ele errou.

    `None` passa: é a chave ausente, caso normal em episódio anterior ao campo.
    """
    if value is not None and not isinstance(value, str):
        raise ValueError(
            f"'{piece}': '{field}' esperava texto, recebeu "
            f"{type(value).__name__} — é o caption que acompanha a "
            f"publicação, uma string só."
        )
    if isinstance(value, str) and EM_DASH in value:
        # AVISA em vez de abortar: o travessão é escolha de escrita, e a
        # correção é reescrever a frase — trocar o caractere por outro no
        # código deixaria a mesma construção de IA, só com outra pontuação.
        # Abortar aqui travaria um render por questão de estilo.
        print(f"[caption] !! {piece}: '{field}' tem travessão — o canal não "
              f"usa em legenda (sai com cara de texto de IA). Reescreva a "
              f"frase antes de publicar.")


# Chamada para o episódio completo, na descrição do Short. A API do YouTube
# não vincula um vídeo a outro (`videos.insert` não tem campo de relação), e
# o vínculo do painel só existe para Short criado a partir do vídeo longo.
# Escrever a URL na descrição é o que resta, e é o que o canal já fazia à mão.
EPISODE_PREFIX = "▶ Episódio completo: "


def episode_line(url: str | None) -> str:
    """A chamada para o episódio completo, ou vazio quando não há URL.

    Episódio sem `youtube_url` no episode.json (o caso de todo episódio
    anterior a este campo) devolve string vazia, que o `compose` descarta como
    qualquer outro bloco ausente.
    """
    url = (url or "").strip()
    return EPISODE_PREFIX + url if url else ""


def compose(description: str | None, hashtags: str | None,
          episode_url: str | None = None) -> str:
    """Junta descrição, chamada do episódio e hashtags num caption pronto.

    Qualquer um dos blocos pode faltar e o resultado continua utilizável: sem
    `texts.json` sai só a descrição; sem `post_caption` saem só as hashtags.
    O que não pode é sobrar linha em branco solta numa das pontas, porque o
    texto vai direto para o campo de publicação.

    `episode_url` é opcional de propósito: só a descrição do YouTube a
    recebe. No Instagram a URL não é clicável e ainda empurra o leitor para
    fora do app, então a legenda do Reels sai sem ela — é o mesmo `.txt` de
    antes.

    `None` chega quando a chave não existe no JSON — trata como vazio em vez de
    estourar, que é o caso comum de clip antigo, anterior a este campo.
    """
    parts = [(description or "").strip(), episode_line(episode_url),
              (hashtags or "").strip()]
    return SEPARATOR.join(p for p in parts if p)


def compose_episode(title: str | None, description: str | None,
                   hashtags: str | None) -> str:
    """Caption do episódio inteiro: título, descrição e hashtags.

    O título entra como primeira linha porque o `.txt` é lido na hora de subir
    o vídeo, e os dois campos são colados em caixas diferentes do YouTube —
    tê-los no mesmo arquivo evita abrir o JSON só para copiar o título.

    A descrição já vem com os próprios blocos e separadores; é inserida como
    está, sem reflow.
    """
    parts = [(p or "").strip() for p in (title, description, hashtags)]
    return SEPARATOR.join(p for p in parts if p)


def txt_path(piece_path: str) -> str:
    """Caminho do `.txt` irmão de uma peça, trocando a extensão.

    Recebe o path da peça já resolvido pelo `layout` em vez de montar um
    novo, para não reintroduzir path por literal fora do `layout.py`.
    """
    stem, _ = os.path.splitext(piece_path)
    return stem + ".txt"


def write(piece_path: str, text: str) -> str:
    """Grava o caption ao lado da peça e devolve o path escrito.

    Sobrescreve o que houver: regerar um clip tem que atualizar o caption, não
    acumular versão antiga ao lado (o mesmo contrato do `.mp4`, que também é
    reescrito no lugar).
    """
    destination = txt_path(piece_path)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    with open(destination, "w", encoding="utf-8") as f:
        f.write(text)
    return destination
