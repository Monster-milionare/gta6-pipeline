"""
Gera a thumbnail customizada (1280x720) de cada vídeo publicado.

Sem thumbnail customizada o YouTube pega um frame aleatório do vídeo pra
usar como capa - quase sempre pior que uma capa desenhada de propósito, e
é a diferença nº1 de CTR entre canais "automáticos" e canais que crescem.

Critérios aqui seguem o estudo de thumbnails da vidIQ (2026, ~500 vídeos
"breakout" analisados em 30 nichos):
  - rosto/personagem grande, ocupando bem mais de 1/4 do quadro;
  - alto contraste entre texto e fundo (fundo escurecido + contorno preto
    grosso no texto);
  - texto curto, 3-5 palavras de impacto (não o título inteiro - esse já
    aparece embaixo, no YouTube, de qualquer forma);
  - nada de elemento importante no canto inferior direito, onde o YouTube
    sobrepõe a duração do vídeo.

Usa sempre o mascote original do canal (ver assets/mascote/gerar_mascote.py).
O FUNDO agora tenta vir de uma imagem gerada por IA via Pollinations.ai
(gratuito, sem conta, sem chave de API, sem cartão - ver
https://github.com/pollinations/pollinations/blob/master/APIDOCS.md) com
um prompt propositalmente GENÉRICO de estética (néon/Miami/vice-city) -
nunca citamos "GTA VI", nem os nomes dos personagens, nem pedimos pra IA
desenhar uma cena específica do jogo. É arte original com clima parecido,
não uma falsificação de screenshot oficial. Pollinations é "best effort"
(sem SLA, pode falhar ou dar rate-limit) - se der qualquer problema, cai
automaticamente pro fundo com os screenshots oficiais de
assets/broll_oficial/ (mesmos usados no vídeo) ou cor sólida, sem nunca
travar a publicação por causa disso.
"""
import random
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont

import config

W, H = 1280, 720

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

# Prompt fixo e genérico (nunca menciona GTA VI nem personagens) - só
# estética "néon synthwave Miami à noite" pra dar um fundo mais dinâmico
# que uma screenshot estática. Ver aviso de uso no docstring do módulo.
_PROMPT_FUNDO_IA = (
    "neon synthwave miami skyline at night, palm trees, pink and cyan "
    "neon lights, retro 80s crime city aesthetic, rain-soaked street "
    "reflections, cinematic dramatic lighting, high contrast, no text, "
    "no logos, no people, no letters, no watermark"
)

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _fundo_ia(w: int, h: int) -> Image.Image | None:
    """Tenta gerar o fundo via Pollinations.ai. Retorna None (nunca
    levanta exceção) em qualquer falha - timeout, rate limit (serviço
    permite ~1 imagem a cada 45s por IP, tranquilo pro nosso volume de 1
    thumbnail por publicação), fora do ar, resposta invalida, etc."""
    try:
        import requests

        seed = random.randint(0, 999_999)
        url = (
            f"https://image.pollinations.ai/prompt/{quote(_PROMPT_FUNDO_IA)}"
            f"?width={w}&height={h}&seed={seed}&nologo=true&safe=true"
        )
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if img.width < 100 or img.height < 100:
            return None
        return img.resize((w, h))
    except Exception:
        return None

def _fundo_broll(w: int, h: int) -> Image.Image:
    broll_dir = config.ASSETS_DIR / "broll_oficial"
    images = sorted(broll_dir.glob("*.jpg")) + sorted(broll_dir.glob("*.png"))
    if not images:
        return Image.new("RGB", (w, h), (18, 18, 24))
    src = Image.open(random.choice(images)).convert("RGB")
    src_ratio, target_ratio = src.width / src.height, w / h
    if src_ratio > target_ratio:
        new_w = int(src.height * target_ratio)
        src = src.crop(((src.width - new_w) // 2, 0, (src.width + new_w) // 2, src.height))
    else:
        new_h = int(src.width / target_ratio)
        src = src.crop((0, (src.height - new_h) // 2, src.width, (src.height + new_h) // 2))
    return src.resize((w, h))

def _fundo_cover(w: int, h: int) -> Image.Image:
    """Fundo da thumbnail: tenta IA (Pollinations) primeiro, cai pro
    broll oficial / cor sólida se a IA falhar por qualquer motivo."""
    return _fundo_ia(w, h) or _fundo_broll(w, h)

def _escurecer(img: Image.Image, fator: float = 0.62) -> Image.Image:
    """Escurece o fundo (mistura com preto) pra texto/mascote ficarem
    legíveis em cima de qualquer imagem de fundo - contraste é o achado
    mais consistente do estudo da vidIQ."""
    preto = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, preto, 1 - fator)

def _titulo_impacto(titulo: str, max_palavras: int = 5) -> str:
    """3-5 palavras de gancho visual, não o título inteiro (esse já
    aparece embaixo da thumbnail no YouTube de qualquer forma)."""
    palavras = [p for p in titulo.upper().replace(":", "").replace("—", "-").split() if p]
    return " ".join(palavras[:max_palavras])

def gerar_thumbnail(titulo: str, out_path: Path) -> Path:
    img = _fundo_cover(W, H)
    img = _escurecer(img)
    draw = ImageDraw.Draw(img, "RGBA")

    # mascote grande, do lado esquerdo, levemente "sangrando" pra fora do
    # quadro à esquerda (zoom dramático = outro achado comum em thumbnail
    # de sucesso: personagem parece "maior que o quadro")
    mascote_path = config.ASSETS_DIR / "mascote" / "falando_b.png"
    if mascote_path.exists():
        mascote = Image.open(mascote_path).convert("RGBA")
        alvo_h = int(H * 0.88)
        escala = alvo_h / mascote.height
        novo_tam = (int(mascote.width * escala), alvo_h)
        mascote_r = mascote.resize(novo_tam, Image.LANCZOS)
        x = -int(W * 0.015)
        y = H - novo_tam[1]
        img.paste(mascote_r, (x, y), mascote_r)

    # texto de impacto no canto superior-direito (longe do canto
    # inferior-direito, onde o YouTube desenha a duração do vídeo)
    texto = _titulo_impacto(titulo)
    tx = int(W * 0.56)
    max_width = W - tx - int(W * 0.04)
    font_size = int(H * 0.145)
    font = _load_font(font_size)
    while draw.textlength(texto, font=font) > max_width and font_size > 28:
        font_size -= 4
        font = _load_font(font_size)

    ty = int(H * 0.08)
    draw.text(
        (tx, ty), texto, font=font, fill=(255, 220, 40, 255),
        stroke_width=max(3, font_size // 14), stroke_fill=(0, 0, 0, 255),
    )

    # faixa de identidade do canal - reforça reconhecimento de marca entre
    # vídeos (mesmo esquema de cor da legenda/título dentro do vídeo)
    bar_h = int(H * 0.085)
    draw.rectangle([0, H - bar_h, W, H], fill=(20, 10, 32, 235))
    marca_font = _load_font(int(bar_h * 0.55))
    draw.text(
        (int(W * 0.37), H - bar_h + int(bar_h * 0.18)), "GTA VI BRASIL",
        font=marca_font, fill=(255, 255, 255, 255),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
