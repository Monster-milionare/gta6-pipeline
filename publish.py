#!/usr/bin/env python3
"""
Roda várias vezes ao dia (via GitHub Actions agendado — ver README). A cada
execução, pega o PRÓXIMO item já aprovado e ainda não publicado, gera a
narração frase a frase, monta o vídeo com ffmpeg e agenda o upload no
YouTube.

IMPORTANTE (auto-recuperação): o workflow sempre chama "python publish.py
--all" agora, não só "python publish.py". Isso existe porque o cron do
GitHub Actions não é confiável de verdade — na prática, execuções agendadas
saem atrasadas (observamos horários previstos pra 09h/06h BRT rodando só
às 12h) ou simplesmente não disparam nesse dia. Se cada execução só
processasse 1 item, um agendamento perdido virava um short que nunca sai
do forno. Com --all, QUALQUER execução (mesmo atrasada, mesmo substituindo
2-3 horários perdidos) processa tudo que ainda falta publicar no dia, uma
de cada vez, com uma pausa aleatória real entre cada item (ver
_ESPERA_ENTRE_ITENS_MIN) pra continuar parecendo um canal publicando no
ritmo humano, não uma rajada de uploads simultâneos (o tipo de padrão que
o sistema anti-spam do YouTube usa pra agrupar/banir canais - ver README).

Uso: python publish.py [--all]
"""
import random
import sys
import time
from datetime import date as date_cls
from pathlib import Path

import config
from content_batch import load_batch, mark_item_published, next_unpublished
from gerar_thumbnail import gerar_thumbnail
from render import render_video
from tts import synthesize_sentences
from upload import set_thumbnail, upload_video

# Pedido de like/inscrição: fixo e programático (não depende do LLM lembrar
# de pedir isso no roteiro, que seria inconsistente) - roda no fim de todo
# vídeo. Varia entre algumas frases pra não soar repetitivo pra quem
# assiste vários vídeos do canal seguidos; render.py detecta
# Segment.is_cta=True e troca o mascote pra pose "apontando" + desenha o
# gráfico de like/inscrição nesse trecho (ver render.py).
CTA_FRASES = [
    "Curte o vídeo e se inscreve no canal pra não perder nenhuma notícia de GTA VI.",
    "Se esse vídeo te ajudou, deixa o like e se inscreve aqui no canal.",
    "Ativa o sininho e se inscreve no canal pra acompanhar tudo sobre GTA VI em primeira mão.",
    "Deixa o like, comenta o que você achou e se inscreve pra ficar por dentro de GTA VI.",
]

# Pausa real entre itens quando há mais de 1 pra publicar na mesma
# execução (catch-up) - minutos. Faixa larga o bastante pra não parecer
# robótico, curta o bastante pra ainda caber tudo dentro do limite de 6h
# de job do GitHub Actions mesmo processando o lote inteiro do zero.
_ESPERA_ENTRE_ITENS_MIN = (12, 25)

def _cta_frase(item) -> str:
    # escolha determinística por item (a mesma frase se o vídeo for
    # reprocessado), variando entre os itens do lote.
    idx = hash(item.item_id) % len(CTA_FRASES)
    return CTA_FRASES[idx]

def _gerar_thumbnail_seguro(item) -> Path | None:
    """Nunca deixa um erro na geração da thumbnail derrubar o publish.py -
    pior caso, o vídeo sai sem thumbnail customizada (YouTube usa um frame
    aleatório), o que é bem melhor que travar a publicação inteira."""
    try:
        thumb_path = config.ASSETS_DIR / "tmp" / f"{item.item_id}_thumb.jpg"
        return gerar_thumbnail(item.titulo, thumb_path)
    except Exception as exc:
        print(f"[publish] aviso: falhou ao gerar thumbnail de {item.item_id}: {exc}")
        return None

def _set_thumbnail_seguro(video_id: str, thumb_path: Path) -> None:
    """set_thumbnail pode dar 403 em canais que ainda não verificaram o
    telefone no YouTube ("doesn't have permissions to upload and set
    custom video thumbnails") - isso é esperado até a verificação, nunca
    deve travar o resto da publicação."""
    try:
        set_thumbnail(video_id, thumb_path)
    except Exception as exc:
        print(f"[publish] aviso: falhou ao definir thumbnail de {video_id}: {exc}")

def _description(item, date_str: str) -> str:
    return (
        f"{item.titulo}\n\n"
        f"Conteúdo baseado em material oficial da Rockstar Games/Take-Two "
        f"Interactive sobre GTA VI. Lançamento: 19/11/2026.\n"
        f"#GTA6 #GTAVI #RockstarGames"
    )

def _process_item(item, date_str: str, review_path: Path) -> None:
    print(f"[publish] processando {item.item_id} ({item.kind}): {item.titulo}")

    audio_dir = config.ASSETS_DIR / "tmp" / "audio" / item.item_id
    segments = synthesize_sentences(item.roteiro, audio_dir)
    cta_segments = synthesize_sentences(_cta_frase(item), audio_dir / "cta", cta=True)
    segments = segments + cta_segments

    video_path = config.ASSETS_DIR / "tmp" / f"{item.item_id}.mp4"
    render_video(item.kind, item.titulo, segments, video_path)

    thumb_path = _gerar_thumbnail_seguro(item)

    video_id = upload_video(
        video_path=video_path,
        title=item.titulo,
        description=_description(item, date_str),
        tags=["GTA VI", "GTA 6", "Rockstar Games"],
        is_short=(item.kind == "short"),
    )

    if thumb_path is not None:
        _set_thumbnail_seguro(video_id, thumb_path)

    mark_item_published(review_path, date_str, item.item_id)
    print(f"[publish] {item.item_id} publicado/agendado como https://youtu.be/{video_id}")

def main():
    date_str = date_cls.today().isoformat()
    review_path = config.REVIEW_DIR / f"{date_str}.md"

    if not review_path.exists():
        print(f"[publish] {review_path} não existe — rode generate.py hoje.")
        return

    batch = load_batch(review_path, date_str)
    if batch.status != "APROVADO":
        print(f"[publish] lote de {date_str} ainda não foi aprovado (rode approve.py {date_str}).")
        return

    process_all = "--all" in sys.argv
    processed_any = False
    primeiro = True
    while True:
        item = next_unpublished(load_batch(review_path, date_str))
        if not item:
            break
        if not primeiro:
            espera_min = random.randint(*_ESPERA_ENTRE_ITENS_MIN)
            print(f"[publish] aguardando ~{espera_min}min antes do próximo item (evita rajada de uploads).")
            time.sleep(espera_min * 60)
        _process_item(item, date_str, review_path)
        processed_any = True
        primeiro = False
        if not process_all:
            break

    if not processed_any:
        print(f"[publish] nada pendente em {date_str} — todo o lote já foi publicado.")

if __name__ == "__main__":
    main()
