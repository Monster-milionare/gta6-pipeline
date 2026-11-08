"""
Gera trilhas de fundo 100% originais (sintetizadas por codigo, zero custo,
zero risco de direitos autorais) no estilo "synthwave noturno" (Miami/
Vice City vibes) pra tocar bem baixinho (ver render.py: MUSICA_VOLUME)
por baixo da narracao dos videos.

Nao baixa nada de terceiros - e so osciladores simples (pad + arpejo +
"kick" suave) somados com numpy e salvos como WAV. Isso evita de vez o
problema de licenciamento/atribuicao de bancos de musica royalty-free,
e roda tanto local quanto no runner do GitHub Actions (so precisa de
numpy, ja adicionado no requirements.txt).

Gera N faixas variando progressao de acordes/bpm/semente, pra ter
variedade entre os videos (render.py escolhe uma aleatoriamente).
"""
import math
import os
import struct
import wave

import numpy as np

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SR = 44100

# Progressoes de acorde (notas em Hz, triade: fundamental, terca, quinta)
# estilo synthwave em tom menor - soam "noturnas"/tensas, combinam com
# o clima de noticias/especulacao sobre GTA VI.
NOTAS = {
    "A2": 110.00, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61,
    "G3": 196.00, "A3": 220.00, "C4": 261.63, "D4": 293.66, "E4": 329.63,
    "F4": 349.23, "G4": 392.00,
}

PROGRESSOES = [
    # (nome, bpm, [(acorde_raiz_grave, [tercas/quintas para pad+arpejo]), ...])
    ("noturna_am", 96, [
        ("A2", ["A3", "C4", "E4"]),
        ("F3", ["F3", "A3", "C4"]),
        ("C3", ["C4", "E4", "G4"]),
        ("G3", ["G3", "C4", "D4"]),
    ]),
    ("drive_dm", 104, [
        ("D3", ["D3", "F3", "A3"]),
        ("A2", ["A3", "C4", "E4"]),
        ("F3", ["F3", "A3", "C4"]),
        ("G3", ["G3", "C4", "D4"]),
    ]),
]


def _env_pluck(n, attack=0.004, decay=0.35):
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1)
    d = np.exp(-t / decay)
    return a * d


def _env_pad(n, attack=0.8, release=0.8, total_sec=0.0):
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1)
    r = np.clip((total_sec - t) / release, 0, 1)
    return np.clip(a * r, 0, 1)


def _osc(freqs_hz, n, detune=0.0):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs_hz:
        out += np.sin(2 * math.pi * f * t)
        if detune:
            out += 0.5 * np.sin(2 * math.pi * f * (1 + detune) * t)
    return out / max(len(freqs_hz), 1)


def _kick(n_total_samples, beat_sec, n_beats, vol=0.22):
    out = np.zeros(n_total_samples)
    dur = 0.18
    n_hit = int(dur * SR)
    t = np.arange(n_hit) / SR
    pitch_env = 70 * np.exp(-t / 0.05) + 45
    phase = 2 * math.pi * np.cumsum(pitch_env) / SR
    hit = np.sin(phase) * np.exp(-t / 0.12)
    for b in range(n_beats):
        start = int(b * beat_sec * SR)
        end = min(start + n_hit, n_total_samples)
        out[start:end] += hit[: end - start] * vol
    return out


def gerar_faixa(nome, bpm, progressao, seed=0):
    rnd = np.random.default_rng(seed)
    beat_sec = 60.0 / bpm
    beats_por_acorde = 8
    acorde_sec = beat_sec * beats_por_acorde
    n_acorde = int(acorde_sec * SR)

    pad_total = np.zeros(0)
    arp_total = np.zeros(0)

    for raiz, tons in progressao:
        f_raiz = NOTAS[raiz]
        freqs_pad = [NOTAS[t] for t in tons]

        # pad: acordes sustentados, com leve "detune" pra soar sintetico/amplo
        pad = _osc(freqs_pad, n_acorde, detune=0.006)
        pad *= _env_pad(n_acorde, attack=0.6, release=1.0, total_sec=acorde_sec)
        pad_total = np.concatenate([pad_total, pad * 0.5])

        # baixo: fundamental uma oitava abaixo, pulso simples em cada tempo
        baixo = np.zeros(n_acorde)
        n_nota = int(beat_sec * SR)
        env_baixo = _env_pluck(n_nota, attack=0.01, decay=0.5)
        onda_baixo = _osc([f_raiz / 2], n_nota) * env_baixo
        for b in range(beats_por_acorde):
            start = b * n_nota
            end = min(start + n_nota, n_acorde)
            baixo[start:end] += onda_baixo[: end - start]
        pad_total[-n_acorde:] += baixo * 0.35

        # arpejo: sobe e desce pelas notas do acorde em colcheias
        seq = tons + tons[::-1][1:]
        n_passo = int(beat_sec * SR / 2)
        env_arp = _env_pluck(n_passo, attack=0.003, decay=0.22)
        arp = np.zeros(n_acorde)
        passo_i = 0
        pos = 0
        while pos < n_acorde:
            nota = NOTAS[seq[passo_i % len(seq)]] * 2  # uma oitava acima p/ brilho
            fim = min(pos + n_passo, n_acorde)
            arp[pos:fim] += (_osc([nota], n_passo) * env_arp)[: fim - pos]
            pos += n_passo
            passo_i += 1
        arp_total = np.concatenate([arp_total, arp * 0.22])

    n_total = len(pad_total)
    n_beats_total = int(n_total / SR / beat_sec)
    kick = _kick(n_total, beat_sec, n_beats_total, vol=0.16)

    mix = pad_total + arp_total + kick
    pico = np.max(np.abs(mix)) + 1e-9
    mix = mix / pico * 0.82  # normaliza com um pouco de headroom

    # fade-in/out curto pra evitar clique no loop
    fade_n = int(0.05 * SR)
    fade_in = np.linspace(0, 1, fade_n)
    fade_out = fade_in[::-1]
    mix[:fade_n] *= fade_in
    mix[-fade_n:] *= fade_out

    pcm = (mix * 32767).astype(np.int16)
    out_path = os.path.join(OUT_DIR, f"{nome}.wav")
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    dur_s = n_total / SR
    print(f"gerado: {out_path} ({dur_s:.1f}s, {bpm}bpm)")
    return out_path


if __name__ == "__main__":
    for i, (nome, bpm, progressao) in enumerate(PROGRESSOES):
        gerar_faixa(nome, bpm, progressao, seed=i)
