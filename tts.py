"""
Narracao 100% gratis via edge-tts (usa o servico de leitura em voz alta do
Microsoft Edge, sem precisar do navegador nem de chave de API - biblioteca
nao-oficial, mas e a opcao free mais usada em canais faceless).

Divide o roteiro em frases e gera 1 audio por frase. Isso e o que permite
sincronizar a legenda com a narracao sem precisar rodar Whisper (transcricao
por IA) pra descobrir os tempos - cada frase ja tem duracao conhecida.
"""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts

import config

# Vozes neurais gratuitas em PT-BR do Edge (troque a vontade):
#   pt-BR-FranciscaNeural (feminina) / pt-BR-AntonioNeural (masculina)
VOICE = getattr(config, "EDGE_TTS_VOICE", "pt-BR-AntonioNeural")


@dataclass
class Segment:
    text: str
    audio_path: Path
    duration_sec: float


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


async def _synth_one(text: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(out_path))


def synthesize_sentences(text: str, out_dir: Path) -> list[Segment]:
    """Gera um mp3 por frase do roteiro e retorna cada um com sua duracao."""
    import asyncio

    out_dir.mkdir(parents=True, exist_ok=True)
    sentences = _split_sentences(text)
    segments = []
    for i, sentence in enumerate(sentences):
        audio_path = out_dir / f"{i:03d}.mp3"
        asyncio.run(_synth_one(sentence, audio_path))
        duration = _probe_duration(audio_path)
        segments.append(Segment(text=sentence, audio_path=audio_path, duration_sec=duration))
    return segments
