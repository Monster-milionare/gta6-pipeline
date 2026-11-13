"""
Motor de vídeo "motion" (100% grátis: Python + Pillow + numpy + ffmpeg).

Substitui o slideshow antigo (que virou render_classico.py e continua aqui
só como plano B automático). Cada QUADRO do vídeo é montado em Python e
mandado pro ffmpeg, então tudo se mexe o tempo todo:

- FUNDO em vídeo: cortes rápidos de clipes OFICIAIS da Rockstar (baixados
  do próprio site de mídia deles - ver assets/clipes_oficiais/
  baixar_clipes.py), trocando a cada frase e a cada ~2,5s, com "soco" de
  zoom + flash em cada corte. O clipe é escolhido pelo assunto da frase
  (falou de Jason -> clipe do Jason). Sem clipe disponível, usa os prints
  oficiais com movimento de câmera (Ken Burns).
- LEGENDA palavra por palavra, gigante, sincronizada com a voz (tempos
  reais de cada palavra vindos do edge-tts), com "pop" de entrada e
  destaque amarelo nas palavras fortes.
- HUD no topo (estilo "DIA 1 - 09:12"): faltam X dias + contagem
  regressiva correndo de verdade até o lançamento + assunto atual.
- CARIMBOS que batem na tela com tremida quando a frase fala uma data,
  número, preço ou "confirmado/oficial" (só texto que está na própria
  frase - nada inventado).
- MASCOTE de corpo inteiro que entra andando, troca de lado, fala com a
  boca sincronizada, levanta a mão e aponta (ver mascote_anim.py).
- Cartão de título na abertura, botão animado de like/inscrição no CTA,
  efeitos sonoros sintetizados (whoosh/impacto) e trilha de fundo.

Se QUALQUER coisa aqui falhar, render_video cai sozinho pro motor
clássico - um erro de edição nunca impede o vídeo do dia de sair.
"""
import math
import random
import re
import subprocess
import traceback
import wave
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config
import mascote_anim

FPS = 30
SR = 44100
RESOLUTIONS = {"long": (1920, 1080), "short": (1080, 1920)}

FUSO = ZoneInfo("America/Sao_Paulo")
LANCAMENTO = datetime(2026, 11, 19, 0, 0, tzinfo=FUSO)

AMARELO = (255, 208, 20)
BRANCO = (255, 255, 255)
PRETO = (12, 10, 16)
VERMELHO = (232, 48, 42)

FONTE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
FONTES_RESERVA = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

MUSICA_VOLUME = 0.11
PAUSA_FRASE = 0.14          # respiro entre frases (s)
CORTE_MAX = 2.6             # nenhum plano de fundo dura mais que isso (s)
PLANO_MAX = 3.3             # os clipes têm ~3.6s

# assunto da frase -> (palavras no texto, pedaços de nome de arquivo, rótulo do HUD)
TEMAS = [
    (("jason",), ("Jason",), "JASON DUVAL"),
    (("lucia", "lúcia"), ("Lucia",), "LUCIA CAMINOS"),
    (("vice city",), ("Vice_City",), "VICE CITY"),
    (("keys",), ("Leonida_Keys",), "LEONIDA KEYS"),
    (("grassrivers",), ("Grassrivers",), "GRASSRIVERS"),
    (("port gellhorn",), ("Port_Gellhorn",), "PORT GELLHORN"),
    (("ambrosia",), ("Ambrosia",), "AMBROSIA"),
    (("kalaga",), ("Mount_Kalaga",), "MOUNT KALAGA"),
    (("cal hampton",), ("Cal_Hampton",), "CAL HAMPTON"),
    (("boobie",), ("Boobie_Ike",), "BOOBIE IKE"),
    (("dre'quan", "drequan"), ("DreQuan",), "DRE'QUAN PRIEST"),
    (("real dimez",), ("Real_Dimez",), "REAL DIMEZ"),
    (("raul",), ("Raul_Bautista",), "RAUL BAUTISTA"),
    (("brian",), ("Brian_Heder",), "BRIAN HEDER"),
    (("pré-carga", "pre-carga", "pré carga", "pre-load"), ("Pre-Load",), "PRÉ-CARGA"),
    (("trailer",), ("Trailer",), "TRAILER"),
    (("leonida",), ("Leonida", "Grassrivers", "Ambrosia", "Vice_City"), "LEONIDA"),
    (("mapa",), (), "MAPA"),
    (("preço", "r$"), (), "PREÇO"),
    (("online",), (), "GTA ONLINE"),
    (("ps5", "playstation"), (), "PLAYSTATION 5"),
    (("xbox",), (), "XBOX SERIES"),
    (("rockstar",), (), "ROCKSTAR GAMES"),
    (("lançamento",), (), "LANÇAMENTO"),
]
ROTULO_PADRAO = "GTA VI BRASIL"

PALAVRAS_FORTES = {
    "gta", "vi", "rockstar", "leonida", "vice", "city", "jason", "lucia", "oficial",
    "oficialmente", "confirmado", "confirmada", "confirmou", "lançamento", "nunca",
    "maior", "primeira", "primeiro", "novo", "nova", "grátis", "trailer", "mapa",
    "agora", "hoje", "amanhã", "pré-carga", "online", "milhões", "bilhões", "recorde",
    "atenção", "cuidado", "segredo", "detalhe", "história", "roubo", "polícia",
}
MESES = "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
_RE_CARIMBOS = [
    re.compile(rf"\b(\d{{1,2}})\s+de\s+({MESES})(?:\s+de\s+(\d{{4}}))?", re.I),
    re.compile(r"R\$\s?\d[\d\.,]*", re.I),
    re.compile(r"\b\d[\d\.,]*\s?%"),
    re.compile(r"\b\d[\d\.,]*\s?(?:GB|gigas|mil|milhões|milhão|bilhões|bilhão|horas|dias|anos|fps|missões|cidades)\b", re.I),
]
_CARIMBOS_PALAVRA = [("confirmad", "CONFIRMADO"), ("oficial", "OFICIAL"), ("exclusiv", "EXCLUSIVO"), ("recorde", "RECORDE")]


