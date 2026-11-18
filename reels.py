#!/usr/bin/env python3
"""
Reels do Instagram, INDEPENDENTES do YouTube.

Por que separado: a cota do YouTube (6 envios/dia) nao vale pro Instagram, e
assim um lado nunca derruba o outro (token do YouTube vencido nao para os
Reels, erro no Instagram nao atrasa o YouTube).

O que posta:
  - EXTRAS: roteiros novos so pro Instagram (mesmo gerador/validador do canal,
    com o radar de noticias validadas), N por dia (padrao 5);
  - LOTE (--lote): shorts do lote do dia que ainda nao foram pro Instagram
    (rede de seguranca do passo de Instagram do publish.yml).

Cada Reel e renderizado e postado em seguida (o proprio tempo de render ja
espaca os posts em ~4 min, sem gastar minutos do Actions dormindo).
O que ja foi postado fica em review/reels/postados.txt (anti-duplicata, junto
com review/instagram_postados.txt do instagram.py). Termina sempre com 0.

Uso: python reels.py [--extras 5] [--alvo 5] [--lote]
  --extras N : quantos extras existem no dia (gera os que faltam)
  --alvo A   : posta ate ter A extras postados hoje (padrao = --extras)
"""
import argparse
import os
import subprocess
import sys
import time
import traceback
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import config
import instagram
import render as _render_mod
import unicidade
from content_batch import ContentItem, DailyBatch, load_batch, save_batch
from render import render_video
from tts import synthesize_sentences

FUSO = ZoneInfo("America/Sao_Paulo")
PASTA = config.REVIEW_DIR / "reels"
POSTADOS = PASTA / "postados.txt"
EXTRAS_POR_DIA = 3
MAX_FALHAS_SEGUIDAS = 2

HASHTAGS = ("#gta6 #gtavi #gta6brasil #rockstargames #gtavicity #games #gamer "
            "#noticiasgames #trailer #gta")
CTAS = [
    "Segue o perfil pra não perder nenhuma notícia de GTA VI até o lançamento.",
    "Segue a gente aqui no Instagram e compartilha com quem joga GTA.",
    "Quer ver tudo de GTA VI em primeira mão? Segue o perfil e ativa as notificações.",
    "Gostou? Segue o perfil e manda esse Reels pra um amigo que joga GTA.",
]


def _git(*args: str) -> int:
    return subprocess.run(["git", *args], check=False).returncode


def _salvar(msg: str) -> None:
    """Empurra review/reels/ pro repositorio (so dentro do Actions)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    try:
        _git("config", "user.name", "gta6-pipeline-bot")
        _git("config", "user.email", "actions@users.noreply.github.com")
        _git("add", "review/reels/")
        if _git("diff", "--cached", "--quiet") == 0:
            return
        _git("commit", "-m", msg)
        for tentativa in range(1, 6):
            if _git("push") == 0:
                return
            print(f"[reels] push rejeitado (tentativa {tentativa}/5) - rebase e tenta de novo", flush=True)
            _git("pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(5)
        print("[reels] AVISO: nao consegui salvar o status no repositorio.", flush=True)
    except Exception as exc:
        print(f"[reels] AVISO: erro ao salvar no git: {exc}", flush=True)


def _postados() -> set:
    feitos = set(instagram._ja_postados())
    if POSTADOS.exists():
        feitos |= {l.strip() for l in POSTADOS.read_text(encoding="utf-8").splitlines() if l.strip()}
    return feitos


def _marcar_postado(item_id: str) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    with open(POSTADOS, "a", encoding="utf-8") as f:
        f.write(item_id + "\n")


def _cta(item) -> str:
    return CTAS[sum(ord(c) for c in item.item_id) % len(CTAS)]


def _legenda(item) -> str:
    if item.item_id.startswith("teoria-"):
        pedido = "Qual teoria voce acha mais certa? Comenta 1 ou 2 e segue o perfil!"
    else:
        pedido = ("Segue @gta6brasil.hoje pra nao perder nada de GTA VI ate o lancamento "
                  "(19/11/2026). Compartilha com quem joga GTA!")
    return f"{item.titulo}\n\n{pedido}\n\n{HASHTAGS}"[:2200]


def _historico_completo(arquivo_de_hoje: Path) -> list:
    """Todo o historico do canal + todos os extras de outros dias."""
    historico = list(unicidade.carregar_historico())
    if PASTA.exists():
        for arq in sorted(PASTA.glob("extras-*.md")):
            if arq == arquivo_de_hoje:
                continue
            try:
                for it in load_batch(arq, arq.stem).items:
                    historico.append((it.item_id, it.titulo, it.roteiro))
            except Exception:
                continue
    return historico


def gerar_extras(date_str: str, quantos: int) -> list:
    """Garante quantos roteiros extras do dia (gera so os que faltam)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = PASTA / f"extras-{date_str}.md"
    itens = list(load_batch(arq, date_str).items) if arq.exists() else []
    if len(itens) >= quantos:
        return itens[:quantos]
    if not config.GROQ_API_KEY:
        print("[reels] GROQ_API_KEY ausente - nao da pra gerar extras novos.", flush=True)
        return itens

    import script_generator as sg
    from openai import OpenAI

    try:                                    # noticias validadas (radar) nos fatos/angulos
        import generate
        generate._ligar_radar()
    except Exception as exc:
        print(f"[reels] radar indisponivel ({exc!r}) - so fatos oficiais.", flush=True)

    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    fatos = sg._load_knowledge_base()
    historico = _historico_completo(arq)
    titulos_hist = [t for _i, t, _r in historico]
    aceitos = [(i.item_id, i.titulo, i.roteiro) for i in itens]
    desloc = date_cls.fromisoformat(date_str).toordinal()

    for n in range(len(itens), quantos):
        item_id = f"reel-{date_str}-{n + 1:02d}"
        angulo = sg.ANGULOS[(desloc + 3 + n * 7) % len(sg.ANGULOS)]
        motivo, recusados = None, []
        for tentativa in range(1, 6):
            proibidos = titulos_hist + [a[1] for a in aceitos] + recusados
            try:
                titulo, roteiro = sg._gerar_um(client, "short", fatos, proibidos, angulo, motivo, "short")
            except Exception as exc:
                print(f"[reels] {item_id}: falha ao gerar ({str(exc)[:160]}) - tentativa {tentativa}/5", flush=True)
                motivo = f"erro de geracao: {str(exc)[:80]}"
                continue
            recusa = sg._validar("short", titulo, roteiro, historico, aceitos, "short")
            if not recusa:
                aceitos.append((item_id, titulo, roteiro))
                itens.append(ContentItem(item_id=item_id, kind="short", titulo=titulo, roteiro=roteiro))
                save_batch(arq, DailyBatch(date=date_str, status="APROVADO", items=itens))
                print(f"[reels] {item_id} ok: {titulo}", flush=True)
                break
            print(f"[reels] {item_id} recusado ({recusa}) - tentativa {tentativa}/5", flush=True)
            recusados.append(titulo)
            motivo = recusa
        else:
            print(f"[reels] {item_id} DESCARTADO: {motivo}", flush=True)
    _salvar(f"chore: roteiros extras de Reels {date_str}")
    return itens


