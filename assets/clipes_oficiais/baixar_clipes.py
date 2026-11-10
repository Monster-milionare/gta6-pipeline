"""
Prepara os CLIPES DE VÍDEO de fundo a partir do material que a própria
Rockstar disponibiliza pra download na página oficial de mídia de GTA VI
(rockstargames.com/VI/media/videos - "Baixe e compartilhe trailers, imagens
e outros materiais"): Trailer 1, Trailer 2, Trailer de lançamento, "Um
Olhar Estendido", "Pré-carregue agora" e os videoclipes dos personagens.

Os arquivos originais são enormes (o Olhar Estendido tem 14 GB), então
NÃO baixamos nada inteiro: o ffmpeg lê direto da URL e pula até o ponto
pedido (requisição HTTP parcial), corta ~3,6s, tira o áudio e já salva em
dois formatos:
    <nome>_<nn>_h.mp4  -> 1920x1080 (vídeo longo)
    <nome>_<nn>_v.mp4  -> 1080x1920 (recorte central 9:16, pros shorts)
Trechos pretos/chapados (telas de logo, classificação etária, fade) são
descartados automaticamente.

O workflow guarda esta pasta em cache (actions/cache), então isso só roda
de verdade na primeira vez ou quando faltar clipe. Nunca derruba o
pipeline: se nada baixar, render.py usa os prints oficiais com movimento.

Uso: python assets/clipes_oficiais/baixar_clipes.py
"""
import json
import os
import subprocess
import sys
import time
import zipfile

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = "https://media-rockstargames-com.akamaized.net/VI/downloads/videos"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# (nome, url, quantos cortes, % do começo a pular, % do fim a pular)
FONTES = [
    ("Launch_Trailer", f"{BASE}/GTAVI_Launch_Trailer/GTAVI_Launch_Trailer.mp4", 26, 0.06, 0.10),
    ("Trailer_2", f"{BASE}/GTAVI_Trailer_2/GTAVI_Trailer_2.mp4", 26, 0.05, 0.08),
    ("Extended_Look", f"{BASE}/GTAVI_An_Extended_Look/GTAVI_An_Extended_Look.mp4", 44, 0.02, 0.04),
    ("Trailer_1", f"{BASE}/GTAVI_Trailer_1/GTAVI_Trailer_1.mp4", 14, 0.08, 0.10),
    ("Pre-Load", f"{BASE}/GTAVI_Pre-Load_Now/GTAVI_Pre-Load_Now.mp4", 5, 0.10, 0.25),
]
ZIP_PERSONAGENS = f"{BASE}/GTAVI_Videos.zip"
CORTES_POR_PERSONAGEM = 3

DUR_CORTE = 3.6
ORCAMENTO_SEG = int(os.environ.get("CLIPES_ORCAMENTO_SEG", "1200"))  # tempo máximo total gasto aqui
_inicio = time.time()


def _sobrou_tempo() -> bool:
    return time.time() - _inicio < ORCAMENTO_SEG


def _rodar(cmd: list, timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def _entrada(fonte: str) -> list:
    """Opções de entrada do ffmpeg/ffprobe (cabeçalho de navegador + reconexão pra URL)."""
    if fonte.startswith("http"):
        return ["-user_agent", UA, "-reconnect", "1", "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5"]
    return []


def _info(fonte: str) -> dict | None:
    r = _rodar(["ffprobe", "-v", "error", *_entrada(fonte), "-select_streams", "v:0",
                "-show_entries", "format=duration:stream=codec_name,width,height,pix_fmt,color_transfer",
                "-of", "json", fonte], 120)
    if r is None or r.returncode != 0:
        print(f"[clipes] ffprobe falhou em {fonte}: {(r.stderr.decode(errors='ignore')[-300:] if r else 'timeout')}")
        return None
    try:
        dados = json.loads(r.stdout)
        st = (dados.get("streams") or [{}])[0]
        return {"dur": float(dados["format"]["duration"]), **st}
    except Exception as exc:
        print(f"[clipes] não entendi o ffprobe de {fonte}: {exc}")
        return None


def _brilho(path: str) -> tuple[float, float]:
    """(média, variação) de luminosidade do meio do corte - detecta tela preta/chapada."""
    r = _rodar(["ffmpeg", "-v", "error", "-ss", "1.7", "-i", path, "-frames:v", "1",
                "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"], 60)
    if r is None or not r.stdout:
        return 0.0, 0.0
    px = r.stdout
    media = sum(px) / len(px)
    var = (sum((p - media) ** 2 for p in px) / len(px)) ** 0.5
    return media, var


def _cortar(fonte: str, t: float, base_saida: str, hdr: bool) -> bool:
    h_path, v_path = base_saida + "_h.mp4", base_saida + "_v.mp4"
    # HDR (PQ/HLG) ficaria lavado se só reduzisse - converte pra SDR
    tm = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable,"
          "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,") if hdr else ""
    filtro = (f"[0:v]{tm}fps=30,split=2[a][b];"
              "[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[h];"
              "[b]crop=ih*9/16:ih,scale=1080:1920,setsar=1[v]")
    comum = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]
    # -ss e -t ANTES do -i: valem pra entrada, então os dois arquivos saem com ~3,6s
    cmd = ["ffmpeg", "-v", "error", "-y", *_entrada(fonte), "-ss", f"{t:.2f}", "-t", f"{DUR_CORTE}",
           "-i", fonte, "-filter_complex", filtro,
           "-map", "[h]", *comum, h_path, "-map", "[v]", *comum, v_path]
    r = _rodar(cmd, 240)
    if hdr and (r is None or r.returncode != 0):
        # ffmpeg sem suporte ao filtro de HDR: melhor um clipe meio lavado que nenhum
        return _cortar(fonte, t, base_saida, False)
    ok = (r is not None and r.returncode == 0 and os.path.exists(h_path) and os.path.exists(v_path)
          and os.path.getsize(h_path) > 60_000 and os.path.getsize(v_path) > 60_000)
    if ok:
        media, var = _brilho(h_path)
        if media < 24 or var < 13:
            print(f"[clipes] descartado (tela escura/chapada, média {media:.0f}, variação {var:.0f}): "
                  f"{os.path.basename(base_saida)}")
            ok = False
    else:
        erro = r.stderr.decode(errors="ignore")[-240:] if r is not None else "timeout"
        print(f"[clipes] corte falhou em {os.path.basename(base_saida)} (t={t:.0f}s): {erro}")
    if not ok:
        for p in (h_path, v_path):
            if os.path.exists(p):
                os.remove(p)
    return ok


