"""Post de citação para Instagram (4:5), escrito sobre o template do design.

O template (assets/template_instagram.png) já traz logo, gradiente, aspas,
filete e barra. Este módulo escreve por cima apenas o que muda por post:
citação, nome e cargo. Não conhece vídeo nem ffmpeg — recebe texto e devolve
PNG.
"""
from __future__ import annotations

import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

from . import caption, config, episodio, layout, render, textos, utils


def _fonte_citacao():
    return ImageFont.truetype(config.POST_FONT, config.POST_CIT_SIZE,
                              index=config.POST_FONT_INDEX)


def quebra(texto: str) -> list:
    """Linhas da citação, medidas na fonte real do post."""
    return render.wrap_by_pixels(texto, fnt=_fonte_citacao(),
                                 largura=config.POST_LARGURA_UTIL)


def valida_card(texto: str) -> dict:
    """O texto cabe num card? Mede na fonte, não conta caracteres.

    Não encolhe a fonte para forçar o encaixe: fonte menor quebra a hierarquia
    visual e denuncia texto espremido. Card que estoura é problema editorial —
    encurtar a frase ou virar mais um card do carrossel.
    """
    texto = (texto or "").strip()
    if not texto:
        return {"cabe": False, "linhas": 0, "motivo": "citação vazia"}

    linhas = quebra(texto)

    # Palavra sozinha maior que a largura útil: a quebra a coloca na linha
    # assim mesmo, porque não há onde quebrar. Passaria na contagem de linhas
    # e sairia cortada na lateral da imagem, sem aviso.
    fnt = _fonte_citacao()
    for linha in linhas:
        largura = fnt.getlength(linha)
        if largura > config.POST_LARGURA_UTIL:
            return {
                "cabe": False,
                "linhas": len(linhas),
                "motivo": (f"'{linha.strip()}' não cabe na largura do card "
                           f"({round(largura)}px de {config.POST_LARGURA_UTIL}) "
                           f"— palavra longa demais, sem onde quebrar"),
            }

    n = len(linhas)
    if n > config.POST_CIT_MAX_LINHAS:
        excesso = n - config.POST_CIT_MAX_LINHAS
        return {
            "cabe": False,
            "linhas": n,
            "motivo": (f"{n} linhas, {excesso} a mais que o limite de "
                       f"{config.POST_CIT_MAX_LINHAS} — encurte a frase ou "
                       f"quebre em outro card"),
        }
    return {"cabe": True, "linhas": n, "motivo": ""}


def _fonte(caminho, tamanho, idx):
    return ImageFont.truetype(caminho, tamanho, index=idx)


def autor_do_episodio(project_dir: str, quem: str = "") -> dict:
    """Nome, cargo e empresa do rodapé, lidos do episodio.json.

    Nome próprio vem daqui, nunca da transcrição — é a mesma regra da legenda
    queimada. Sem convidado externo, a empresa assina a citação.

    `quem` escolhe o convidado quando o episódio tem mais de um (o prompt de
    materiais prevê "dois convidados da mesma empresa"). Sem `quem`, assina o
    primeiro. Nome que não está no episodio.json levanta erro em vez de cair no
    primeiro: publicar a frase de uma pessoa com o nome de outra é o erro mais
    caro desta etapa, e silêncio aqui produziria exatamente isso.
    """
    ep = episodio.load(project_dir)
    convidados = ep.get("convidados") or []
    if not convidados:
        return {"nome": ep.get("empresa", ""), "cargo": "",
                "empresa": ep.get("cidade", "")}

    c = convidados[0]
    if quem:
        alvo = quem.strip().casefold()
        achado = [x for x in convidados
                  if (x.get("nome") or "").strip().casefold() == alvo]
        if not achado:
            nomes = ", ".join(x.get("nome", "") for x in convidados) or "(nenhum)"
            raise ValueError(
                f"'{quem}' não é convidado deste episódio — o episodio.json "
                f"tem: {nomes}"
            )
        c = achado[0]

    return {"nome": c.get("nome", ""), "cargo": c.get("cargo", ""),
            "empresa": ep.get("empresa", "")}


