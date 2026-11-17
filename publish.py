#!/usr/bin/env python3
"""
Publica o lote do dia no YouTube. Pra cada item aprovado e ainda não
publicado: gera a narração, monta o vídeo (render.py) e sobe pro YouTube.

COMO ISSO SOBREVIVE AO CRON RUIM DO GITHUB (motivo de já ter ficado dias
sem sair vídeo): o agendador do GitHub Actions atrasa horas ou nem dispara.
Então o desenho aqui é "qualquer execução resolve o dia inteiro":

1. UMA execução sobe TODOS os itens pendentes do dia de uma vez, e quem
   espalha os vídeos ao longo do dia é o próprio YouTube: cada item sobe
   como privado com "publishAt" no horário-alvo dele (SLOT_LONGO /
   SLOTS_SHORTS, horário de Brasília). Não tem mais "sleep" de 12-25min
   entre itens segurando a máquina (isso queimava a cota grátis de minutos
   do Actions e deixava a execução horas exposta a falha).
2. Se a execução sair atrasada e o horário-alvo de um item já passou, ele
   sai na hora (ou GAP_MIN minutos depois do anterior, pra não virar
   rajada de uploads públicos no mesmo minuto).
3. O status "Publicado: sim" é salvo no repositório (git push) LOGO APÓS
   cada item, não só no fim - se a execução morrer no meio, a próxima não
   sobe o mesmo vídeo duas vezes.
4. Se um item der erro (render, upload...), ele é pulado e os outros
   continuam - um item quebrado não trava mais a fila inteira. A execução
   termina vermelha no fim pra ficar visível na aba Actions.
5. O "dia" é sempre o dia em Brasília (não UTC), então execução atrasada
   de noite não cai no dia seguinte por engano.

Uso: python publish.py [--all]
"""
import os
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import estilos
import render as _render_mod
import unicidade
from content_batch import load_batch, mark_item_published
from gerar_thumbnail import gerar_thumbnail
from render import render_video
from tts import synthesize_sentences
from upload import set_thumbnail, upload_video

FUSO = ZoneInfo("America/Sao_Paulo")

# O video longo sai em 1280x720 (YouTube exibe em HD normal): o render quadro
# a quadro em 1920x1080 era ~2,5x mais lento e queimava os minutos gratis do
# GitHub Actions. O short continua 1080x1920.
_render_mod.RESOLUTIONS["long"] = (1280, 720)


class CotaEsgotada(Exception):
    """Cota diaria da API do YouTube acabou - nao adianta tentar de novo hoje."""

_thumb_bloqueada = False   # canal sem verificacao por telefone: 403 em toda thumbnail

# Horários-alvo de publicação (Brasília). Longo perto do almoço, shorts
# espalhados do almoço até a noite (picos de uso de celular no Brasil).
SLOT_LONGO = "19:00"   # pico de noite no Brasil
SLOTS_SHORTS = ["12:20", "10:20", "08:50", "14:10", "16:00", "17:40", "19:20", "20:50"]
# Distância mínima entre dois vídeos indo ao ar (quando os horários-alvo
# já passaram e a execução está "correndo atrás").
GAP_MIN = 25
# "publishAt" precisa estar no futuro; menos que isso de folga, publica na hora.
ANTECEDENCIA_MIN = 12

# Pedido de like/inscrição: fixo e programático (não depende do LLM lembrar
# de pedir isso no roteiro) - roda no fim de todo vídeo. render.py detecta
# Segment.is_cta=True e anima o botão de like/inscrição nesse trecho.
CTA_TEORIA = ("Comenta 1 ou 2 aqui embaixo e se inscreve: a teoria mais votada "
              "vira video exclusivo no canal.")
CTA_FRASES = [
    "Curte o vídeo e se inscreve no canal pra não perder nenhuma notícia de GTA VI.",
    "Se esse vídeo te ajudou, deixa o like e se inscreve aqui no canal.",
    "Ativa o sininho e se inscreve no canal pra acompanhar tudo sobre GTA VI em primeira mão.",
    "Deixa o like, comenta o que você achou e se inscreve pra ficar por dentro de GTA VI.",
]


CTA_VAZAMENTO = ("Quer saber o que a Rockstar realmente confirmar? Se inscreve no canal: "
                 "aqui rumor e rumor, e fato e fato.")


def _cta_frase(item) -> str:
    if item.item_id.startswith("teoria-"):
        return CTA_TEORIA
    if item.item_id.startswith("vazamento-"):
        return CTA_VAZAMENTO
    idx = sum(ord(c) for c in item.item_id) % len(CTA_FRASES)
    return CTA_FRASES[idx]


def _gerar_thumbnail_seguro(item) -> Path | None:
    """Erro na thumbnail nunca derruba a publicação - pior caso o vídeo
    sai sem thumbnail customizada."""
    try:
        thumb_path = config.ASSETS_DIR / "tmp" / f"{item.item_id}_thumb.jpg"
        return gerar_thumbnail(item.titulo, thumb_path)
    except Exception as exc:
        print(f"[publish] aviso: falhou ao gerar thumbnail de {item.item_id}: {exc}")
        return None


