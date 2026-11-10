#!/usr/bin/env python3
"""
Renderiza um video de TESTE (nao publica nada) com o roteiro mais recente
e salva uma "folha de quadros" em preview/ pra conferir a edicao sem
precisar subir no YouTube. Usado pelo workflow "Preview da edicao".

Uso: python preview.py [short|long]
"""
import io
import subprocess
import sys
from pathlib import Path

from PIL import Image

import config
from content_batch import load_batch
from render import render_video
from tts import synthesize_sentences


def _quadro(video: Path, t: float, larg: int) -> Image.Image:
    bruto = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    img = Image.open(io.BytesIO(bruto)).convert("RGB")
    img.thumbnail((larg, 4000))
    return img


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "short"
    arquivos = sorted(config.REVIEW_DIR.glob("*.md"))
    batch = load_batch(arquivos[-1], arquivos[-1].stem)
    item = next(i for i in batch.items if i.kind == kind)
    audio_dir = config.ASSETS_DIR / "tmp" / "audio" / "preview"
    segs = synthesize_sentences(item.roteiro, audio_dir)
    if kind == "long":
        segs = segs[:9]
    segs += synthesize_sentences("Curte o video e se inscreve no canal pra nao perder nada de GTA VI.",
                                 audio_dir / "cta", cta=True)
    video = config.ASSETS_DIR / "tmp" / f"preview_{kind}.mp4"
    render_video(kind, item.titulo, segs, video)

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout.strip())
    tempos = [0.7, 2.0] + [dur * k / 7 for k in range(1, 6)] + [dur - 1.0]
    larg, colunas = (300, 4) if kind == "short" else (640, 2)
    quadros = [_quadro(video, t, larg) for t in tempos]
    qw, qh = quadros[0].size
    linhas = (len(quadros) + colunas - 1) // colunas
    folha = Image.new("RGB", (colunas * qw + (colunas - 1) * 6, linhas * qh + (linhas - 1) * 6), "white")
    for i, q in enumerate(quadros):
        folha.paste(q, ((i % colunas) * (qw + 6), (i // colunas) * (qh + 6)))
    pasta = config.BASE_DIR / "preview"
    pasta.mkdir(exist_ok=True)
    folha.save(pasta / f"folha_{kind}.jpg", quality=86)
    clipes = len(list((config.ASSETS_DIR / "clipes_oficiais").glob("*_h.mp4")))
    com_tempo = sum(1 for s in segs if s.words)
    (pasta / f"info_{kind}.txt").write_text(
        f"item: {item.item_id} - {item.titulo}\n"
        f"duracao: {dur:.1f}s | frases: {len(segs)} | frases com tempo por palavra: {com_tempo}\n"
        f"clipes oficiais disponiveis: {clipes}\n"
        f"exemplo de palavras: {segs[0].words[:6]}\n", encoding="utf-8")
    print(f"[preview] ok: {pasta / f'folha_{kind}.jpg'} ({dur:.1f}s, {clipes} clipes)")


if __name__ == "__main__":
    main()