def limpa_citacao(texto: str, nomes: list) -> str:
    """Prepara a fala transcrita para virar citação publicada.

    Mesmo tratamento da legenda queimada — expande contração, remove muleta,
    corrige nome próprio — e pelo mesmo motivo: "tá" na tela parece erro de
    digitação. Numa citação atribuída a uma pessoa identificada isso pesa mais,
    então o limite também é mais rígido: NUNCA reescrever a frase. Citação que
    precisa ser reescrita para funcionar não é a citação certa.
    """
    return utils.corrige_nomes(utils.clean_caption(texto), nomes)


def compoe_card(texto: str, autor: dict, out_path: str, template: str = None):
    """Escreve citação e autor sobre o template e salva o PNG.

    `autor` traz nome, cargo e empresa — vindos do episodio.json, nunca da
    transcrição (a transcrição erra nome próprio).

    Levanta ValueError se o texto não couber: a decisão de encurtar ou quebrar
    em outro card é editorial e não pode ser tomada aqui.
    """
    template = template or config.POST_TEMPLATE
    if not os.path.exists(template):
        raise FileNotFoundError(
            f"template do post não encontrado em {template} — "
            f"o arquivo deveria estar versionado em assets/"
        )

    v = valida_card(texto)
    if not v["cabe"]:
        raise ValueError(f"citação não cabe no card: {v['motivo']}")

    img = Image.open(template).convert("RGB")
    d = ImageDraw.Draw(img)

    # Citação — ancorada pelo TOPO, não centralizada: cards de 2 e de 5 linhas
    # partem da mesma altura, então o texto não pula a cada deslize do
    # carrossel.
    fcit = _fonte_citacao()
    for i, linha in enumerate(quebra(texto)):
        y = config.POST_CIT_Y + i * config.POST_CIT_PASSO
        d.text((config.POST_MARGEM_X, y), linha, font=fcit,
               fill=config.POST_COR_CITACAO)

    # Rodapé (o filete laranja já vem desenhado no template)
    fnome = _fonte(config.POST_FONT, config.POST_NOME_SIZE, config.POST_FONT_INDEX)
    d.text((config.POST_MARGEM_X, config.POST_NOME_Y), autor["nome"],
           font=fnome, fill=config.POST_COR_NOME)

    fcargo = _fonte(config.POST_MONO, config.POST_CARGO_SIZE, config.POST_MONO_INDEX)
    rodape = " · ".join(p for p in (autor.get("cargo"), autor.get("empresa")) if p)
    d.text((config.POST_MARGEM_X, config.POST_CARGO_Y), rodape,
           font=fcargo, fill=config.POST_COR_CARGO)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, quality=95)
    return out_path


def slug_de_arquivo(slug: str) -> str:
    """Slug seguro para virar nome de arquivo, preservando a legibilidade.

    O slug é digitado à mão no `posts.json` e vira nome de arquivo. Sem isto um
    `../` cria diretório lixo dentro da pasta de saída e, com barras demais,
    quebra num FileNotFoundError do Pillow em vez de gerar o post — erro que
    não diz ao gestor o que ele digitou de errado.

    É público porque o `publish` também sanea por aqui, e pelo mesmo motivo:
    slug que escapa da pasta faz o publish achar um arquivo de fora do
    projeto e publicá-lo. Os dois precisam da MESMA regra — duas cópias
    divergem na primeira mudança e a divergência só aparece publicada.
    """
    limpo = re.sub(r"[^\w.-]", "_", (slug or "").strip(), flags=re.UNICODE)
    limpo = limpo.strip("._-")
    return limpo or "post"


