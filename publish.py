#!/usr/bin/env python3
"""
Roda varias vezes ao dia (via GitHub Actions agendado - ver README). A cada
execucao, pega o PROXIMO item ja aprovado e ainda nao publicado, gera a
narracao frase a frase, monta o video com ffmpeg e agenda o upload no
YouTube.

Uso normal (via schedule): python publish.py
Processar tudo que restar hoje de uma vez: python publish.py --all
"""
import sys
from datetime import date as date_cls
from pathlib import Path

import config
from content_batch import load_batch, mark_item_published, next_unpublished
from render import render_video
from tts import synthesize_sentences
from upload import upload_video


def _description(item, date_str: str) -> str:
    return (
        f"{item.titulo}\n\n"
        f"Conteudo baseado em material oficial da Rockstar Games/Take-Two "
        f"Interactive sobre GTA VI. Lancamento: 19/11/2026.\n"
        f"#GTA6 #GTAVI #RockstarGames"
    )


def _process_item(item, date_str: str, review_path: Path) -> None:
    print(f"[publish] processando {item.item_id} ({item.kind}): {item.titulo}")

    audio_dir = config.ASSETS_DIR / "tmp" / "audio" / item.item_id
    segments = synthesize_sentences(item.roteiro, audio_dir)

    video_path = config.ASSETS_DIR / "tmp" / f"{item.item_id}.mp4"
    render_video(item.kind, item.titulo, segments, video_path)

    video_id = upload_video(
        video_path=video_path,
        title=item.titulo,
        description=_description(item, date_str),
        tags=["GTA VI", "GTA 6", "Rockstar Games"],
        is_short=(item.kind == "short"),
    )

    mark_item_published(review_path, date_str, item.item_id)
    print(f"[publish] {item.item_id} publicado/agendado como https://youtu.be/{video_id}")


def main():
    date_str = date_cls.today().isoformat()
    review_path = config.REVIEW_DIR / f"{date_str}.md"

    if not review_path.exists():
        print(f"[publish] {review_path} nao existe - rode generate.py hoje.")
        return

    batch = load_batch(review_path, date_str)
    if batch.status != "APROVADO":
        print(f"[publish] lote de {date_str} ainda nao foi aprovado (rode approve.py {date_str}).")
        return

    process_all = "--all" in sys.argv
    processed_any = False
    while True:
        item = next_unpublished(load_batch(review_path, date_str))
        if not item:
            break
        _process_item(item, date_str, review_path)
        processed_any = True
        if not process_all:
            break

    if not processed_any:
        print(f"[publish] nada pendente em {date_str} - todo o lote ja foi publicado.")


if __name__ == "__main__":
    main()
