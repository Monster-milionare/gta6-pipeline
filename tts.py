"""
Narração 100% grátis via edge-tts (usa o serviço de leitura em voz alta do
Microsoft Edge, sem precisar do navegador nem de chave de API — biblioteca
não-oficial, mas é a opção free mais usada em canais faceless).

Divide o roteiro em frases e gera 1 áudio por frase. Além do áudio, guarda
o TEMPO DE CADA PALAVRA (evento "WordBoundary" do edge-tts) em
Segment.words — é isso que deixa o render.py fazer legenda palavra por
palavra e boca do mascote sincronizadas com a voz, sem rodar nenhuma IA de
transcrição.

SOBRE EXPRESSIVIDADE DE VOZ (honesto, pra não vender ilusão): edge-tts é a
melhor opção 100% grátis que existe, mas ele usa um modelo de prosódia fixo
por voz — não é um modelo conversacional tipo o do ChatGPT/Gemini. Pra
compensar, aqui a gente varia rate/pitch por frase E aumenta a energia
(rate/pitch mais altos) em frases de impacto (exclamação/pergunta, ou CTA).
"""
import asyncio
import inspect
import random
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import edge_tts

import config

# Voz "humana" — pt-BR-MacerioMultilingualNeural é a voz masculina neural
# multilíngue mais recente da Microsoft pra PT-BR. Se algum dia ela sumir
# do catálogo do edge-tts, cai pro fallback automaticamente.
VOICE_PREFERENCIAS = [
    getattr(config, "EDGE_TTS_VOICE", None),
    "pt-BR-MacerioMultilingualNeural",
    "pt-BR-AntonioNeural",
]


def _dedup_preservando_ordem(itens: list) -> list:
    vistos: set = set()
    out = []
    for item in itens:
        if item and item not in vistos:
            vistos.add(item)
            out.append(item)
    return out


VOICE_PREFERENCIAS = _dedup_preservando_ordem(VOICE_PREFERENCIAS)
VOICE = VOICE_PREFERENCIAS[0]

# IMPORTANTE: edge-tts exige sinal explícito (+/-) mesmo pra zero - "0%"
# sozinho derruba com ValueError (bug real que já quebrou a publicação).
_RATE_VARIACAO = ("+4%", "+7%", "+2%", "+10%", "+5%", "+12%", "+8%")
_PITCH_VARIACAO = ("+0Hz", "+2Hz", "-2Hz", "+4Hz", "-3Hz", "+1Hz")
_RATE_VARIACAO_ENERGICA = ("+12%", "+15%", "+18%", "+13%", "+16%")
_PITCH_VARIACAO_ENERGICA = ("+4Hz", "+6Hz", "+8Hz", "+5Hz")

PAUSA_ENTRE_FRASES_SEC = 0.22


@dataclass
class Segment:
    text: str
    audio_path: Path
    duration_sec: float
    is_cta: bool = False
    # [(palavra, inicio_seg, fim_seg)] relativo ao começo do áudio da frase
    words: list = field(default_factory=list)
    energica: bool = False


def _split_sentences(text: str) -> list:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _eh_frase_energica(sentence: str, cta: bool) -> bool:
    """CTA sempre entra com energia; fora isso, frase com exclamação ou
    interrogação ganha rate/pitch mais altos."""
    return cta or "!" in sentence or "?" in sentence


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


async def _synth_one(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> list:
    kwargs = {}
    # edge-tts >= 7 só manda o tempo de cada palavra se pedir explicitamente
    if "boundary" in inspect.signature(edge_tts.Communicate.__init__).parameters:
        kwargs["boundary"] = "WordBoundary"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, **kwargs)
    words = []
    recebeu_audio = False
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
                recebeu_audio = True
            elif chunk["type"] == "WordBoundary":
                inicio = chunk["offset"] / 10_000_000
                words.append((chunk["text"], inicio, inicio + chunk["duration"] / 10_000_000))
    if not recebeu_audio:
        raise RuntimeError("edge-tts não devolveu áudio")
    return words


def _synth_com_fallback(text: str, out_path: Path, rate: str, pitch: str) -> list:
    ultimo_erro = None
    for voice in VOICE_PREFERENCIAS:
        for _tentativa in range(2):
            try:
                return asyncio.run(_synth_one(text, out_path, voice, rate, pitch))
            except Exception as exc:  # voz fora do catálogo ou soluço de rede
                ultimo_erro = exc
    raise RuntimeError(
        f"Nenhuma voz da lista {VOICE_PREFERENCIAS} funcionou."
    ) from ultimo_erro


def synthesize_sentences(text: str, out_dir: Path, cta: bool = False) -> list:
    """Gera um mp3 por frase do roteiro e retorna cada um com sua duração
    e o tempo de cada palavra.

    cta=True marca o(s) segmento(s) como pedido de like/inscrição (render.py
    anima o botão de like/inscrição e o mascote aponta pra ele)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sentences = _split_sentences(text)
    segments = []
    for i, sentence in enumerate(sentences):
        audio_path = out_dir / f"{i:03d}.mp3"
        energica = _eh_frase_energica(sentence, cta)
        if energica:
            rate = random.choice(_RATE_VARIACAO_ENERGICA)
            pitch = random.choice(_PITCH_VARIACAO_ENERGICA)
        else:
            rate = random.choice(_RATE_VARIACAO)
            pitch = random.choice(_PITCH_VARIACAO)
        words = _synth_com_fallback(sentence, audio_path, rate, pitch)
        duration = _probe_duration(audio_path) + PAUSA_ENTRE_FRASES_SEC
        segments.append(Segment(text=sentence, audio_path=audio_path, duration_sec=duration,
                                is_cta=cta, words=words, energica=energica))
    return segments