# ------------------------------------------------------------------ utilidades

_TRACOS = {c: "-" for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014)}


def _limpa(txt: str) -> str:
    """Troca travessões/hífens especiais (o roteiro vem com eles) por "-" comum."""
    return txt.translate(_TRACOS)


def _ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _ease_back(x: float) -> float:
    """Passa um pouco do alvo e volta (efeito 'pop')."""
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _garantir_fonte() -> str | None:
    destino = config.ASSETS_DIR / "fontes" / "Anton-Regular.ttf"
    if destino.exists() and destino.stat().st_size > 20_000:
        return str(destino)
    try:
        import requests
        destino.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(FONTE_URL, timeout=20)
        resp.raise_for_status()
        destino.write_bytes(resp.content)
        return str(destino)
    except Exception as exc:
        print(f"[render] aviso: não baixei a fonte Anton ({exc}) - usando fonte reserva.")
    for caminho in FONTES_RESERVA:
        if Path(caminho).exists():
            return caminho
    return None


_FONTE_PATH: list = []


@lru_cache(maxsize=64)
def _fonte(tam: int) -> ImageFont.FreeTypeFont:
    if not _FONTE_PATH:
        _FONTE_PATH.append(_garantir_fonte())
    if _FONTE_PATH[0]:
        return ImageFont.truetype(_FONTE_PATH[0], tam)
    return ImageFont.load_default()


def _texto_sprite(texto: str, tam: int, cor, contorno: int, max_w: int | None = None,
                  sombra: bool = True) -> Image.Image:
    """Texto com contorno grosso + sombra, em RGBA recortado justo."""
    fonte = _fonte(tam)
    medida = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    while max_w and tam > 24 and medida.textlength(texto, font=fonte) + 2 * contorno > max_w:
        tam = int(tam * 0.92)
        fonte = _fonte(tam)
    x0, y0, x1, y1 = medida.textbbox((0, 0), texto, font=fonte, stroke_width=contorno)
    desloc = max(3, tam // 14) if sombra else 0
    img = Image.new("RGBA", (x1 - x0 + desloc + 4, y1 - y0 + desloc + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if sombra:
        d.text((2 - x0 + desloc, 2 - y0 + desloc), texto, font=fonte, fill=(0, 0, 0, 150),
               stroke_width=contorno, stroke_fill=(0, 0, 0, 150))
    d.text((2 - x0, 2 - y0), texto, font=fonte, fill=cor, stroke_width=contorno, stroke_fill=PRETO)
    return img


def _colar(base: Image.Image, sprite: Image.Image, cx: float, cy: float, escala: float = 1.0,
           alfa: float = 1.0) -> None:
    """Cola `sprite` centralizado em (cx, cy), com escala/transparência opcionais."""
    if escala != 1.0:
        w, h = max(1, int(sprite.width * escala)), max(1, int(sprite.height * escala))
        sprite = sprite.resize((w, h), Image.BILINEAR)
    if alfa < 1.0:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * max(alfa, 0.0))))
    base.paste(sprite, (int(cx - sprite.width / 2), int(cy - sprite.height / 2)), sprite)


def _tema(texto: str):
    baixo = _limpa(texto).lower()
    for chaves, arquivos, rotulo in TEMAS:
        if any(c in baixo for c in chaves):
            return arquivos, rotulo
    return (), None


# ------------------------------------------------------------------ áudio

def _decodificar(path: Path) -> np.ndarray:
    bruto = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def _aparar(audio: np.ndarray) -> tuple[np.ndarray, float]:
    """Tira o silêncio do começo/fim da frase (deixa o ritmo mais apertado).
    Retorna (áudio aparado, segundos removidos do começo)."""
    if audio.size == 0:
        return audio, 0.0
    forte = np.flatnonzero(np.abs(audio) > 0.012)
    if forte.size == 0:
        return audio, 0.0
    ini = max(0, int(forte[0]) - int(0.03 * SR))
    fim = min(audio.size, int(forte[-1]) + int(0.10 * SR))
    return audio[ini:fim], ini / SR


def _whoosh(dur: float = 0.34) -> np.ndarray:
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    ruido = rng.standard_normal(n).astype(np.float32)
    suave = np.convolve(ruido, np.ones(28, dtype=np.float32) / 28, mode="same")
    agudo = ruido - np.convolve(ruido, np.ones(6, dtype=np.float32) / 6, mode="same")
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.sin(np.pi * t) ** 2
    return (suave * (1 - t) * 2.2 + agudo * t * 0.35) * env


def _impacto(dur: float = 0.42) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 95 * np.exp(-t * 9) + 42
    fase = 2 * np.pi * np.cumsum(freq) / SR
    grave = np.sin(fase) * np.exp(-t * 9)
    rng = np.random.default_rng(3)
    clique = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 90) * 0.5
    return (grave + clique).astype(np.float32)


def _pop(dur: float = 0.09) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 700 + 900 * t / dur
    return (np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 30)).astype(np.float32)


def _somar(base: np.ndarray, som: np.ndarray, t: float, vol: float) -> None:
    i = int(t * SR)
    if i >= base.size:
        return
    trecho = som[: base.size - i]
    base[i:i + trecho.size] += trecho * vol