def _set_thumbnail_seguro(video_id: str, thumb_path: Path) -> None:
    """set_thumbnail dá 403 em canal sem telefone verificado - esperado,
    nunca trava o resto."""
    global _thumb_bloqueada
    if _thumb_bloqueada:
        return
    try:
        set_thumbnail(video_id, thumb_path)
    except Exception as exc:
        if "403" in str(exc) or "forbidden" in str(exc).lower():
            _thumb_bloqueada = True   # nao gasta cota tentando de novo
        print(f"[publish] aviso: falhou ao definir thumbnail de {video_id}: {exc}")


def _description(item) -> str:
    aviso = ("ATENCAO: este video fala de um RELATO/RUMOR NAO CONFIRMADO pela Rockstar Games. "
             "Nada aqui e oficial.\n\n") if item.item_id.startswith("vazamento-") else ""
    return (
        f"{item.titulo}\n\n{aviso}"
        f"Conteúdo baseado em material oficial da Rockstar Games/Take-Two "
        f"Interactive sobre GTA VI. Lançamento: 19/11/2026.\n"
        f"#GTA6 #GTAVI #RockstarGames"
    )


def _upload_com_retry(**kwargs) -> str:
    """Sobe o video tentando de novo em erro passageiro (rede, 5xx do Google).
    Cota esgotada levanta CotaEsgotada (sem insistir); outros erros sobem."""
    ultimo = None
    for tentativa in range(1, 5):
        try:
            return upload_video(**kwargs)
        except Exception as exc:
            msg = str(exc)
            if "quotaExceeded" in msg or "uploadLimitExceeded" in msg or "dailyLimitExceeded" in msg:
                raise CotaEsgotada(msg) from exc
            if "invalid_grant" in msg or "RefreshError" in type(exc).__name__:
                raise RuntimeError(
                    "TOKEN DO YOUTUBE INVALIDO/EXPIRADO (invalid_grant): gere de novo o "
                    "token.json e atualize o secret YOUTUBE_TOKEN_JSON.") from exc
            status = getattr(getattr(exc, "resp", None), "status", None)
            passageiro = status in (500, 502, 503, 504) or isinstance(
                exc, (ConnectionError, TimeoutError, OSError)) or "timed out" in msg.lower()
            ultimo = exc
            if not passageiro or tentativa == 4:
                break
            espera = 20 * tentativa
            print(f"[publish] upload falhou ({exc!r}) - tentativa {tentativa}/4, aguardando {espera}s")
            time.sleep(espera)
    raise ultimo


def _slot_do_item(batch, item, date_str: str) -> datetime:
    if item.kind == "long":
        hhmm = SLOT_LONGO
    else:
        shorts = [i.item_id for i in batch.items if i.kind == "short"]
        idx = shorts.index(item.item_id) if item.item_id in shorts else 0
        hhmm = SLOTS_SHORTS[min(idx, len(SLOTS_SHORTS) - 1)]
    hora, minuto = (int(x) for x in hhmm.split(":"))
    ano, mes, dia = (int(x) for x in date_str.split("-"))
    return datetime(ano, mes, dia, hora, minuto, tzinfo=FUSO)


def _decidir_horario(slot: datetime, ultimo: datetime | None) -> datetime | None:
    """None = publica agora (público direto). datetime = sobe privado e o
    YouTube publica sozinho nesse horário."""
    agora = datetime.now(FUSO)
    folga = timedelta(minutes=ANTECEDENCIA_MIN)
    gap = timedelta(minutes=GAP_MIN)
    alvo = slot if ultimo is None else max(slot, ultimo + gap)
    if alvo > agora + folga:
        return alvo
    if ultimo is None or ultimo + gap <= agora:
        return None
    return max(ultimo + gap, agora + folga)


def _git(*args: str) -> int:
    return subprocess.run(["git", *args], check=False).returncode


