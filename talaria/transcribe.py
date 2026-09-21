"""Transcrição automática: legenda do YouTube (rápido) ou Whisper local (fallback).

Saída: <projeto>/transcricao.json  {"segments": [{start, end, text}]}
       <projeto>/transcricao.txt   (legível, com [mm:ss] por bloco, p/ curadoria)
"""
import json

from . import acquire, config, layout, utils, vtt_parse


def _write_outputs(segments, project_dir):
    with open(layout.garante(layout.transcricao(project_dir)), "w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)

    # versão legível em blocos de ~25s (1 parágrafo por bloco) p/ curadoria
    blocks, cur, start = [], [], None
    for s in segments:
        if start is None:
            start = s["start"]
        cur.append(s["text"])
        if s["end"] - start >= 25:
            blocks.append((start, s["end"], " ".join(cur)))
            cur, start = [], None
    if cur:
        blocks.append((start, segments[-1]["end"], " ".join(cur)))
    with open(layout.garante(layout.transcricao_txt(project_dir)), "w", encoding="utf-8") as f:
        for a, b, txt in blocks:
            f.write(f"[{utils.mmss(a)}-{utils.mmss(b)}] {txt}\n\n")

    dur = utils.mmss(segments[-1]["end"]) if segments else "00:00"
    print(f"[transcribe] {len(segments)} segmentos, {len(blocks)} blocos, duração {dur}")


def from_youtube_captions(vtt_path, project_dir):
    """Parseia um VTT já baixado. Retorna True se gerou segmentos."""
    segments = vtt_parse.parse_vtt(vtt_path)
    if not segments:
        return False
    _write_outputs(segments, project_dir)
    print("[transcribe] via legenda do YouTube")
    return True


def from_whisper(video_path, project_dir, model=None):
    """Transcreve o vídeo com faster-whisper (fallback CUDA->CPU)."""
    from faster_whisper import WhisperModel

    model = model or config.WHISPER_MODEL
    device, compute = "cuda", "float16"
    try:
        wm = WhisperModel(model, device=device, compute_type=compute)
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe] GPU indisponível ({e}); usando CPU int8.")
        device, compute = "cpu", "int8"
        wm = WhisperModel(model, device=device, compute_type=compute)

    print(f"[transcribe] Whisper {model} em {device} (isso leva alguns minutos)...")
    seg_iter, _info = wm.transcribe(
        video_path, language=config.WHISPER_LANG, word_timestamps=True,
    )
    # reagrupa por palavras p/ manter o mesmo estilo de segmento do VTT
    words = []
    for s in seg_iter:
        if s.words:
            for w in s.words:
                words.append((w.start, w.word.strip()))
        else:
            words.append((s.start, s.text.strip()))
    segments = utils.group_words_into_segments(words)
    _write_outputs(segments, project_dir)
    print("[transcribe] via Whisper local")
    return True


def transcribe(source, video_path, project_dir, model=None):
    """Orquestra: se source é YouTube com legenda, usa ela; senão Whisper.

    source: URL original (ou path local). video_path: fonte.mp4 já baixado.
    """
    if acquire.detect_source(source) == "youtube":
        vtt = acquire.fetch_youtube_captions(source, project_dir, config.WHISPER_LANG)
        if vtt and from_youtube_captions(vtt, project_dir):
            return
        print("[transcribe] sem legenda no YouTube; caindo para Whisper.")
    from_whisper(video_path, project_dir, model=model)