def _musica(total: int) -> np.ndarray | None:
    pasta = config.ASSETS_DIR / "musica"
    faixas = sorted(pasta.glob("*.wav")) + sorted(pasta.glob("*.mp3"))
    if not faixas:
        return None
    try:
        faixa = _decodificar(random.choice(faixas))
    except Exception:
        return None
    if faixa.size < SR:
        return None
    voltas = int(math.ceil(total / faixa.size))
    trilha = np.tile(faixa, voltas)[:total].copy()
    rampa = min(int(1.2 * SR), total // 4)
    trilha[:rampa] *= np.linspace(0, 1, rampa, dtype=np.float32)
    trilha[-rampa:] *= np.linspace(1, 0, rampa, dtype=np.float32)
    return trilha


# ------------------------------------------------------------------ linha do tempo

@dataclass
class Fala:
    texto: str
    t0: float
    t1: float
    palavras: list          # [(palavra, t0, t1)] em tempo absoluto do vídeo
    cta: bool = False
    energica: bool = False


@dataclass
class Bloco:                # 1 "cartão" de legenda (1-3 palavras)
    texto: str
    t0: float
    t1: float
    forte: bool = False


@dataclass
class Carimbo:
    texto: str
    t0: float
    dur: float = 1.9


@dataclass
class Plano:                # 1 trecho de fundo
    t0: float
    t1: float
    tags: tuple = ()
    forte: bool = False     # corte de início de frase (ganha soco de zoom + flash)


def _palavras_estimadas(texto: str, dur: float) -> list:
    tokens = [t for t in _limpa(texto).split() if t]
    if not tokens:
        return []
    pesos = [len(t) + 2 for t in tokens]
    total = float(sum(pesos))
    util = max(dur - 0.12, 0.2)
    saida, t = [], 0.04
    for tok, peso in zip(tokens, pesos):
        d = util * peso / total
        saida.append((tok.strip(".,;:!?\"()"), t, t + d * 0.92))
        t += d
    return saida


def _montar_falas(segments) -> tuple[list, np.ndarray]:
    falas, pedacos, t = [], [], 0.0
    for seg in segments:
        audio, corte_ini = _aparar(_decodificar(seg.audio_path))
        dur = audio.size / SR
        brutas = list(getattr(seg, "words", None) or [])
        palavras = []
        for (p, a, b) in brutas:
            a, b = a - corte_ini, b - corte_ini
            if b <= 0 or a >= dur:
                continue
            palavras.append((_limpa(p), t + max(a, 0.0), t + min(b, dur)))
        if not palavras:
            palavras = [(p, t + a, t + b) for (p, a, b) in _palavras_estimadas(seg.text, dur)]
        energica = bool(getattr(seg, "energica", False)) or seg.text.rstrip().endswith(("!", "?"))
        falas.append(Fala(seg.text, t, t + dur, palavras, cta=bool(seg.is_cta), energica=energica))
        pausa = np.zeros(int(PAUSA_FRASE * SR), dtype=np.float32)
        pedacos += [audio, pausa]
        t += dur + pausa.size / SR
    return falas, np.concatenate(pedacos) if pedacos else np.zeros(SR, dtype=np.float32)


def _montar_blocos(falas) -> list:
    blocos = []
    for fala in falas:
        grupos, atual = [], []
        for pal in fala.palavras:
            texto_atual = " ".join(p[0] for p in atual)
            curto = all(len(p[0]) <= 3 for p in atual)
            if atual and curto and len(atual) < 3 and len(texto_atual) + 1 + len(pal[0]) <= 15:
                atual.append(pal)
            else:
                if atual:
                    grupos.append(atual)
                atual = [pal]
        if atual:
            grupos.append(atual)
        for i, g in enumerate(grupos):
            fim = grupos[i + 1][0][1] if i + 1 < len(grupos) else min(g[-1][2] + 0.2, fala.t1 + PAUSA_FRASE)
            texto = " ".join(p[0] for p in g).upper()
            nucleo = [re.sub(r"[^\wáàâãéêíóôõúç-]", "", p[0].lower()) for p in g]
            forte = any(ch.isdigit() for ch in texto) or any(n in PALAVRAS_FORTES for n in nucleo)
            if fala.energica and i == len(grupos) - 1:
                forte = True
            blocos.append(Bloco(texto, g[0][1], max(fim, g[0][1] + 0.12), forte))
    return blocos


def _montar_carimbos(falas, inicio_minimo: float) -> list:
    carimbos, ultimo = [], -99.0
    for fala in falas:
        if fala.cta:
            continue
        texto = _limpa(fala.texto)
        achado, alvo = None, None
        for rx in _RE_CARIMBOS:
            m = rx.search(texto)
            if m:
                achado, alvo = m.group(0).upper(), m.group(0).split()[0].lower()
                break
        if not achado:
            for raiz, rotulo in _CARIMBOS_PALAVRA:
                if raiz in texto.lower():
                    achado, alvo = rotulo, raiz
                    break
        if not achado:
            continue
        quando = fala.t0 + 0.25
        for (p, a, _b) in fala.palavras:
            if p.lower().startswith(alvo[:5]):
                quando = a
                break
        quando = max(quando, inicio_minimo)
        if quando - ultimo < 3.2 or quando > fala.t1 + 0.4:
            continue
        carimbos.append(Carimbo(re.sub(r"\s+", " ", achado), quando))
        ultimo = quando
    return carimbos


def _montar_planos(falas, total: float) -> list:
    planos = []
    for i, fala in enumerate(falas):
        fim = falas[i + 1].t0 if i + 1 < len(falas) else total
        tags, _rot = _tema(fala.texto)
        cortes = [fala.t0 if i else 0.0]
        inicios = [p[1] for p in fala.palavras]
        while fim - cortes[-1] > PLANO_MAX:
            alvo = cortes[-1] + CORTE_MAX
            perto = [x for x in inicios if abs(x - alvo) < 0.6 and x > cortes[-1] + 1.2]
            cortes.append(min(perto, key=lambda x: abs(x - alvo)) if perto else alvo)
        for j, c in enumerate(cortes):
            prox = cortes[j + 1] if j + 1 < len(cortes) else fim
            planos.append(Plano(c, prox, tags, forte=(j == 0 and i > 0)))
    return planos


# ------------------------------------------------------------------ fundo

class Fundo:
    """Entrega o quadro de fundo n. Clipes oficiais em vídeo quando existem;
    prints oficiais com movimento de câmera quando não."""

    def __init__(self, kind: str, w: int, h: int, planos: list, rng: random.Random):
        self.w, self.h, self.planos, self.rng = w, h, planos, rng
        sufixo = "_h.mp4" if kind == "long" else "_v.mp4"
        self.clipes = sorted((config.ASSETS_DIR / "clipes_oficiais").glob(f"*{sufixo}"))
        pasta = config.ASSETS_DIR / "broll_oficial"
        self.fotos = sorted(pasta.glob("*.jpg")) + sorted(pasta.glob("*.png"))
        self.recentes: list = []
        self.i = -1
        self.proc = None
        self.foto = None
        self.ultimo = Image.new("RGB", (w, h), (16, 14, 24))
        self.n_plano = 0
        self.frames_plano = 1
        print(f"[render] fundo: {len(self.clipes)} clipes oficiais, {len(self.fotos)} prints oficiais")

    def _escolher(self, plano: Plano):
        def com_tag(lista):
            return [p for p in lista if any(tag.lower() in p.name.lower() for tag in plano.tags)]
        candidatos = []
        if plano.tags:
            candidatos = com_tag(self.clipes) or com_tag(self.fotos)
        if not candidatos:
            usar_foto = bool(self.fotos) and (not self.clipes or self.rng.random() < 0.12)
            candidatos = self.fotos if usar_foto else self.clipes
        if not candidatos:
            return None
        livres = [c for c in candidatos if c not in self.recentes] or candidatos
        escolha = self.rng.choice(livres)
        self.recentes = (self.recentes + [escolha])[-14:]
        return escolha

    def _fechar(self):
        if self.proc is not None:
            try:
                self.proc.stdout.close()
                self.proc.kill()
                self.proc.wait(timeout=5)
            except Exception:
                pass
            self.proc = None
        self.foto = None

    def _abrir(self, plano: Plano):
        self._fechar()
        dur = plano.t1 - plano.t0
        self.frames_plano = max(1, int(round(dur * FPS)))
        self.n_plano = 0
        fonte = self._escolher(plano)
        if fonte is None:
            return
        if fonte.suffix.lower() == ".mp4":
            folga = max(0.0, 3.5 - dur - 0.1)
            inicio = self.rng.uniform(0, folga) if folga > 0 else 0.0
            self.proc = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-ss", f"{inicio:.2f}", "-i", str(fonte),
                 "-vf", f"fps={FPS},scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
                        f"crop={self.w}:{self.h}",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        else:
            try:
                img = Image.open(fonte).convert("RGB")
            except Exception:
                return
            # cobre o quadro com sobra de 22% pra câmera poder andar
            alvo_w, alvo_h = int(self.w * 1.22), int(self.h * 1.22)
            escala = max(alvo_w / img.width, alvo_h / img.height)
            img = img.resize((int(img.width * escala) + 1, int(img.height * escala) + 1), Image.BILINEAR)
            self.foto = (img, self.rng.choice([(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]),
                         self.rng.random() < 0.5)

    def _quadro_foto(self) -> Image.Image:
        img, (dx, dy), aproxima = self.foto
        p = self.n_plano / max(1, self.frames_plano - 1)
        zoom = 1.0 + 0.16 * (p if aproxima else 1 - p)
        cw, ch = self.w * 1.04 / zoom * 1.0, self.h * 1.04 / zoom * 1.0
        sobra_x, sobra_y = img.width - cw, img.height - ch
        cx = sobra_x / 2 + dx * sobra_x * 0.45 * (p - 0.5) * 2
        cy = sobra_y / 2 + dy * sobra_y * 0.45 * (p - 0.5) * 2
        return img.resize((self.w, self.h), Image.BILINEAR, box=(cx, cy, cx + cw, cy + ch))

    def frame(self, t: float) -> tuple[Image.Image, int, bool]:
        """Retorna (quadro, nº do quadro dentro do plano, se o plano é corte forte)."""
        while self.i + 1 < len(self.planos) and t >= self.planos[self.i + 1].t0 - 1e-6:
            self.i += 1
            self._abrir(self.planos[self.i])
        forte = self.planos[self.i].forte if self.i >= 0 else False
        img = None
        if self.proc is not None:
            dados = self.proc.stdout.read(self.w * self.h * 3)
            if len(dados) == self.w * self.h * 3:
                img = Image.frombytes("RGB", (self.w, self.h), dados)
        elif self.foto is not None:
            img = self._quadro_foto()
        if img is None:
            img = self.ultimo.copy()
        else:
            self.ultimo = img.copy()   # os overlays são desenhados em cima de `img`
        n = self.n_plano
        self.n_plano += 1
        return img, n, forte


def _degrade(w: int, h: int, de_baixo: bool, forca: int) -> Image.Image:
    col = np.linspace(0, 1, h, dtype=np.float32) ** 1.6
    if not de_baixo:
        col = col[::-1]
    alfa = np.repeat((col * forca).astype(np.uint8)[:, None], w, axis=1)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.putalpha(Image.fromarray(alfa))
    return img


# ------------------------------------------------------------------ elementos de tela

def _caixa(w: int, h: int, cor, raio: int) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=raio, fill=cor)
    return img


class Hud:
    """Faixa do topo: [FALTAM X DIAS] - GTA VI / assunto atual / contagem regressiva."""

    def __init__(self, kind: str, w: int, h: int, falas: list):
        self.w, self.h = w, h
        self.u = (w if kind == "short" else h) / 1080  # unidade de escala
        self.topo = int(h * (0.075 if kind == "short" else 0.045))
        self.margem = int(w * 0.045)
        self.agora = datetime.now(FUSO)
        dias = (LANCAMENTO.date() - self.agora.date()).days
        if dias > 1:
            chip = f"FALTAM {dias} DIAS"
        elif dias == 1:
            chip = "FALTA 1 DIA"
        elif dias == 0:
            chip = "É HOJE"
        else:
            chip = f"DIA {-dias + 1}"
        self.pos_lancamento = self.agora >= LANCAMENTO
        u = self.u
        txt = _texto_sprite(chip, int(46 * u), PRETO, 0, sombra=False)
        self.chip = _caixa(txt.width + int(30 * u), int(72 * u), AMARELO + (255,), int(10 * u))
        self.chip.alpha_composite(txt, (int(15 * u), (self.chip.height - txt.height) // 2))
        self.marca = _texto_sprite("GTA VI", int(46 * u), BRANCO, int(3 * u))
        self.ponto = int(9 * u)
        # assunto ao longo do tempo
        self.assuntos = [(0.0, ROTULO_PADRAO)]
        for fala in falas:
            _tags, rot = _tema(fala.texto)
            if rot and rot != self.assuntos[-1][1]:
                self.assuntos.append((fala.t0, rot))
        self._cache_assunto: dict = {}
        self._cache_relogio: dict = {}
        self.rotulo_relogio = _texto_sprite("JÁ DISPONÍVEL HÁ" if self.pos_lancamento else "LANÇAMENTO EM",
                                            int(24 * u), (190, 190, 200), 0, sombra=False)

    def _assunto(self, rotulo: str) -> Image.Image:
        if rotulo not in self._cache_assunto:
            u = self.u
            txt = _texto_sprite(rotulo, int(30 * u), (24, 22, 30), 0, sombra=False)
            cx = _caixa(txt.width + int(26 * u), int(46 * u), (236, 236, 240, 240), int(6 * u))
            cx.alpha_composite(txt, (int(13 * u), (cx.height - txt.height) // 2))
            self._cache_assunto[rotulo] = cx
        return self._cache_assunto[rotulo]

    def _relogio(self, t: float) -> Image.Image:
        momento = self.agora + timedelta(seconds=t)
        delta = (momento - LANCAMENTO) if self.pos_lancamento else (LANCAMENTO - momento)
        seg = max(0, int(delta.total_seconds()))
        texto = f"{seg // 86400}D {seg % 86400 // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
        if texto not in self._cache_relogio:
            u = self.u
            dig = _texto_sprite(texto, int(50 * u), VERMELHO, 0, sombra=False)
            larg = max(dig.width, self.rotulo_relogio.width) + int(32 * u)
            cx = _caixa(larg, int(112 * u), (14, 12, 20, 225), int(10 * u))
            ImageDraw.Draw(cx).rounded_rectangle([0, 0, larg - 1, cx.height - 1], radius=int(10 * u),
                                                 outline=VERMELHO + (255,), width=max(2, int(3 * u)))
            cx.alpha_composite(self.rotulo_relogio, ((larg - self.rotulo_relogio.width) // 2, int(10 * u)))
            cx.alpha_composite(dig, ((larg - dig.width) // 2, int(44 * u)))
            if len(self._cache_relogio) > 8:
                self._cache_relogio.clear()
            self._cache_relogio[texto] = cx
        return self._cache_relogio[texto]

    def desenhar(self, frame: Image.Image, t: float) -> None:
        u = self.u
        entra = _ease_out(t / 0.35)
        desliza = int((1 - entra) * -80 * u)
        x, y = self.margem, self.topo + desliza
        frame.paste(self.chip, (x, y), self.chip)
        px = x + self.chip.width + int(18 * u)
        # ponto vermelho piscando (tipo "gravando")
        if int(t * 2) % 2 == 0:
            ImageDraw.Draw(frame).ellipse([px, y + self.chip.height // 2 - self.ponto,
                                           px + 2 * self.ponto, y + self.chip.height // 2 + self.ponto],
                                          fill=VERMELHO)
        frame.paste(self.marca, (px + 3 * self.ponto, y + (self.chip.height - self.marca.height) // 2), self.marca)
        # assunto atual (desliza quando muda)
        atual, desde = ROTULO_PADRAO, 0.0
        for (ta, rot) in self.assuntos:
            if ta <= t:
                atual, desde = rot, ta
        spr = self._assunto(atual)
        anda = _ease_out((t - desde) / 0.22)
        frame.paste(spr, (x + int((1 - anda) * -50 * u), y + self.chip.height + int(10 * u)), spr)
        rel = self._relogio(t)
        frame.paste(rel, (self.w - self.margem - rel.width, y), rel)


class Legendas:
    def __init__(self, kind: str, w: int, h: int, blocos: list):
        self.blocos, self.w, self.h = blocos, w, h
        self.cy = h * (0.545 if kind == "short" else 0.80)
        self.tam = int(h * (0.066 if kind == "short" else 0.105))
        self.max_w = int(w * (0.88 if kind == "short" else 0.56))
        self.i = 0
        self._cache: dict = {}

    def desenhar(self, frame: Image.Image, t: float) -> None:
        while self.i + 1 < len(self.blocos) and t >= self.blocos[self.i + 1].t0:
            self.i += 1
        if not self.blocos:
            return
        b = self.blocos[self.i]
        if not (b.t0 <= t < b.t1):
            return
        if self.i not in self._cache:
            spr = _texto_sprite(
                b.texto, int(self.tam * (1.16 if b.forte else 1.0)), AMARELO if b.forte else BRANCO,
                max(6, self.tam // 9), self.max_w)
            if b.forte:   # palavra forte entra levemente torta (mais "viva")
                spr = spr.rotate(3 if self.i % 2 else -3, expand=True, resample=Image.BICUBIC)
            self._cache = {self.i: spr}
        idade = t - b.t0
        escala = 0.62 + 0.38 * _ease_back(idade / 0.13) if idade < 0.13 else 1.0
        _colar(frame, self._cache[self.i], self.w / 2, self.cy, escala)


class Carimbos:
    def __init__(self, kind: str, w: int, h: int, carimbos: list, rng: random.Random):
        self.itens, self.w, self.h = carimbos, w, h
        self.cx = w * (0.5 if kind == "short" else 0.70)
        self.cy = h * (0.335 if kind == "short" else 0.38)
        u = (w if kind == "short" else h) / 1080
        self.sprites = []
        for c in carimbos:
            txt = _texto_sprite(c.texto, int(150 * u), VERMELHO, 0, int(w * (0.72 if kind == "short" else 0.40)),
                                sombra=False)
            borda, folga = int(14 * u), int(34 * u)
            cx = Image.new("RGBA", (txt.width + 2 * folga, txt.height + 2 * folga), (0, 0, 0, 0))
            d = ImageDraw.Draw(cx)
            d.rounded_rectangle([0, 0, cx.width - 1, cx.height - 1], radius=int(26 * u),
                                fill=(255, 255, 255, 235), outline=VERMELHO + (255,), width=borda)
            cx.alpha_composite(txt, (folga, folga))
            self.sprites.append(cx.rotate(rng.choice([-9, -7, 7, 9]), expand=True, resample=Image.BICUBIC))

    def tremor(self, t: float) -> tuple[int, int]:
        for c in self.itens:
            idade = t - c.t0
            if 0.12 <= idade < 0.30:
                k = int(idade * FPS)
                return ((11 if k % 2 else -11), (7 if k % 3 else -7))
        return (0, 0)

    def ativo(self, t: float) -> bool:
        return any(c.t0 <= t < c.t0 + c.dur for c in self.itens)

    def desenhar(self, frame: Image.Image, t: float) -> None:
        for c, spr in zip(self.itens, self.sprites):
            idade = t - c.t0
            if not (0 <= idade < c.dur):
                continue
            if idade < 0.12:        # vem de longe e "bate" na tela
                escala, alfa = 2.6 - 1.6 * (idade / 0.12) ** 2, min(1.0, idade / 0.06)
            elif idade < 0.20:
                escala, alfa = 0.94 + 0.06 * ((idade - 0.12) / 0.08), 1.0
            else:
                escala, alfa = 1.0, 1.0
            if idade > c.dur - 0.22:
                alfa = max(0.0, (c.dur - idade) / 0.22)
            _colar(frame, spr, self.cx, self.cy, escala, alfa)


class Titulo:
    """Cartão com o título do vídeo nos primeiros segundos."""

    DUR = 2.5

    def __init__(self, kind: str, w: int, h: int, titulo: str):
        self.w, self.h = w, h
        u = (w if kind == "short" else h) / 1080
        larg = int(w * (0.84 if kind == "short" else 0.50))
        fonte = _fonte(int(68 * u))
        medida = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        linhas, atual = [], ""
        for palavra in _limpa(titulo).upper().split():
            tentativa = f"{atual} {palavra}".strip()
            if medida.textlength(tentativa, font=fonte) <= larg - int(80 * u) or not atual:
                atual = tentativa
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
        linhas = linhas[:4]
        alt_linha = int(84 * u)
        cx = _caixa(larg, alt_linha * len(linhas) + int(44 * u), (14, 12, 20, 232), int(18 * u))
        d = ImageDraw.Draw(cx)
        d.rounded_rectangle([0, 0, int(16 * u), cx.height - 1], radius=int(8 * u), fill=AMARELO + (255,))
        for i, linha in enumerate(linhas):
            cor = AMARELO if i == 0 else BRANCO
            d.text((int(44 * u), int(16 * u) + i * alt_linha), linha, font=fonte, fill=cor)
        self.sprite = cx
        self.cx = w * (0.5 if kind == "short" else 0.30)
        self.cy = h * (0.30 if kind == "short" else 0.36)

    def desenhar(self, frame: Image.Image, t: float) -> None:
        if t >= self.DUR:
            return
        if t < 0.3:
            dx = (1 - _ease_back(t / 0.3)) * -self.w * 0.9
        elif t > self.DUR - 0.25:
            dx = -((t - (self.DUR - 0.25)) / 0.25) ** 2 * self.w
        else:
            dx = 0
        _colar(frame, self.sprite, self.cx + dx, self.cy)


class BotaoCta:
    """Botões animados de CURTIR / INSCREVA-SE (formas próprias, sem logo do YouTube)."""

    def __init__(self, kind: str, w: int, h: int, falas: list):
        self.t0 = next((f.t0 for f in falas if f.cta), None)
        self.cx = w * (0.5 if kind == "short" else 0.70)
        self.cy = h * (0.335 if kind == "short" else 0.38)
        if self.t0 is None:
            return
        u = (w if kind == "short" else h) / 1080
        self.antes = self._montar(u, "INSCREVA-SE", VERMELHO, BRANCO)
        self.depois = self._montar(u, "INSCRITO", (70, 70, 80), BRANCO, marcado=True)

    @staticmethod
    def _montar(u: float, texto: str, cor, cor_texto, marcado: bool = False) -> Image.Image:
        larg, alt = int(640 * u), int(330 * u)
        img = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # pílula de CURTIR
        d.rounded_rectangle([int(90 * u), 0, larg - int(90 * u), int(140 * u)], radius=int(70 * u),
                            fill=(250, 250, 255, 245), outline=PRETO + (255,), width=int(6 * u))
        px, py = int(150 * u), int(38 * u)
        cor_mao = (40, 110, 255) if marcado else (30, 28, 36)
        d.rounded_rectangle([px, py + int(26 * u), px + int(18 * u), py + int(70 * u)], radius=int(5 * u), fill=cor_mao)
        d.rounded_rectangle([px + int(24 * u), py + int(22 * u), px + int(78 * u), py + int(70 * u)],
                            radius=int(12 * u), fill=cor_mao)
        d.line([(px + int(40 * u), py + int(30 * u)), (px + int(54 * u), py - int(2 * u))], fill=cor_mao,
               width=int(20 * u))
        d.text((px + int(110 * u), int(26 * u)), "CURTIR", font=_fonte(int(64 * u)), fill=PRETO)
        # botão de inscrição
        d.rounded_rectangle([0, int(170 * u), larg - 1, alt - 1], radius=int(34 * u), fill=cor + (255,),
                            outline=PRETO + (255,), width=int(6 * u))
        fonte = _fonte(int(92 * u))
        tw = d.textlength(texto, font=fonte)
        d.text(((larg - tw) / 2, int(186 * u)), texto, font=fonte, fill=cor_texto)
        return img

    def desenhar(self, frame: Image.Image, t: float) -> None:
        if self.t0 is None or t < self.t0:
            return
        idade = t - self.t0
        clique = 1.15
        if idade < 0.22:
            escala = 0.3 + 0.7 * _ease_back(idade / 0.22)
        elif clique <= idade < clique + 0.16:
            escala = 1.0 - 0.10 * math.sin(math.pi * (idade - clique) / 0.16)
        else:
            escala = 1.0 + 0.025 * math.sin(idade * 6)
        _colar(frame, self.depois if idade >= clique + 0.08 else self.antes, self.cx, self.cy, escala)


class Mascote:
    """Dirige o mascote: entra andando, troca de lado, fala, gesticula, aponta."""

    def __init__(self, kind: str, w: int, h: int, falas: list, blocos: list, carimbos: Carimbos,
                 cta_t0: float | None):
        self.w, self.h, self.falas, self.blocos, self.carimbos, self.cta_t0 = w, h, falas, blocos, carimbos, cta_t0
        if kind == "short":
            self.altura = int(h * 0.265)
            self.pontos = [w * 0.24, w * 0.60]
            self.chao = h * 0.885
        else:
            self.altura = int(h * 0.36)
            self.pontos = [w * 0.10, w * 0.90]
            self.chao = h * 0.975
        # trajetos: (t0, t1, x0, x1)
        fora = -w * 0.15
        self.trajetos = [(0.0, 0.8, fora, self.pontos[0])]
        lado = 0
        for i, fala in enumerate(falas):
            if i and i % 3 == 0 and not fala.cta and fala.t0 > self.trajetos[-1][1] + 1.0:
                novo = 1 - lado
                dur = 0.9 if kind == "short" else 1.25
                self.trajetos.append((fala.t0, fala.t0 + dur, self.pontos[lado], self.pontos[novo]))
                lado = novo
        self.palavras = [p for f in falas for p in f.palavras]
        self.ip = 0
        self.ib = 0

    def _falando(self, t: float) -> bool:
        while self.ip + 1 < len(self.palavras) and t >= self.palavras[self.ip + 1][1]:
            self.ip += 1
        if not self.palavras:
            return False
        _p, a, b = self.palavras[self.ip]
        return a <= t < b

    def desenhar(self, frame: Image.Image, t: float) -> None:
        x, andando = self.pontos[0], False
        for (a, b, x0, x1) in self.trajetos:
            if t >= b:
                x = x1
            elif t >= a:
                p = (t - a) / (b - a)
                x = x0 + (x1 - x0) * (p * p * (3 - 2 * p))
                andando = True
        falando = self._falando(t)
        boca = (2 if int(t * 10) % 2 == 0 else 1) if falando else 0
        while self.ib + 1 < len(self.blocos) and t >= self.blocos[self.ib + 1].t0:
            self.ib += 1
        forte = bool(self.blocos) and self.blocos[self.ib].forte and self.blocos[self.ib].t0 <= t < self.blocos[self.ib].t1
        na_esquerda = x < self.w / 2
        braco_e = braco_d = 12
        aponta = 0
        apontando = self.carimbos.ativo(t) or (self.cta_t0 is not None and t >= self.cta_t0)
        if apontando and not andando:
            # aponta pro meio/alto da tela, onde ficam o carimbo e o botão
            if na_esquerda:
                braco_d, aponta = 150, 1
            else:
                braco_e, aponta = 150, -1
        elif forte and not andando:
            aceno = 120 + 15 * (int(t * 8) % 3)
            if na_esquerda:
                braco_e = aceno
            else:
                braco_d = aceno
        elif andando:
            balanco = int(24 * math.sin(t * 12))
            braco_e, braco_d = 12 + max(0, balanco), 12 + max(0, -balanco)
        fase = int(t * 14) % 8 if andando else -1
        spr = mascote_anim.sprite(self.altura, boca=boca, braco_e=braco_e, braco_d=braco_d, aponta=aponta,
                                  fase=fase, sobrancelha=1 if (forte or apontando) else 0)
        quique = -abs(math.sin(t * 9)) * self.altura * 0.022 if (falando and not andando) else 0
        pe = self.altura * mascote_anim.CHAO_Y / mascote_anim.LH
        frame.paste(spr, (int(x - spr.width / 2), int(self.chao - pe + quique)), spr)


# ------------------------------------------------------------------ render

def _render_motion(kind: str, titulo: str, segments: list, out_path: Path) -> Path:
    w, h = RESOLUTIONS[kind]
    rng = random.Random(sum(ord(c) for c in titulo) + len(segments))

    falas, narracao = _montar_falas(segments)
    cauda = int(0.35 * SR)
    total_amostras = narracao.size + cauda
    total = total_amostras / SR
    blocos = _montar_blocos(falas)
    carimbos_lista = _montar_carimbos(falas, Titulo.DUR + 0.2)
    planos = _montar_planos(falas, total)

    # --- áudio: narração + efeitos + trilha
    mix = np.zeros(total_amostras, dtype=np.float32)
    mix[:narracao.size] += narracao
    whoosh, impacto, pop = _whoosh(), _impacto(), _pop()
    for k, plano in enumerate(p for p in planos if p.forte):
        if k % 2 == 0:
            _somar(mix, whoosh, max(0.0, plano.t0 - 0.12), 0.16)
    for c in carimbos_lista:
        _somar(mix, impacto, c.t0 + 0.10, 0.55)
    cta_t0 = next((f.t0 for f in falas if f.cta), None)
    if cta_t0 is not None:
        _somar(mix, pop, cta_t0 + 0.02, 0.35)
        _somar(mix, pop, cta_t0 + 1.17, 0.45)
    trilha = _musica(total_amostras)
    if trilha is not None:
        mix += trilha * MUSICA_VOLUME
    mix = np.clip(mix, -1.0, 1.0)

    tmp = config.ASSETS_DIR / "tmp" / "motion"
    tmp.mkdir(parents=True, exist_ok=True)
    wav_path = tmp / f"{out_path.stem}.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())

    # --- elementos visuais
    fundo = Fundo(kind, w, h, planos, rng)
    hud = Hud(kind, w, h, falas)
    legendas = Legendas(kind, w, h, blocos)
    carimbos = Carimbos(kind, w, h, carimbos_lista, rng)
    cartao = Titulo(kind, w, h, titulo)
    botao = BotaoCta(kind, w, h, falas)
    mascote = Mascote(kind, w, h, falas, blocos, carimbos, cta_t0)
    degrade_baixo = _degrade(w, int(h * 0.50), True, 190)
    degrade_topo = _degrade(w, int(h * 0.24), False, 150)
    branco = Image.new("RGB", (w, h), (255, 255, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
         "-i", str(wav_path),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", "-shortest",
         str(out_path)],
        stdin=subprocess.PIPE,
    )
    n_frames = int(math.ceil(total * FPS))
    print(f"[render] motion: {kind} {w}x{h}, {total:.1f}s, {n_frames} quadros, {len(planos)} cortes, "
          f"{len(blocos)} legendas, {len(carimbos_lista)} carimbos", flush=True)
    try:
        for n in range(n_frames):
            t = n / FPS
            frame, n_plano, forte = fundo.frame(t)
            # soco de zoom no corte + tremida quando o carimbo bate
            zoom = 1.0 + (0.12 * (1 - _ease_out(n_plano / 6)) if (forte and n_plano < 6) else 0.0)
            dx, dy = carimbos.tremor(t)
            if zoom > 1.001 or dx or dy:
                m = 14 if (dx or dy) else 0
                cw, ch = w / zoom - 2 * m, h / zoom - 2 * m
                bx, by = (w - cw) / 2 + dx, (h - ch) / 2 + dy
                bx, by = min(max(bx, 0.0), w - cw), min(max(by, 0.0), h - ch)
                frame = frame.resize((w, h), Image.BILINEAR, box=(bx, by, bx + cw, by + ch))
            if forte and n_plano < 3:
                frame = Image.blend(frame, branco, (0.30, 0.16, 0.07)[n_plano])
            frame.paste(degrade_baixo, (0, h - degrade_baixo.height), degrade_baixo)
            frame.paste(degrade_topo, (0, 0), degrade_topo)
            mascote.desenhar(frame, t)
            carimbos.desenhar(frame, t)
            botao.desenhar(frame, t)
            cartao.desenhar(frame, t)
            legendas.desenhar(frame, t)
            hud.desenhar(frame, t)
            if kind == "long":   # barra de progresso (no short o app já mostra a dele)
                ImageDraw.Draw(frame).rectangle([0, 0, int(w * t / total), int(h * 0.008)], fill=AMARELO)
            enc.stdin.write(frame.tobytes())
    finally:
        fundo._fechar()
        try:
            enc.stdin.close()
        except Exception:
            pass
    if enc.wait() != 0 or not out_path.exists() or out_path.stat().st_size < 50_000:
        raise RuntimeError("ffmpeg não gerou o vídeo final")
    return out_path


ULTIMO_MOTOR = "?"


def render_video(kind: str, titulo: str, segments: list, out_path: Path) -> Path:
    global ULTIMO_MOTOR
    if not segments:
        raise ValueError("Nenhum segmento de narração pra montar o vídeo.")
    try:
        saida = _render_motion(kind, titulo, segments, out_path)
        ULTIMO_MOTOR = "motion"
        return saida
    except Exception:
        ULTIMO_MOTOR = "classico"
        print("[render] ERRO no motor motion - caindo pro motor clássico:")
        traceback.print_exc()
        import render_classico
        return render_classico.render_video(kind, titulo, segments, out_path)
