"""Envelope de energia do áudio — onde a fala pausa, para cortar sem vazar.

Os tempos de clip saem da transcrição, cuja resolução é de 1 segundo. Um end
tirado dali cai em cima da fronteira entre duas words e deixa vazar o ataque
da seguinte: o clip terminava em 901.0 e o espectador ouvia o "Poucas"
que abre a frase seguinte.

A pausa entre words numa fala corrida é curta (~40ms no caso medido), então
margem fixed não resolve — recuar demais come a última sílaba aproveitada. O
jeito certo é olhar o áudio e cortar no vale.

Requer ffmpeg no PATH. Sem ele, as funções devolvem o tempo original: o render
segue funcionando, só sem o ajuste fino.
"""
from __future__ import annotations

import array
import math
import subprocess

# Janela de análise. 20ms é curto o bastante para achar pausa entre words e
# longo o bastante para o RMS não oscilar com o período da voz.
WINDOW_S = 0.02
RATE_HZ = 16000

# Quanto o ajuste pode recuar procurando a pausa. Meia janela de fala normal:
# além disso o clip perde conteúdo em vez de ganhar limpeza.
SEARCH_S = 0.60


def _pcm(video_path: str, start: float, dur: float) -> array.array:
    """Extrai um trecho de áudio como PCM mono 16-bit."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", video_path, "-ac", "1", "-ar", str(RATE_HZ), "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    a = array.array("h")
    a.frombytes(out[:len(out) // 2 * 2])
    return a


def envelope(video_path: str, start: float, dur: float) -> list:
    """[(t_absoluto, dB)] em janelas de WINDOW_S. dB relativo ao fundo de escala."""
    a = _pcm(video_path, start, dur)
    win = int(RATE_HZ * WINDOW_S)
    points = []
    for i in range(len(a) // win):
        ch = a[i * win:(i + 1) * win]
        rms = math.sqrt(sum(x * x for x in ch) / len(ch)) + 1e-9
        points.append((start + i * WINDOW_S, 20 * math.log10(rms / 32768)))
    return points


# Energia abaixo disto account como pausa. Fala fica acima de -25 dB; o floor de
# sala destes episódios ronda -50 dB.
PAUSE_THRESHOLD_DB = -35.0


# Silêncio mínimo para uma pausa contar como FIM DE FALA. Abaixo disto é pausa
# interna — respiração, hesitação, separação entre words — e cortar ali deixa
# a frase pela metade (vale de 80ms em 2341.56 era interno; a
# frase só terminava em 2342.26, com 660ms de silêncio depois).
SILENCE_MIN_S = 0.25


def _silence_duration(points: list, i: int, threshold: float) -> float:
    """Por quanto tempo a energia fica abaixo do threshold a partir de `i`."""
    j = i
    while j < len(points) and points[j][1] <= threshold:
        j += 1
    return (j - i) * WINDOW_S


def valley_before(video_path: str, t: float, search: float = SEARCH_S) -> float:
    """Instante da pausa REAL mais próxima de `t`, olhando para trás.

    Não basta a energia cair: o silêncio precisa DURAR. Numa fala corrida a
    energia mergulha entre words a cada 100ms, e cortar no primeiro mergulho
    parte a frase no meio. Só vale a pausa seguida de SILENCE_MIN_S de quietude.

    Sem pausa longa na janela, devolve `t` — melhor não mexer do que cortar no
    lugar errado.
    """
    try:
        points = envelope(video_path, max(0.0, t - search), search)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return t
    if not points:
        return t
    for i in range(len(points) - 1, -1, -1):     # do end pretendido para trás
        inst, db = points[i]
        if db <= PAUSE_THRESHOLD_DB and \
                _silence_duration(points, i, PAUSE_THRESHOLD_DB) >= SILENCE_MIN_S:
            # Corta no FUNDO da pausa, não na borda: a borda ainda tem cauda
            # da fala e o fundo é onde o ouvido não percebe emenda.
            j = i
            while j < len(points) and points[j][1] <= PAUSE_THRESHOLD_DB:
                j += 1
            return min(points[i:j], key=lambda p: p[1])[0]
    return t


def clips_mid_word(video_path: str, end: float, threshold_db: float = -25.0,
               window: float = 0.06) -> bool:
    """True se a fala ainda está ALTA no instante do clip.

    Toda fala termina com uma sílaba, então olhar 150ms para trás acusa
    qualquer clip — inclusive os corretos, onde a última palavra está sendo
    pronunciada e decai naturalmente. A pergunta certa é mais estreita: no
    exato ponto do clip, a energia ainda está em nível de fala?

    Janela de 60ms, e só acusa se a energia NÃO estiver caindo: palavra
    terminando decai; palavra cortada no meio para de repente com o nível alto.
    """
    # Lê com folga e fica com as últimas janelas: o mp4 sai alguns
    # milissegundos mais longo que o pedido, e ancorar no valor pedido deixava
    # a leitura com um ponto só — insuficiente para ver se a energia decai.
    try:
        points = envelope(video_path, max(0.0, end - window * 3), window * 3)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
    n = max(2, int(round(window / WINDOW_S)))
    points = points[-n:]
    if len(points) < 2:
        return False
    dbs = [db for _, db in points]
    # Fala terminando decai; fala cortada para de repente ainda no nível alto.
    # Medido: clip defeituoso fica em -31/-28/-31 dB (estável); os corretos
    # ou terminam abaixo de -35 dB ou despencam mais de 10 dB na última
    # janela ("importadas": -25.8 -> -39.4).
    if dbs[-1] <= threshold_db - 10.0:
        return False                     # terminou em silêncio
    return (dbs[0] - dbs[-1]) < 8.0      # não decaiu o bastante