def _salvar_status_git(item_id: str) -> None:
    """Empurra "Publicado: sim" pro repositório logo depois de cada item
    (só dentro do GitHub Actions). O vídeo já está no YouTube nesse ponto;
    perder essa marcação = risco de subir o mesmo vídeo de novo."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    try:
        _git("config", "user.name", "gta6-pipeline-bot")
        _git("config", "user.email", "actions@users.noreply.github.com")
        _git("add", "review/")
        for f in ("state/videos.json", "state/pesos.json"):
            if Path(f).exists():
                _git("add", "-f", f)
        if _git("diff", "--cached", "--quiet") == 0:
            return
        _git("commit", "-m", f"chore: {item_id} publicado")
        for tentativa in range(1, 6):
            if _git("push") == 0:
                print(f"[publish] status de {item_id} salvo no repositorio.")
                return
            print(f"[publish] push rejeitado (tentativa {tentativa}/5) - rebase e tenta de novo")
            _git("pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(5)
        print(f"[publish] AVISO: nao consegui salvar o status de {item_id} no repositorio.")
    except Exception as exc:
        print(f"[publish] AVISO: erro ao salvar status de {item_id} no git: {exc}")


def _process_item(batch, item, date_str: str, review_path: Path, ultimo: datetime | None) -> datetime:
    """Renderiza + sobe 1 item. Retorna o horário em que ele vai ao ar."""
    print(f"[publish] processando {item.item_id} ({item.kind}): {item.titulo}", flush=True)

    audio_dir = config.ASSETS_DIR / "tmp" / "audio" / item.item_id
    segments = synthesize_sentences(item.roteiro, audio_dir)
    cta_segments = synthesize_sentences(_cta_frase(item), audio_dir / "cta", cta=True)
    segments = segments + cta_segments

    video_path = config.ASSETS_DIR / "tmp" / f"{item.item_id}.mp4"
    # Atualizacao 2.0: o ritmo de corte vem do estilo do item (rotativo). Lotes
    # antigos, sem "Estilo:", ganham um estilo sorteado de forma estavel pelo id.
    if not item.estilo:
        try:
            item.estilo = estilos.planejar_dia([(item.item_id, item.kind)], item.item_id)[0][0]
        except Exception:
            item.estilo = "neon"
    print(f"[publish] estilo de edicao: {item.estilo} | pegada: {item.pegada or '-'}", flush=True)
    render_video(item.kind, item.titulo, segments, video_path, item.estilo)

    thumb_path = _gerar_thumbnail_seguro(item)

    quando = _decidir_horario(_slot_do_item(batch, item, date_str), ultimo)
    kwargs = dict(
        video_path=video_path,
        title=item.titulo,
        description=_description(item),
        tags=["GTA VI", "GTA 6", "Rockstar Games"] + (["GTA 6 vazamento", "GTA 6 rumor"] if item.item_id.startswith("vazamento-") else []),
        is_short=(item.kind == "short"),
    )
    video_id = None
    if quando is not None:
        iso = quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        try:
            video_id = _upload_com_retry(publish_at_iso=iso, **kwargs)
            print(f"[publish] {item.item_id} agendado pra {quando:%d/%m %H:%M} (Brasilia)")
        except CotaEsgotada:
            raise
        except Exception as exc:
            print(f"[publish] aviso: upload agendado falhou ({exc}) - tentando publicar direto.")
            quando = None
    if video_id is None:
        video_id = _upload_com_retry(**kwargs)
        quando = datetime.now(FUSO)
        print(f"[publish] {item.item_id} publicado direto (publico agora).")

    if thumb_path is not None:
        _set_thumbnail_seguro(video_id, thumb_path)

    mark_item_published(review_path, date_str, item.item_id)
    estilos.registrar_video(item, video_id, (quando or datetime.now(FUSO)).isoformat())
    _salvar_status_git(item.item_id)
    print(f"[publish] {item.item_id} -> https://youtu.be/{video_id}", flush=True)
    return quando


def main() -> int:
    date_str = datetime.now(FUSO).date().isoformat()
    review_path = config.REVIEW_DIR / f"{date_str}.md"

    if not review_path.exists():
        print(f"[publish] {review_path} não existe — rode generate.py hoje.")
        return 0

    batch = load_batch(review_path, date_str)
    if batch.status != "APROVADO":
        print(f"[publish] lote de {date_str} não está aprovado (trava de qualidade) - nada a publicar.")
        return 0

    try:
        _lim = int((config.BASE_DIR / "limite_uploads.txt").read_text().strip())
    except Exception:
        _lim = 2
    pendentes = [i for i in batch.items[:_lim] if not i.publicado]   # Atualizacao 3.0: teto diario
    if not pendentes:
        print(f"[publish] nada pendente em {date_str} — todo o lote já foi publicado.")
        return 0
    if "--all" not in sys.argv:
        pendentes = pendentes[:1]

    ultimo = None
    falhas = []
    for n, item in enumerate(pendentes):
        if n > 0:
            time.sleep(random.randint(5, 15))
        # Ultima trava anti-repeticao: nunca sobe tema igual a algo ja publicado
        # (de hoje ou de qualquer dia anterior).
        try:
            repetido = unicidade.achar_repeticao(
                item.titulo, item.roteiro,
                unicidade.carregar_historico(so_publicados=True), ignorar_id=item.item_id)
        except Exception as exc:
            repetido = None
            print(f"[publish] aviso: checagem de repeticao falhou ({exc!r}) - seguindo.")
        if repetido:
            print(f"[publish] PULADO {item.item_id}: tema repetido - {repetido}", flush=True)
            mark_item_published(review_path, date_str, item.item_id)
            _salvar_status_git(item.item_id)
            continue
        try:
            ultimo = _process_item(batch, item, date_str, review_path, ultimo)
        except CotaEsgotada as exc:
            print(f"[publish] COTA DIARIA DO YOUTUBE ESGOTADA - paro por hoje ({exc}).")
            return 2
        except Exception:
            print(f"[publish] ERRO em {item.item_id} - pulando pro próximo item:")
            traceback.print_exc()
            falhas.append(item.item_id)

    if falhas:
        print(f"[publish] terminou com falha em: {', '.join(falhas)} (a próxima execução tenta de novo).")
        return 1
    print(f"[publish] {len(pendentes)} item(ns) processado(s) sem erro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
