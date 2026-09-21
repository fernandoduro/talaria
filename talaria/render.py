"""Renderiza cortes verticais 9:16 (fundo blur) com legenda queimada.

O backend de legenda (drawtext ou overlay de PNGs) é escolhido em runtime por
config.CAPTION_BACKEND — ver talaria/caption_png.py.

Lê transcricao.json (segmentos) + momentos.json (cortes curados) e, por corte,
gera o MP4 vertical com legenda para as plataformas escolhidas.

momentos.json: lista de {slug, start, end, ...}. Campos extras (quem, titulo,
frase_efeito) são ignorados aqui — servem para os textos.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from PIL import ImageFont

from . import (audio, caption, caption_png, config, encerramento, episodio,
               layout, textos, utils)

_PILFONT = ImageFont.truetype(config.FONT, config.FONTSIZE)


def _text_width_px(s: str, fnt=None) -> float:
    return (fnt or _PILFONT).getlength(s)


def wrap_by_pixels(txt: str, fnt=None, largura: float | None = None) -> list[str]:
    """Quebra o texto por LARGURA REAL EM PIXELS (não por nº de caracteres).

    Garante que nenhuma linha ultrapasse a largura. Usa quantas linhas precisar
    — melhor 3 linhas curtas que texto cortado nas laterais.

    Sem argumentos, quebra a legenda queimada do vídeo (fonte e SAFE_W do
    config). Com `fnt`/`largura`, serve também o post de citação, que tem fonte
    e área diferentes.
    """
    largura = config.SAFE_W if largura is None else largura
    words = txt.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip() if cur else w
        if _text_width_px(cand, fnt) <= largura:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _esc_drawtext(s: str) -> str:
    """Escapa o texto para o valor de text= dentro de -filter_complex."""
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:").replace("'", "’")
    s = s.replace("%", "\\%").replace(",", "\\,")
    return s


def _drawtext_chain(segments, start, end, nomes=None) -> str:
    """Constrói a cadeia de filtros drawtext para as legendas de um corte."""
    parts = []
    # Mesma fonte de verdade do backend overlay: sem isto o drawtext perdia o
    # aparo de texto e mostrava fala que o corte não reproduz.
    for rs, re_, txt in _segments_in_cut(segments, start, end, nomes):
        lines = wrap_by_pixels(txt)
        n = len(lines)
        for li, line in enumerate(lines):
            y = config.BASE_Y - (n - 1 - li) * config.LINE_H
            t = _esc_drawtext(line)
            parts.append(
                f"drawtext=fontfile='{config.FONT}':text='{t}':"
                f"fontsize={config.FONTSIZE}:fontcolor=white:"
                f"borderw={config.CAP_BORDER}:bordercolor=black:"
                f"box=1:boxcolor=black@{config.CAP_BOX_ALPHA}:"
                f"boxborderw={config.CAP_BOX_BORDER}:"
                f"x=(w-text_w)/2:y={y}:"
                f"enable='between(t,{rs:.3f},{re_:.3f})'"
            )
    return ",".join(parts) if parts else "null"


def _filtergraph(segments, start, end, nomes=None) -> str:
    """9:16 com fundo blur + legendas via drawtext."""
    draw = _drawtext_chain(segments, start, end, nomes)
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={config.FRAME_W}:{config.FRAME_H}:force_original_aspect_ratio=increase,"
        f"crop={config.FRAME_W}:{config.FRAME_H},gblur=sigma={config.BG_BLUR_SIGMA}[bgb];"
        f"[fg]scale={config.FG_SCALE_W}:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{draw}[outv]"
    )


def _marca_dagua_graph(in_label: str, logo_label: str) -> str:
    """Overlay do logo no canto superior direito, encadeado após a legenda.

    Os dois backends de legenda (`drawtext` e `overlay`) já convergem no label
    `[outv]` — a marca d'água entra depois disso, produzindo `[outv2]`, sem
    tocar em `_filtergraph` nem em `caption_png.build_overlay_graph`.
    """
    return (
        f"[{logo_label}]scale={config.MARCA_DAGUA_LARGURA}:-1[wm];"
        f"[{in_label}][wm]overlay=W-w-{config.MARCA_DAGUA_MARGEM}:"
        f"{config.MARCA_DAGUA_MARGEM}[outv2]"
    )


BASE_GRAPH = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
    "crop={W}:{H},gblur=sigma={S}[bgb];"
    "[fg]scale={FW}:-2[fgs];"
    "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[comp]"
)


def _base_graph() -> str:
    return BASE_GRAPH.format(W=config.FRAME_W, H=config.FRAME_H,
                             S=config.BG_BLUR_SIGMA, FW=config.FG_SCALE_W)


def _segments_in_cut(segments, start, end, nomes=None):
    """Segmentos que aparecem no corte, com tempos relativos ao início dele.

    Quando o corte apara um segmento (começa ou termina no meio dele), o TEXTO
    é aparado na mesma proporção. Sem isso a legenda mostra fala que o áudio do
    corte não alcança: o último segmento ficava 1.4s na tela exibindo os
    150 caracteres do bloco inteiro, enquanto o áudio só dizia as 4 primeiras
    palavras.
    """
    out = []
    for seg in segments:
        s, e = seg["start"], seg["end"]
        if e <= start or s >= end:
            continue
        txt = utils.corrige_nomes(utils.clean_caption(seg["text"]), nomes)
        if not txt:
            continue
        vis_s, vis_e = max(s, start), min(e, end)
        if (vis_e - vis_s) < LEGENDA_MIN_S:
            continue          # rápido demais para ler: só pisca na tela
        txt = _apara_texto(txt, (vis_s - s) / (e - s), (vis_e - s) / (e - s))
        if not txt:
            continue
        out.append((vis_s - start, vis_e - start, txt))
    return out


# Tempo mínimo de tela para uma legenda valer a pena. O fim do corte vem do
# vale de áudio, não da grade da transcrição, então sobram milissegundos do
# bloco seguinte — sem este piso viravam PNG de 1 frame ("Poucas" piscando no
# fim do corte, a palavra que o ajuste de áudio tinha tirado).
LEGENDA_MIN_S = 0.30


# Folga mínima tirada do fim do corte, para absorver arredondamento quando o
# ajuste por áudio não roda (sem ffmpeg, ou fim já no vale).
MARGEM_FIM_S = 0.02

# Quanto o ajuste por áudio pode recuar. Além disso o corte perderia conteúdo
# em vez de ganhar limpeza, e o problema passa a ser o fim escolhido.
AJUSTE_AUDIO_MAX_S = 0.5


def aplica_margem_fim(end: float, start: float) -> float:
    """Recua o fim do corte pela margem, respeitando a duração mínima.

    Um corte já no limite dos 60s não pode encolher: a margem existe para
    absorver arredondamento, não para violar a regra de duração.
    """
    piso = start + min(config.CORTE_MIN_S, end - start)
    return max(piso, end - MARGEM_FIM_S)


def ajusta_fim_por_audio(video_path, start, end):
    """Move o fim do corte para a pausa de fala mais próxima.

    Os tempos vêm da transcrição, que tem resolução de 1 segundo — o fim cai em
    cima da fronteira entre duas palavras e vaza o ataque da seguinte
    ("Poucas"). Esta é a correção que antes se fazia medindo o envelope à mão.

    Recua no máximo AJUSTE_AUDIO_MAX_S e nunca abaixo da duração mínima; sem
    ffmpeg, cai na margem fixa.
    """
    vale = audio.vale_antes(video_path, end, busca=AJUSTE_AUDIO_MAX_S)
    if vale >= end or (end - vale) > AJUSTE_AUDIO_MAX_S:
        return aplica_margem_fim(end, start)
    if (vale - start) < config.CORTE_MIN_S:
        return aplica_margem_fim(end, start)
    return vale


def _apara_texto(txt: str, ini: float, fim: float) -> str:
    """Recorta `txt` na fatia proporcional [ini, fim] (0..1), por palavra.

    A transcrição não traz tempo por palavra, então a posição é estimada
    proporcionalmente ao texto — aproximação suficiente para não exibir frase
    que o corte não reproduz. O recorte é feito em fronteira de palavra: cortar
    por caractere deixaria "reprodu" na tela.
    """
    if ini <= 0 and fim >= 1:
        return txt
    palavras = txt.split()
    if not palavras:
        return txt
    n = len(palavras)
    a = max(0, min(n, int(round(ini * n))))
    b = max(a, min(n, int(round(fim * n))))
    if b - a < 1:                     # fatia curta demais: mantém 1 palavra
        b = min(n, a + 1)
    # A estimativa proporcional erra por uma ou duas palavras. Nas duas direções
    # o alvo é o mesmo: fechar a legenda na pontuação mais próxima do corte, em
    # vez de deixá-la pendurada no meio da frase.
    if b < n:
        b = _ajusta_ate_pontuacao(palavras, b)
    return " ".join(palavras[a:b])


# Quantas palavras o ajuste pode andar para achar a pontuação. Dois em cada
# direção cobre o erro típico da estimativa proporcional sem deixar a legenda
# invadir a frase seguinte.
JANELA_PONTUACAO = 2


def _ajusta_ate_pontuacao(palavras: list, b: int) -> int:
    """Move o fim da fatia para a pontuação mais próxima, dentro da janela.

    Recuar evita arrastar o começo da frase seguinte ("...reproduzir. Acho
    que"); avançar evita cortar antes do ponto que o áudio já completou
    ("muito mais do" quando a fala diz "muito mais do mesmo.").
    """
    fim_de_frase = (".", "!", "?", "…")
    for d in range(0, JANELA_PONTUACAO + 1):
        atras = b - 1 - d
        if atras >= 0 and palavras[atras].endswith(fim_de_frase):
            return atras + 1
        frente = b - 1 + d
        if frente < len(palavras) and palavras[frente].endswith(fim_de_frase):
            return frente + 1
    return b


def _build_overlay_inputs(segments, start, end, tmpdir, nomes=None):
    """Rasteriza um PNG por segmento. Retorna [(png, rel_start, rel_end)]."""
    items = []
    for i, (rs, re_, txt) in enumerate(_segments_in_cut(segments, start, end, nomes)):
        png = os.path.join(tmpdir, f"cap_{i:05d}.png")
        caption_png.render_caption_png(wrap_by_pixels(txt), png)
        items.append((png, rs, re_))
    return items


def concatena_encerramento(corte_path: str, project_dir: str) -> None:
    """Acrescenta o card de encerramento ao fim de `corte_path`, no lugar.

    Usa o CONCAT FILTER, não o concat demuxer com `-c copy`. Testado na
    prática: `-c copy` produzia um arquivo quase do tamanho do corte sozinho,
    porque os dois clipes vêm de encodes independentes (o corte do
    filtergraph principal, o card do Pillow) com timestamps que não se
    encadeiam — o ffmpeg avisa "Non-monotonic DTS" e o card acaba descartado
    ou truncado, SEM erro de retorno. O concat filter reencoda esta etapa
    (curta — só a junção, não o corte inteiro) e recalcula os timestamps do
    zero com `setpts`/`asetpts`, o que corrige o problema.
    """
    card_path = encerramento.card_cacheado(project_dir)

    tmpdir = tempfile.mkdtemp(prefix="talaria_concat_")
    try:
        saida = os.path.join(tmpdir, "concatenado.mp4")
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", corte_path, "-i", card_path,
            "-filter_complex",
            # setsar=1 normaliza o aspect ratio de pixel: o card (gerado do
            # PNG estático) e o corte (do filtergraph principal) podem sair
            # com SAR diferente mesmo tendo a mesma resolução em pixels, e o
            # concat filter — ao contrário do demuxer — rejeita entradas com
            # parâmetros de vídeo que não batem exatamente.
            "[0:v]setpts=PTS-STARTPTS,setsar=1[v0];[0:a]asetpts=PTS-STARTPTS[a0];"
            "[1:v]setpts=PTS-STARTPTS,setsar=1[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            saida,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao concatenar o encerramento:\n"
                               f"{r.stderr[-1500:]}")
        shutil.move(saida, corte_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def render_cut(video_path, segments, moment, project_dir, platforms, nomes=None):
    """Renderiza um corte para as plataformas escolhidas (youtube/instagram)."""
    slug = moment["slug"]
    start, end = float(moment["start"]), float(moment["end"])
    end = ajusta_fim_por_audio(video_path, start, end)

    outputs = []
    if "youtube" in platforms:
        outputs.append(("youtube_shorts", f"{slug}_short.mp4"))
    if "instagram" in platforms:
        outputs.append(("instagram_reels", f"{slug}_reel.mp4"))

    if not outputs:
        raise ValueError("Nenhuma plataforma selecionada (use youtube e/ou instagram).")

    # Renderiza uma vez; se as duas plataformas foram pedidas, copia (pixel-idêntico).
    first_subdir, first_name = outputs[0]
    first_dir = layout.plataforma(project_dir, first_subdir)
    os.makedirs(first_dir, exist_ok=True)
    first_out = os.path.join(first_dir, first_name)

    print(f"[render] {slug} ({end - start:.0f}s) -> {first_subdir}/{first_name} "
          f"[legenda: {config.CAPTION_BACKEND}]")

    tmpdir = None
    try:
        if config.CAPTION_BACKEND == "drawtext":
            seek_inputs = ["-i", video_path]
            fg = _filtergraph(segments, start, end, nomes)
        else:
            # Rasteriza as legendas em PNG e sobrepõe com overlay+enable.
            tmpdir = tempfile.mkdtemp(prefix=f"talaria_{slug}_")
            items = _build_overlay_inputs(segments, start, end, tmpdir, nomes)
            seek_inputs = ["-i", video_path]
            for png, _rs, _re in items:
                seek_inputs += ["-i", png]
            fg = _base_graph() + ";" + caption_png.build_overlay_graph(items)

        # A marca d'água entra como o ÚLTIMO input, com `-loop 1` — sem loop,
        # uma imagem estática vira um único frame em t=0, e herdar o mesmo
        # `-ss`/`-to` do vídeo produziria stream vazio (testado empiricamente:
        # ffmpeg recorta ANTES desse frame e não sobra nada). Com `-loop 1` o
        # stream é contínuo e o -ss/-to do bloco anterior não o afeta.
        logo_idx = len(seek_inputs) // 2   # cada item de seek_inputs é "-i, caminho"
        fg += ";" + _marca_dagua_graph("outv", str(logo_idx))

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-to", str(end), *seek_inputs,
            "-loop", "1", "-i", config.LOGO_PATH,
            "-filter_complex", fg,
            "-map", "[outv2]", "-map", "0:a",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT,
            "-c:a", config.ACODEC, "-b:a", config.ABITRATE,
            "-movflags", "+faststart",
            "-shortest",
            first_out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou em {slug}:\n{r.stderr[-1500:]}")
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # A checagem de cauda roda ANTES de concatenar o card, e não depois: ela
    # mede a energia do áudio bem no instante `end - start` dentro do arquivo,
    # esperando encontrar ali o fim (silencioso ou não) da fala real. Depois
    # de concatenado, esse mesmo instante passa a ser onde o card MUDO começa
    # — a leitura veria sempre uma queda de energia ali (fala -> silêncio do
    # card) e reportaria "cauda limpa" mesmo quando a fala foi cortada no
    # meio de uma palavra. A ordem importa: medir no arquivo sem o card.
    if audio.cauda_vaza(first_out, end - start):
        print(f"[render] !! {slug}: a fala não termina limpa — o fim pode estar "
              f"cortando palavra. Ajuste o `end` e renderize de novo.")

    # O card entra DEPOIS da checagem acima e ANTES de copiar para as outras
    # plataformas — as duas plataformas precisam do mesmo arquivo final.
    concatena_encerramento(first_out, project_dir)

    for subdir, name in outputs[1:]:
        d = layout.plataforma(project_dir, subdir)
        os.makedirs(d, exist_ok=True)
        shutil.copy2(first_out, os.path.join(d, name))

    # Caption de publicação ao lado de cada peça: o gestor abre e cola no campo
    # de legenda. Escrito depois das cópias para cobrir todas as plataformas.
    escreve_captions(project_dir, moment,
                     [os.path.join(layout.plataforma(project_dir, sub), nome)
                      for sub, nome in outputs])

    print(f"[render] {slug} OK")


def _e_do_youtube(peca: str) -> bool:
    """True quando a peça está na pasta de saída do YouTube.

    A pasta é o que distingue as duas cópias: o mp4 é pixel-idêntico e o slug
    é o mesmo, só o diretório muda. Vem do `layout`, nunca de literal.
    """
    pasta = os.path.basename(os.path.dirname(os.path.abspath(peca)))
    return pasta == layout.YOUTUBE_SHORTS


def escreve_captions(project_dir, moment, pecas):
    """Grava o caption de publicação ao lado de cada peça renderizada.

    A descrição é o `legenda_post` que a curadoria escreveu para o corte; as
    hashtags valem para o episódio inteiro e vêm do `textos.json`.

    A chamada para o episódio completo entra SÓ no `.txt` do YouTube: no
    Instagram a URL não é clicável e manda o leitor para fora do app. As duas
    peças deixam de ter caption idêntico por essa razão, e só por ela.

    Corte sem `legenda_post` ainda ganha o arquivo (as hashtags já poupam
    trabalho), mas AVISA: caption mudo publicado é pior que caption ausente,
    porque passa despercebido até estar no ar.
    """
    caption.valida("legenda_post", moment.get("legenda_post"), moment["slug"])
    descricao = (moment.get("legenda_post") or "").strip()
    if not descricao:
        print(f"[caption] !! {moment['slug']}: sem legenda_post — o .txt sai "
              f"só com as hashtags. Preencha em decisoes/curadoria.json.")

    hashtags = (textos.load(project_dir) or {}).get("hashtags", "")
    url = episodio.url_youtube(project_dir)
    if not url:
        print(f"[caption] !! {moment['slug']}: sem url_youtube no "
              f"episodio.json — o Short sai sem chamada para o episódio "
              f"completo. Preencha quando o vídeo longo estiver no ar.")

    escritos = []
    for peca in pecas:
        texto = caption.monta(descricao, hashtags,
                              url if _e_do_youtube(peca) else None)
        escritos.append(caption.escreve(peca, texto))
    return escritos


def escreve_caption_episodio(project_dir):
    """Grava título + descrição do episódio em `publicar/episodio.txt`.

    O `textos.json` é JSON, então copiar a descrição de lá para o YouTube
    obriga a lidar com `\\n` escapado. Este arquivo é o mesmo conteúdo já
    formatado, para abrir e colar.

    Devolve `None` sem criar arquivo quando ainda não há textos: episódio antes
    da etapa de materiais não tem o que colar, e um `.txt` vazio na pasta de
    publicação só confundiria.
    """
    dados = textos.load(project_dir) or {}
    texto = caption.monta_episodio(dados.get("titulo"), dados.get("descricao"),
                                   dados.get("hashtags"))
    if not texto:
        return None
    destino = layout.garante(layout.episodio_txt(project_dir))
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)
    return destino


def render_all(project_dir, platforms, only=None):
    """Renderiza todos os cortes de momentos.json (ou só os slugs em `only`)."""
    video_path = layout.video(project_dir)
    with open(layout.transcricao(project_dir), encoding="utf-8") as f:
        segments = json.load(f)["segments"]
    with open(layout.momentos(project_dir), encoding="utf-8") as f:
        momentos = json.load(f)

    nomes = _nomes_proprios(project_dir)

    for m in momentos:
        if only and m["slug"] not in only:
            continue
        render_cut(video_path, segments, m, project_dir, platforms, nomes=nomes)

    # Título e descrição do episódio saem junto: quem renderiza está publicando,
    # e é nessa hora que os dois textos são colados no YouTube.
    ep_txt = escreve_caption_episodio(project_dir)
    if ep_txt:
        print(f"[caption] episódio -> {os.path.basename(ep_txt)}")


def _nomes_proprios(project_dir):
    """Nomes que a legenda deve grafar como o episodio.json manda.

    A transcrição erra nome próprio (Zarvik/Zarvic/Zlarvik) e a
    legenda vai queimada no vídeo. Episódio sem metadados não quebra o render —
    segue sem correção.
    """
    try:
        ep = episodio.load(project_dir)
    except (FileNotFoundError, ValueError):
        return []
    nomes = [ep.get("empresa", "")]
    nomes += [c.get("nome", "") for c in ep.get("convidados") or []]
    return [n for n in nomes if n and len(n) >= 4]
