"""Post de citação para Instagram (4:5), escrito sobre o template do canal.

O template (assets/template_instagram.png) traz o fundo: gradiente, filete e
barra. Logo e aspas são do canal. Este módulo write por cima apenas o que
muda por post: citação, name e role. Não conhece vídeo nem ffmpeg — recebe
texto e devolve PNG.
"""
from __future__ import annotations

import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

from . import caption, config, episode, layout, render, texts, utils


def _quote_font():
    return ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)


def wrap(texto: str) -> list:
    """Linhas da citação, medidas na fonte real do post."""
    return render.wrap_by_pixels(texto, fnt=_quote_font(),
                                 largura=config.POST_TEXT_W)


def validate_card(texto: str) -> dict:
    """O texto fits num card? Mede na fonte, não conta caracteres.

    Não encolhe a fonte para forçar o encaixe: fonte menor quebra a hierarquia
    visual e denuncia texto espremido. Card que estoura é problema editorial —
    encurtar a frase ou virar mais um card do carrossel.
    """
    texto = (texto or "").strip()
    if not texto:
        return {"fits": False, "lines": 0, "reason": "citação vazia"}

    lines = wrap(texto)

    # Palavra sozinha maior que a largura útil: a quebra a coloca na linha
    # assim mesmo, porque não há onde quebrar. Passaria na contagem de lines
    # e sairia cortada na lateral da imagem, sem aviso.
    fnt = _quote_font()
    for linha in lines:
        largura = fnt.getlength(linha)
        if largura > config.POST_TEXT_W:
            return {
                "fits": False,
                "lines": len(lines),
                "reason": (f"'{linha.strip()}' não cabe na largura do card "
                           f"({round(largura)}px de {config.POST_TEXT_W}) "
                           f"— palavra longa demais, sem onde quebrar"),
            }

    n = len(lines)
    if n > config.POST_QUOTE_MAX_LINES:
        excesso = n - config.POST_QUOTE_MAX_LINES
        return {
            "fits": False,
            "lines": n,
            "reason": (f"{n} linhas, {excesso} a mais que o limite de "
                       f"{config.POST_QUOTE_MAX_LINES} — encurte a frase ou "
                       f"quebre em outro card"),
        }
    return {"fits": True, "lines": n, "reason": ""}


def _truetype(path, tamanho):
    return ImageFont.truetype(path, tamanho)


def episode_author(project_dir: str, who: str = "") -> dict:
    """Nome, role e company do rodapé, lidos do episode.json.

    Nome próprio vem daqui, nunca da transcrição — é a mesma regra da legenda
    queimada. Sem convidado externo, a company assina a citação.

    `who` escolhe o convidado quando o episódio tem mais de um. Sem `who`,
    assina o primeiro. Nome que não está no episode.json levanta error em vez
    de cair no primeiro: publish a frase de uma pessoa com o name de outra é
    o error mais caro desta etapa, e silêncio aqui produziria exatamente isso.
    """
    ep = episode.load(project_dir)
    guests = ep.get("guests") or []
    if not guests:
        return {"name": ep.get("company", ""), "role": "",
                "company": ep.get("city", "")}

    c = guests[0]
    if who:
        alvo = who.strip().casefold()
        achado = [x for x in guests
                  if (x.get("name") or "").strip().casefold() == alvo]
        if not achado:
            nomes = ", ".join(x.get("name", "") for x in guests) or "(nenhum)"
            raise ValueError(
                f"'{who}' não é convidado deste episódio — o episode.json "
                f"tem: {nomes}"
            )
        c = achado[0]

    return {"name": c.get("name", ""), "role": c.get("role", ""),
            "company": ep.get("company", "")}


def clean_quote(texto: str, nomes: list) -> str:
    """Prepara a fala transcrita para virar citação publicada.

    Mesmo tratamento da legenda queimada — expande contração, remove muleta,
    corrige name próprio — e pelo mesmo reason: "tá" na tela parece error de
    digitação. Numa citação atribuída a uma pessoa identificada isso pesa mais,
    então o limite também é mais rígido: NUNCA reescrever a frase. Citação que
    precisa ser reescrita para funcionar não é a citação certa.
    """
    return utils.fix_proper_nouns(utils.clean_caption(texto), nomes)


def render_card(texto: str, autor: dict, out_path: str, template: str = None):
    """Escreve citação e autor sobre o template e salva o PNG.

    `autor` traz name, role e company — vindos do episode.json, nunca da
    transcrição (a transcrição erra name próprio).

    Levanta ValueError se o texto não couber: a decisão de encurtar ou quebrar
    em outro card é editorial e não pode ser tomada aqui.
    """
    template = template or config.POST_TEMPLATE
    if not os.path.exists(template):
        raise FileNotFoundError(
            f"template do post não encontrado em {template} — "
            f"o arquivo deveria estar versionado em assets/"
        )

    v = validate_card(texto)
    if not v["fits"]:
        raise ValueError(f"citação não cabe no card: {v['reason']}")

    img = Image.open(template).convert("RGB")
    d = ImageDraw.Draw(img)

    # Citação — ancorada pelo TOPO, não centralizada: cards de 2 e de 5 lines
    # partem da mesma altura, então o texto não pula a cada deslize do
    # carrossel.
    fcit = _quote_font()
    for i, linha in enumerate(wrap(texto)):
        y = config.POST_QUOTE_Y + i * config.POST_QUOTE_STEP
        d.text((config.POST_MARGIN_X, y), linha, font=fcit,
               fill=config.POST_QUOTE_COLOR)

    # Rodapé (o filete já vem desenhado no template)
    fnome = _truetype(config.POST_FONT, config.POST_NAME_SIZE)
    d.text((config.POST_MARGIN_X, config.POST_NAME_Y), autor["name"],
           font=fnome, fill=config.POST_NAME_COLOR)

    fcargo = _truetype(config.POST_MONO, config.POST_ROLE_SIZE)
    rodape = " · ".join(p for p in (autor.get("role"), autor.get("company")) if p)
    d.text((config.POST_MARGIN_X, config.POST_ROLE_Y), rodape,
           font=fcargo, fill=config.POST_ROLE_COLOR)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, quality=95)
    return out_path