def _ja_tentados() -> set:
    path = os.path.join(OUT_DIR, "_tentados.txt")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {linha.strip() for linha in f if linha.strip()}


def _marcar_tentado(nome: str) -> None:
    with open(os.path.join(OUT_DIR, "_tentados.txt"), "a", encoding="utf-8") as f:
        f.write(nome + "\n")


def _processar_fonte(nome: str, fonte: str, n: int, pula_ini: float, pula_fim: float, tentados: set) -> int:
    faltam = [i for i in range(n)
              if f"{nome}_{i:02d}" not in tentados
              and not os.path.exists(os.path.join(OUT_DIR, f"{nome}_{i:02d}_h.mp4"))]
    if not faltam:
        return 0
    info = _info(fonte)
    if not info:
        return 0
    hdr = info.get("color_transfer") in ("smpte2084", "arib-std-b67")
    print(f"[clipes] {nome}: {info['dur']:.0f}s, {info.get('codec_name')} "
          f"{info.get('width')}x{info.get('height')} {info.get('pix_fmt')} "
          f"transfer={info.get('color_transfer')} -> {len(faltam)} cortes a fazer", flush=True)
    ini, fim = info["dur"] * pula_ini, info["dur"] * (1 - pula_fim) - DUR_CORTE
    if fim <= ini:
        return 0
    novos, falhas_seguidas = 0, 0
    for i in faltam:
        if not _sobrou_tempo():
            print("[clipes] orçamento de tempo esgotado - o resto fica pra próxima execução.")
            break
        if falhas_seguidas >= 4:
            print(f"[clipes] {nome}: muitas falhas seguidas, pulando esta fonte.")
            break
        # pontos espalhados por igual, com um desvio fixo por índice (sempre os mesmos)
        t = ini + (fim - ini) * (i + 0.5) / n + ((i * 37) % 11 - 5) * 0.35
        chave = f"{nome}_{i:02d}"
        if _cortar(fonte, max(ini, min(t, fim)), os.path.join(OUT_DIR, chave), hdr):
            novos += 1
            falhas_seguidas = 0
            print(f"[clipes] ok: {chave}", flush=True)
        else:
            falhas_seguidas += 1
        _marcar_tentado(chave)
    return novos


def _personagens(tentados: set) -> int:
    """Videoclipes dos personagens (ZIP de ~120 MB) -> alguns cortes de cada."""
    if "zip_personagens" in tentados or not _sobrou_tempo():
        return 0
    zip_path = os.path.join(OUT_DIR, "_personagens.zip")
    pasta = os.path.join(OUT_DIR, "_personagens")
    novos = 0
    try:
        import requests
        with requests.get(ZIP_PERSONAGENS, stream=True, timeout=60, headers={"User-Agent": UA}) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for pedaco in resp.iter_content(1 << 20):
                    f.write(pedaco)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(pasta)
        videos = []
        for raiz, _dirs, arquivos in os.walk(pasta):
            videos += [os.path.join(raiz, a) for a in arquivos if a.lower().endswith((".mp4", ".mov"))]
        print(f"[clipes] zip de personagens: {len(videos)} vídeos")
        for video in sorted(videos):
            nome = os.path.splitext(os.path.basename(video))[0].replace("GTAVI_", "").replace(" ", "_")
            novos += _processar_fonte(nome, video, CORTES_POR_PERSONAGEM, 0.05, 0.10, tentados)
        _marcar_tentado("zip_personagens")
    except Exception as exc:
        print(f"[clipes] aviso: zip de personagens falhou: {exc}")
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.isdir(pasta):
            import shutil
            shutil.rmtree(pasta, ignore_errors=True)
    return novos


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    tentados = _ja_tentados()
    antes = len([a for a in os.listdir(OUT_DIR) if a.endswith("_h.mp4")])
    novos = 0
    # 1ª passada pega um pouco de cada fonte (variedade logo de cara); 2ª completa
    for fracao in (0.4, 1.0):
        for (nome, url, n, p_ini, p_fim) in FONTES:
            if not _sobrou_tempo():
                break
            alvo = max(2, int(n * fracao))
            novos += _processar_fonte(nome, url, n, p_ini, p_fim,
                                      tentados | {f"{nome}_{i:02d}" for i in range(alvo, n)})
            tentados = _ja_tentados()
        if fracao < 1.0:
            novos += _personagens(tentados)
            tentados = _ja_tentados()
    total = len([a for a in os.listdir(OUT_DIR) if a.endswith("_h.mp4")])
    print(f"[clipes] {total} clipes oficiais prontos em {OUT_DIR} ({novos} novos, {antes} já existiam, "
          f"{time.time() - _inicio:.0f}s)")
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write(f"novos={'true' if novos else 'false'}\n")
            f.write(f"total={total}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # nunca derruba o pipeline
        print(f"[clipes] erro inesperado (seguindo sem clipes novos): {exc}")
        sys.exit(0)
