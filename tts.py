"""
Narração 100% grátis via edge-tts (usa o serviço de leitura em voz alta do
Microsoft Edge, sem precisar do navegador nem de chave de API — biblioteca
não-oficial, mas é a opção free mais usada em canais faceless).

Divide o roteiro em frases e gera 1 áudio por frase. Isso é o que permite
sincronizar a legenda com a narração sem precisar rodar Whisper (transcrição
por IA) pra descobrir os tempos — cada frase já tem duração conhecida.

SOBRE EXPRESSIVIDADE DE VOZ (honesto, pra não vender ilusão): edge-tts é a
melhor opção 100% grátis que existe, mas ele usa um modelo de prosódia fixo
por voz — não é um modelo conversacional tipo o do ChatGPT/Gemini, que gera
entonação nova a cada frase com base no significado. Pra compensar isso,
aqui a gente varia rate/pitch por frase E aumenta a energia (rate/pitch mais
altos) em frases de impacto (fala por exclamação/pergunta, ou CTA de
like/inscrição) — não é 100% igual a uma voz "viva", mas já tira bastante
do efeito robótico de "ler tudo no mesmo tom". Pra ter a voz do nível
ChatGPT/Gemini de verdade precisaria de um serviço pago (ex.: ElevenLabs,
que tem cota free mas MUITO pequena pro volume diário desse canal).
"""
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts

import config

# Voz "humana" — pt-BR-MacerioMultilingualNeural é a voz masculina neural
# multilíngue mais recente da Microsoft pra PT-BR (geração mais nova, mais
# natural/expressiva que as vozes neurais "clássicas"). Se algum dia ela
# sumir do catálogo do edge-tts, cai pro fallback automaticamente — nunca
# trava o pipeline por causa de nome de voz.
VOICE_PREFERENCIAS = [
    getattr(config, "EDGE_TTS_VOICE", None),
    "pt-BR-MacerioMultilingualNeural",
    "pt-BR-AntonioNeural",
]

def _dedup_preservando_ordem(itens: list[str]) -> list[str]:
    vistos: set[str] = set()
    out = []
    for item in itens:
        if item and item not in vistos:
            vistos.add(item)
            out.append(item)
    return out

VOICE_PREFERENCIAS = _dedup_preservando_ordem(VOICE_PREFERENCIAS)
VOICE = VOICE_PREFERENCIAS[0]

# Variação de ritmo/tom por frase pra soar menos "robótico" (uma pessoa de
# verdade nunca fala toda frase exatamente no mesmo tom/ritmo). edge-tts
# aceita rate/pitch direto, sem precisar escrever SSML na mão.
# IMPORTANTE: edge-tts exige sinal explicito (+/-) mesmo pra zero -
# "0%" sozinho derruba com ValueError ("Invalid rate '0%'."), por isso
# "+0%" aqui (bug real que quebrou a publicação em produção - corrigido).
_RATE_VARIACAO = ("+0%", "+3%", "-3%", "+6%", "-5%", "+9%", "-1%")
_PITCH_VARIACAO = ("+0Hz", "+2Hz", "-2Hz", "+4Hz", "-3Hz", "+1Hz")

# Frases de impacto (exclamação/pergunta) e CTA de like/inscrição ganham
# rate/pitch mais altos de propósito — simula a "empolgação" que uma pessoa
# de verdade colocaria nesse tipo de frase, é o maior fator de diferença
# entre uma narração que soa "lida" e uma que soa "falada com energia".
_RATE_VARIACAO_ENERGICA = ("+9%", "+13%", "+17%", "+11%", "+15%")
_PITCH_VARIACAO_ENERGICA = ("+4Hz", "+6Hz", "+8Hz", "+5Hz")

# Pausa curta entre frases (silêncio no fim do áudio) — sem isso a
# narração gruda uma frase na outra sem respirar, o que é um dos
# principais motivos de voz sintética soar robótica.
PAUSA_ENTRE_FRASES_SEC = 0.22

@dataclass
class Segment:
    text: str
    audio_path: Path
    duration_sec: float
    is_cta: bool = False

def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]

def _eh_frase_energica(sentence: str, cta: bool) -> bool:
    """CTA sempre entra com energia; fora isso, qualquer frase que termine
    (ou tenha) exclamação/interrogação ganha rate/pitch mais altos — é o
    jeito mais simples e confiável (sem precisar de IA extra) de aproximar
    a entonação do que uma pessoa real faria com essas frases."""
    if cta:
        return True
    stripped = sentence.rstrip()
    return stripped.endswith(("!", "?")) or "!" in sentence or "?" in sentence

def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())

async def _synth_one(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))

def _synth_com_fallback(text: str, out_path: Path, rate: str, pitch: str) -> None:
    import asyncio

    ultimo_erro = None
    for voice in VOICE_PREFERENCIAS:
        try:
            asyncio.run(_synth_one(text, out_path, voice, rate, pitch))
            return
        except Exception as exc:  # voz pode não existir mais no catálogo do edge-tts
            ultimo_erro = exc
            continue
    raise RuntimeError(
        f"Nenhuma voz da lista {VOICE_PREFERENCIAS} funcionou."
    ) from ultimo_erro

def synthesize_sentences(text: str, out_dir: Path, cta: bool = False) -> list[Segment]:
    """Gera um mp3 por frase do roteiro e retorna cada um com sua duração.

    cta=True marca o(s) segmento(s) gerados como pedido de like/inscrição
    (usado por render.py pra trocar a pose do mascote pra "apontando" e
    mostrar o gráfico de like/inscrição na tela nesse trecho) e também faz
    esse segmento ser narrado com a variação de rate/pitch "energética"
    (ver _eh_frase_energica)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sentences = _split_sentences(text)
    segments = []
    for i, sentence in enumerate(sentences):
        audio_path = out_dir / f"{i:03d}.mp3"
        if _eh_frase_energica(sentence, cta):
            rate = random.choice(_RATE_VARIACAO_ENERGICA)
            pitch = random.choice(_PITCH_VARIACAO_ENERGICA)
        else:
            rate = random.choice(_RATE_VARIACAO)
            pitch = random.choice(_PITCH_VARIACAO)
        _synth_com_fallback(sentence, audio_path, rate, pitch)
        duration = _probe_duration(audio_path) + PAUSA_ENTRE_FRASES_SEC
        segments.append(Segment(text=sentence, audio_path=audio_path, duration_sec=duration, is_cta=cta))
    return segments