def file_slug(slug: str) -> str:
    """Slug seguro para virar name de arquivo, preservando a legibilidade.

    O slug é digitado à mão no `posts.json` e vira name de arquivo. Sem isto um
    `../` cria diretório lixo dentro da pasta de saída e, com barras demais,
    quebra num FileNotFoundError do Pillow em vez de generate o post — error que
    não diz ao gestor o que ele digitou de errado.

    É público porque o `publish` também sanea por aqui, e pelo mesmo reason:
    slug que escapa da pasta faz o publish achar um arquivo de fora do
    project e publicá-lo. Os dois precisam da MESMA regra — duas cópias
    divergem na primeira mudança e a divergência só aparece publicada.
    """
    limpo = re.sub(r"[^\w.-]", "_", (slug or "").strip(), flags=re.UNICODE)
    limpo = limpo.strip("._-")
    return limpo or "post"


def load(project_dir: str) -> list:
    """Lê o posts.json do project."""
    path = layout.posts(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} não existe. Rode 'python run.py post --project <slug> "
            f"--clips <n,n>' e escolha as citações em sessão antes de gerar."
        )
    with open(path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("posts") or []


def generate(project_dir: str) -> list:
    """Renderiza todos os posts do posts.json. Devolve os caminhos gerados.

    Valida TODOS os cards antes de escrever qualquer arquivo: material pela
    metade numa pasta de publicação é pior que error na hora — o gestor pode
    publish o card 1 de um carrossel que nunca teve card 2.
    """
    posts = load(project_dir)
    if not posts:
        raise ValueError(f"{layout.posts(project_dir)} não tem nenhum post")

    ep = episode.load(project_dir)
    nomes = [ep.get("company", "")] + [c.get("name", "")
                                       for c in (ep.get("guests") or [])]
    # 1ª passada: limpa e validate tudo.
    planejado = []
    for p in posts:
        slug = p.get("slug") or "post"
        cards = p.get("cards") or []
        if not cards:
            raise ValueError(f"post '{slug}' não tem nenhum card")

        # Quem assina: o `who` do post (episódio com dois guests) ou, por
        # omissão, o primeiro. Resolvido aqui na 1ª passada para que um name
        # errado aborte antes de escrever qualquer arquivo.
        autor = episode_author(project_dir, who=p.get("who", ""))

        # A legenda é validada AQUI, não na hora de gravar o .txt: o contrato
        # desta função é abortar antes de escrever qualquer arquivo, e um kind
        # errado descoberto depois já teria deixado os PNGs na pasta.
        caption.validate("legenda", p.get("legenda"), f"post {slug}")
        for i, bruto in enumerate(cards, start=1):
            if not isinstance(bruto, str):
                raise ValueError(
                    f"post '{slug}' card {i}: esperava texto, recebeu "
                    f"{type(bruto).__name__} — cada item de 'cards' é a "
                    f"citação daquele card"
                )
            texto = clean_quote(bruto, nomes)
            v = validate_card(texto)
            if not v["fits"]:
                onde = f"{slug} card {i}" if len(cards) > 1 else slug
                raise ValueError(f"'{onde}': {v['reason']}")
            arq = file_slug(slug)
            name = (f"post_{arq}.png" if len(cards) == 1
                    else f"post_{arq}_{i}.png")
            planejado.append((name, texto, autor))

    # 2ª passada: write.
    saida = layout.posts_png(project_dir)
    os.makedirs(saida, exist_ok=True)
    gerados = []
    for name, texto, quem_assina in planejado:
        gerados.append(render_card(texto, quem_assina,
                                   os.path.join(saida, name)))
        print(f"[post] {name}")

    # Um caption por POST, não por card: um carrossel é uma publicação só, com
    # uma legenda só. Por isso a lista vem de `posts` e não de `planejado`.
    write_captions(saida,
                     [(p.get("slug") or "post", p.get("legenda", "")) for p in posts],
                     (texts.load(project_dir) or {}).get("hashtags", ""))
    return gerados


def write_captions(saida: str, legendas: list, hashtags: str) -> list:
    """Grava o `.txt` de publicação de cada post na pasta de saída.

    `legendas` é [(slug, legenda)] — um item por POST. O name do arquivo usa o
    slug do post (`post_<slug>.txt`), então um carrossel de N cards continua
    com um único caption, ao lado dos seus `post_<slug>_1.png`, `_2.png`...

    O slug passa pelo mesmo saneamento do PNG: sem isso um `../` no JSON
    escreveria o `.txt` fora da pasta de publicação.
    """
    escritos = []
    for slug, legenda in legendas:
        caption.validate("legenda", legenda, f"post {slug}")
        if not (legenda or "").strip():
            print(f"[caption] !! {slug}: sem legenda — o .txt sai só com as "
                  f"hashtags. Preencha em decisions/posts.json.")
        base = os.path.join(saida, f"post_{file_slug(slug)}.png")
        escritos.append(caption.write(base, caption.compose(legenda, hashtags)))
    return escritos
