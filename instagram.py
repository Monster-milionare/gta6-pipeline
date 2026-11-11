#!/usr/bin/env python3
"""
Posta como Reels no Instagram os shorts que o publish.py acabou de subir no
YouTube (mesmo video vertical, sem custo extra de producao).

Roda como passo do workflow DEPOIS do publish.py, no mesmo job - e la que os
arquivos .mp4 renderizados ainda existem (assets/tmp). Se os secrets
IG_ACCESS_TOKEN / IG_USER_ID nao existirem, nao faz nada e termina em
silencio: o canal do YouTube nunca depende disso.

Fluxo (API de publicacao de conteudo do Instagram, upload resumivel - nao
precisa de URL publica pro video):
  1. cria o "container" do Reel e recebe o endereco de upload;
  2. envia o arquivo de video pra esse endereco;
  3. espera o Instagram processar (status FINISHED);
  4. publica o container.
O que ja foi postado fica em review/instagram_postados.txt (anti-duplicata).
Qualquer erro em um video e registrado e o proximo segue; este script
termina sempre com codigo 0.

Uso: python instagram.py
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import config
from content_batch import load_batch

GRAPH = "https://graph.facebook.com/v21.0"
POSTADOS = config.REVIEW_DIR / "instagram_postados.txt"
HASHTAGS = "#GTA6 #GTAVI #RockstarGames #Gaming #GTA"


def _ja_postados() -> set:
    if not POSTADOS.exists():
        return set()
    return {l.strip() for l in POSTADOS.read_text(encoding="utf-8").splitlines() if l.strip()}


def _legenda(item) -> str:
    if item.item_id.startswith("teoria-"):
        pedido = "Qual teoria voce acha mais certa? Comenta 1 ou 2! A mais votada vira video exclusivo."
    else:
        pedido = "Segue o perfil pra acompanhar tudo de GTA VI ate o lancamento (19/11/2026)."
    return f"{item.titulo}\n\n{pedido}\n\n{HASHTAGS}"[:2200]


def _erro(resp) -> str:
    try:
        return str(resp.json())[:300]
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"


def postar_reel(token: str, ig_id: str, video: Path, legenda: str) -> str:
    """Devolve o id da midia publicada ou levanta RuntimeError."""
    r = requests.post(f"{GRAPH}/{ig_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": legenda,
        "share_to_feed": "true", "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"criar container falhou: {_erro(r)}")
    dados = r.json()
    container, uri = dados["id"], dados.get("uri")
    if not uri:
        raise RuntimeError(f"Instagram nao devolveu endereco de upload: {dados}")

    tamanho = video.stat().st_size
    with open(video, "rb") as f:
        up = requests.post(uri, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tamanho)})
    if up.status_code != 200:
        raise RuntimeError(f"upload do video falhou: {_erro(up)}")

    status = ""
    for _ in range(40):                      # ate ~7 min
        time.sleep(10)
        s = requests.get(f"{GRAPH}/{container}", timeout=30,
                         params={"fields": "status_code,status", "access_token": token})
        if s.status_code == 200:
            status = s.json().get("status_code", "")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"processamento falhou: {s.json()}")
    if status != "FINISHED":
        raise RuntimeError(f"Instagram nao terminou de processar (ultimo status: {status or '?'})")

    p = requests.post(f"{GRAPH}/{ig_id}/media_publish", timeout=60,
                      data={"creation_id": container, "access_token": token})
    if p.status_code != 200:
        raise RuntimeError(f"publicar falhou: {_erro(p)}")
    return p.json().get("id", "?")


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    ig_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not ig_id:
        print("[instagram] IG_ACCESS_TOKEN/IG_USER_ID nao configurados - pulando (so YouTube).")
        return 0

    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    revisao = config.REVIEW_DIR / f"{hoje}.md"
    if not revisao.exists():
        print("[instagram] sem lote de hoje - nada a postar.")
        return 0
    batch = load_batch(revisao, hoje)
    feitos = _ja_postados()

    pendentes = []
    for item in batch.items:
        video = config.ASSETS_DIR / "tmp" / f"{item.item_id}.mp4"
        if item.kind == "short" and item.publicado and item.item_id not in feitos and video.exists():
            pendentes.append((item, video))
    if not pendentes:
        print("[instagram] nenhum short novo pra postar.")
        return 0

    # confere o token antes de gastar tempo com upload
    chk = requests.get(f"{GRAPH}/{ig_id}", timeout=30,
                       params={"fields": "username", "access_token": token})
    if chk.status_code != 200:
        print(f"[instagram] token/ID invalidos ou sem permissao: {_erro(chk)}")
        return 0
    print(f"[instagram] conta: @{chk.json().get('username', '?')} - {len(pendentes)} Reel(s) pra postar.")

    for n, (item, video) in enumerate(pendentes):
        if n:
            time.sleep(20)
        try:
            media = postar_reel(token, ig_id, video, _legenda(item))
        except Exception as exc:
            print(f"[instagram] {item.item_id}: ERRO - {str(exc)[:300]}", flush=True)
            continue
        with open(POSTADOS, "a", encoding="utf-8") as f:
            f.write(item.item_id + "\n")
        print(f"[instagram] {item.item_id} postado como Reel (id {media}).", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:        # nunca derruba o workflow
        print(f"[instagram] erro inesperado: {exc!r}")
        sys.exit(0)
