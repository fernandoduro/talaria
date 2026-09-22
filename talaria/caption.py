"""Caption de publicação: o texto que acompanha cada peça na hora de publish.

Um `.txt` ao lado de cada `.mp4`/`.png`, com o mesmo name base — o gestor abre,
copia e cola no campo de legenda do Instagram ou do YouTube.

A descrição vem de who chama (`post_caption` do clip, `legenda` do post) e as
hashtags do `texts.json`, que valem para o episódio inteiro. Montar isso aqui,
e não em cada chamador, é o mesmo reason do `layout.py` ser a autoridade única
sobre caminho: `render` e `post_instagram` precisam do formato idêntico, e duas
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
# destacada para who revisa antes de publish.
SEPARATOR = "\n\n"

# O canal não usa travessão em legenda: sai com cara de texto de IA, e mesmo
# assim já escapou até um clip estar no ar — por isso a regra também vive
# aqui, onde toda legenda passa.
EM_DASH = "\u2014"


def validate(campo: str, valor, peca: str) -> None:
    """Recusa descrição que não seja texto, dizendo qual peça e qual campo.

    Os dois campos de descrição (`post_caption` no clip, `legenda` no post)
    são digitados à mão no JSON. Sem esta checagem, um valor de outro kind só
    aparece lá adiante como `AttributeError: 'int' object has no attribute
    'strip'`, que não diz ao gestor onde ele errou.

    `None` passa: é a chave ausente, caso normal em episódio anterior ao campo.
    """
    if valor is not None and not isinstance(valor, str):
        raise ValueError(
            f"'{peca}': '{campo}' esperava texto, recebeu "
            f"{type(valor).__name__} — é o caption que acompanha a "
            f"publicação, uma string só."
        )
    if isinstance(valor, str) and EM_DASH in valor:
        # AVISA em vez de abortar: o travessão é escolha de escrita, e a
        # correção é reescrever a frase — trocar o caractere por outro no
        # código deixaria a mesma construção de IA, só com outra pontuação.
        # Abortar aqui travaria um render por questão de estilo.
        print(f"[caption] !! {peca}: '{campo}' tem travessão — o canal não "
              f"usa em legenda (sai com cara de texto de IA). Reescreva a "
              f"frase antes de publish.")


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
          url_episodio: str | None = None) -> str:
    """Junta descrição, chamada do episódio e hashtags num caption pronto.

    Qualquer um dos blocos pode faltar e o resultado continua utilizável: sem
    `texts.json` sai só a descrição; sem `post_caption` saem só as hashtags.
    O que não pode é sobrar linha em branco solta numa das pontas, porque o
    texto vai direto para o campo de publicação.

    `url_episodio` é opcional de propósito: só a descrição do YouTube a
    recebe. No Instagram a URL não é clicável e ainda empurra o leitor para
    fora do app, então a legenda do Reels sai sem ela — é o mesmo `.txt` de
    antes.

    `None` chega quando a chave não existe no JSON — trata como vazio em vez de
    estourar, que é o caso comum de clip antigo, anterior a este campo.
    """
    partes = [(description or "").strip(), episode_line(url_episodio),
              (hashtags or "").strip()]
    return SEPARATOR.join(p for p in partes if p)


def compose_episode(title: str | None, description: str | None,
                   hashtags: str | None) -> str:
    """Caption do episódio inteiro: título, descrição e hashtags.

    O título entra como primeira linha porque o `.txt` é lido na hora de subir
    o vídeo, e os dois campos são colados em caixas diferentes do YouTube —
    tê-los no mesmo arquivo evita abrir o JSON só para copiar o título.

    A descrição já vem com os próprios blocos e separadores; é inserida como
    está, sem reflow.
    """
    partes = [(p or "").strip() for p in (title, description, hashtags)]
    return SEPARATOR.join(p for p in partes if p)


def caminho(caminho_peca: str) -> str:
    """Caminho do `.txt` irmão de uma peça, trocando a extensão.

    Recebe o caminho da peça já resolvido pelo `layout` em vez de montar um
    novo, para não reintroduzir caminho por literal fora do `layout.py`.
    """
    raiz, _ = os.path.splitext(caminho_peca)
    return raiz + ".txt"


def write(caminho_peca: str, texto: str) -> str:
    """Grava o caption ao lado da peça e devolve o caminho escrito.

    Sobrescreve o que houver: regerar um clip tem que atualizar o caption, não
    acumular versão antiga ao lado (o mesmo contrato do `.mp4`, que também é
    reescrito no lugar).
    """
    destino = caminho(caminho_peca)
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)
    return destino