def carrega(project_dir: str) -> list:
    """Lê o posts.json do projeto."""
    path = layout.posts(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py post --projeto <slug> "
            f"--cortes <n,n>' e escolha as citações em sessão antes de gerar."
        )
    with open(path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("posts") or []


def gerar(project_dir: str) -> list:
    """Renderiza todos os posts do posts.json. Devolve os caminhos gerados.

    Valida TODOS os cards antes de escrever qualquer arquivo: material pela
    metade numa pasta de publicação é pior que erro na hora — o gestor pode
    publicar o card 1 de um carrossel que nunca teve card 2.
    """
    posts = carrega(project_dir)
    if not posts:
        raise ValueError(f"{layout.posts(project_dir)} não tem nenhum post")

    ep = episodio.load(project_dir)
    nomes = [ep.get("empresa", "")] + [c.get("nome", "")
                                       for c in (ep.get("convidados") or [])]
    # 1ª passada: limpa e valida tudo.
    planejado = []
    for p in posts:
        slug = p.get("slug") or "post"
        cards = p.get("cards") or []
        if not cards:
            raise ValueError(f"post '{slug}' não tem nenhum card")

        # Quem assina: o `quem` do post (episódio com dois convidados) ou, por
        # omissão, o primeiro. Resolvido aqui na 1ª passada para que um nome
        # errado aborte antes de escrever qualquer arquivo.
        autor = autor_do_episodio(project_dir, quem=p.get("quem", ""))

        # A legenda é validada AQUI, não na hora de gravar o .txt: o contrato
        # desta função é abortar antes de escrever qualquer arquivo, e um tipo
        # errado descoberto depois já teria deixado os PNGs na pasta.
        caption.valida("legenda", p.get("legenda"), f"post {slug}")
        for i, bruto in enumerate(cards, start=1):
            if not isinstance(bruto, str):
                raise ValueError(
                    f"post '{slug}' card {i}: esperava texto, recebeu "
                    f"{type(bruto).__name__} — cada item de 'cards' é a "
                    f"citação daquele card"
                )
            texto = limpa_citacao(bruto, nomes)
            v = valida_card(texto)
            if not v["cabe"]:
                onde = f"{slug} card {i}" if len(cards) > 1 else slug
                raise ValueError(f"'{onde}': {v['motivo']}")
            arq = slug_de_arquivo(slug)
            nome = (f"post_{arq}.png" if len(cards) == 1
                    else f"post_{arq}_{i}.png")
            planejado.append((nome, texto, autor))

    # 2ª passada: escreve.
    saida = layout.posts_png(project_dir)
    os.makedirs(saida, exist_ok=True)
    gerados = []
    for nome, texto, quem_assina in planejado:
        gerados.append(compoe_card(texto, quem_assina,
                                   os.path.join(saida, nome)))
        print(f"[post] {nome}")

    # Um caption por POST, não por card: um carrossel é uma publicação só, com
    # uma legenda só. Por isso a lista vem de `posts` e não de `planejado`.
    escreve_captions(saida,
                     [(p.get("slug") or "post", p.get("legenda", "")) for p in posts],
                     (textos.load(project_dir) or {}).get("hashtags", ""))
    return gerados


def escreve_captions(saida: str, legendas: list, hashtags: str) -> list:
    """Grava o `.txt` de publicação de cada post na pasta de saída.

    `legendas` é [(slug, legenda)] — um item por POST. O nome do arquivo usa o
    slug do post (`post_<slug>.txt`), então um carrossel de N cards continua
    com um único caption, ao lado dos seus `post_<slug>_1.png`, `_2.png`...

    O slug passa pelo mesmo saneamento do PNG: sem isso um `../` no JSON
    escreveria o `.txt` fora da pasta de publicação.
    """
    escritos = []
    for slug, legenda in legendas:
        caption.valida("legenda", legenda, f"post {slug}")
        if not (legenda or "").strip():
            print(f"[caption] !! {slug}: sem legenda — o .txt sai só com as "
                  f"hashtags. Preencha em decisoes/posts.json.")
        base = os.path.join(saida, f"post_{slug_de_arquivo(slug)}.png")
        escritos.append(caption.escreve(base, caption.monta(legenda, hashtags)))
    return escritos