def renderizar_e_postar(item, token: str, ig_id: str) -> str:
    print(f"[reels] processando {item.item_id}: {item.titulo}", flush=True)
    audio_dir = config.ASSETS_DIR / "tmp" / "audio" / item.item_id
    segments = synthesize_sentences(item.roteiro, audio_dir)
    segments = segments + synthesize_sentences(_cta(item), audio_dir / "cta", cta=True)
    video = config.ASSETS_DIR / "tmp" / f"{item.item_id}.mp4"
    try:
        import estilos
        estilo = item.estilo or estilos.planejar_dia([(item.item_id, "short")], item.item_id)[0][0]
    except Exception:
        estilo = None
    render_video("short", item.titulo, segments, video, estilo)
    assert getattr(_render_mod, "ULTIMO_MOTOR", "motion") == "motion", "render caiu no motor classico (visual antigo) - nao postado"
    media = instagram.postar_reel(token, ig_id, video, _legenda(item))
    try:
        video.unlink()
    except Exception:
        pass
    return media


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extras", type=int, default=EXTRAS_POR_DIA)
    ap.add_argument("--alvo", type=int, default=None)
    ap.add_argument("--lote", action="store_true")
    args = ap.parse_args()
    alvo = args.extras if args.alvo is None else min(args.alvo, args.extras)

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    ig_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not ig_id:
        print("[reels] IG_ACCESS_TOKEN/IG_USER_ID nao configurados - nada a fazer.")
        return 0
    chk = requests.get(f"{instagram.GRAPH}/{ig_id}", timeout=30,
                       params={"fields": "username", "access_token": token})
    if chk.status_code != 200:
        print(f"[reels] token/ID invalidos ou sem permissao: {instagram._erro(chk)}")
        return 0
    print(f"[reels] conta: @{chk.json().get('username', '?')}", flush=True)

    hoje = datetime.now(FUSO).date().isoformat()
    feitos = _postados()
    fila = []

    if args.lote:                            # shorts do lote que ainda nao foram pro Instagram
        revisao = config.REVIEW_DIR / f"{hoje}.md"
        if revisao.exists():
            for it in load_batch(revisao, hoje).items:
                if it.kind == "short" and it.publicado and it.item_id not in feitos:
                    fila.append(it)
        print(f"[reels] shorts do lote pendentes no Instagram: {len(fila)}", flush=True)

    try:
        extras = gerar_extras(hoje, args.extras)
    except Exception:
        print("[reels] erro ao gerar extras (seguindo com o que ja existe):", flush=True)
        traceback.print_exc()
        extras = []
    ja_extras = sum(1 for e in extras if e.item_id in feitos)
    for e in extras:
        if ja_extras + sum(1 for x in fila if x.item_id.startswith("reel-")) >= alvo:
            break
        if e.item_id not in feitos:
            fila.append(e)

    print(f"[reels] fila: {len(fila)} Reel(s) ({', '.join(i.item_id for i in fila) or '-'})", flush=True)
    falhas = 0
    for item in fila:
        try:
            media = renderizar_e_postar(item, token, ig_id)
        except Exception as exc:
            falhas += 1
            print(f"[reels] {item.item_id}: ERRO - {str(exc)[:300]}", flush=True)
            traceback.print_exc()
            if falhas >= MAX_FALHAS_SEGUIDAS:
                print("[reels] muitas falhas seguidas - paro por agora (a proxima execucao tenta de novo).", flush=True)
                break
            continue
        falhas = 0
        _marcar_postado(item.item_id)
        _salvar(f"chore: {item.item_id} postado no Instagram")
        print(f"[reels] {item.item_id} postado como Reel (id {media}).", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                 # nunca derruba o workflow
        print(f"[reels] erro inesperado: {exc!r}")
        traceback.print_exc()
        sys.exit(0)
