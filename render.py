"""
Montagem 100% gratis com ffmpeg + Pillow (sem API paga de render).

Formato: "slideshow narrado" - cada frase do roteiro vira 1 cena com uma
imagem de fundo (assets/broll_oficial/) + legenda da propria frase + a
narracao daquela frase (ver tts.py). Isso e propositalmente o oposto do
padrao que o YouTube pune ("AI slideshow SEM comentario/narracao", ver
README): aqui toda cena tem narracao real de um roteiro checado por voce.

IMPORTANTE sobre as imagens em assets/broll_oficial/:
- So coloque ai screenshots/frames de material OFICIAL ja liberado
  (trailers, Extended Look, Launch Trailer, site oficial da Rockstar).
  Nunca gere imagem de IA fingindo ser cena/personagem do jogo - e isso
  que a Take-Two esta processando (ver conversa anterior). Se ainda nao
  tiver nenhuma imagem oficial salva, o script usa um fundo neutro de
  placeholder pra nao travar - troque assim que tiver os prints oficiais.
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from tts import Segment

RESOLUTIONS = {
    "long": (1920, 1080),
    "short": (1080, 1920),
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _background_image(kind: str, index: int) -> Image.Image:
    w, h = RESOLUTIONS[kind]
    broll_dir = config.ASSETS_DIR / "broll_oficial"
    images = sorted(broll_dir.glob("*.jpg")) + sorted(broll_dir.glob("*.png"))
    if images:
        src = Image.open(images[index % len(images)]).convert("RGB")
        # cobre o frame mantendo proporcao (crop central)
        src_ratio, target_ratio = src.width / src.height, w / h
        if src_ratio > target_ratio:
            new_w = int(src.height * target_ratio)
            src = src.crop(((src.width - new_w) // 2, 0, (src.width + new_w) // 2, src.height))
        else:
            new_h = int(src.width / target_ratio)
            src = src.crop((0, (src.height - new_h) // 2, src.width, (src.height + new_h) // 2))
        return src.resize((w, h))
    # placeholder neutro ate voce colocar imagens oficiais em assets/broll_oficial/
    return Image.new("RGB", (w, h), (18, 18, 24))


def _wrap_by_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Quebra linha medindo largura real do texto renderizado (nao por
    contagem de caracteres) - evita legenda vazando pra fora do frame."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _truncate_by_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "...", font=font) > max_width:
        text = text[:-1]
    return text + "..."


def _frame_with_caption(kind: str, index: int, titulo: str, caption: str) -> Path:
    w, h = RESOLUTIONS[kind]
    img = _background_image(kind, index)
    draw = ImageDraw.Draw(img, "RGBA")
    margin_x = int(w * 0.06)
    text_max_width = w - 2 * margin_x

    # tarja escura + legenda embaixo (estilo legenda de video)
    caption_font = _load_font(int(h * 0.038))
    wrapped = _wrap_by_pixels(draw, caption, caption_font, text_max_width)
    line_h = int(h * 0.05)
    bar_h = line_h * len(wrapped) + int(h * 0.05)
    draw.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0, 180))
    y = h - bar_h + int(h * 0.02)
    for line in wrapped:
        draw.text((margin_x, y), line, font=caption_font, fill=(255, 255, 255, 255))
        y += line_h

    # nome/titulo discreto no topo (mantem identidade do canal em todo video)
    title_font = _load_font(int(h * 0.028))
    draw.rectangle([0, 0, w, int(h * 0.065)], fill=(0, 0, 0, 140))
    title_fit = _truncate_by_pixels(draw, titulo, title_font, text_max_width)
    draw.text((margin_x, int(h * 0.017)), title_fit, font=title_font, fill=(255, 255, 255, 255))

    tmp_dir = config.ASSETS_DIR / "tmp" / "frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"{kind}_{index:03d}.png"
    img.save(out_path)
    return out_path


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def render_video(kind: str, titulo: str, segments: list[Segment], out_path: Path) -> Path:
    if not segments:
        raise ValueError("Nenhum segmento de narracao pra montar o video.")

    clip_dir = config.ASSETS_DIR / "tmp" / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []

    for i, seg in enumerate(segments):
        frame_path = _frame_with_caption(kind, i, titulo, seg.text)
        clip_path = clip_dir / f"clip_{i:03d}.mp4"
        _run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(frame_path),
            "-i", str(seg.audio_path),
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
            "-b:a", "192k", "-pix_fmt", "yuv420p",
            "-t", str(seg.duration_sec),
            "-vf", f"scale={RESOLUTIONS[kind][0]}:{RESOLUTIONS[kind][1]}",
            str(clip_path),
        ])
        clip_paths.append(clip_path)

    concat_list = clip_dir / "concat_list.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(out_path),
    ])
    return out_path
