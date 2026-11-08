"""
Montagem 100% grátis com ffmpeg + Pillow (sem API paga de render).

Formato: "slideshow narrado" — cada frase do roteiro vira 1 cena com uma
imagem de fundo (assets/broll_oficial/) + legenda da própria frase + a
narração daquela frase (ver tts.py). Isso é propositalmente o oposto do
padrão que o YouTube pune ("AI slideshow SEM comentário/narração", ver
README): aqui toda cena tem narração real de um roteiro checado por você.

IMPORTANTE sobre as imagens em assets/broll_oficial/:
- Só coloque aí screenshots/frames de material OFICIAL já liberado
  (trailers, Extended Look, Launch Trailer, site oficial da Rockstar).
  Nunca gere imagem de IA fingindo ser cena/personagem do jogo — é isso
  que a Take-Two está processando (ver conversa anterior). Se ainda não
  tiver nenhuma imagem oficial salva, o script usa um fundo neutro de
  placeholder pra não travar — troque assim que tiver os prints oficiais.
"""
import random
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

# Mascote original do canal (protagonista estilo Vice City/Miami) - ver
# assets/mascote/gerar_mascote.py (gerado em runtime pelo workflow, sem
# assets binarios versionados no repo). Alterna as duas poses de "falando"
# a cada frase pra dar uma animação simples de boca mexendo (estilo
# stop-motion) sem precisar de video real.
MASCOTE_POSES = ["falando_a.png", "falando_b.png"]
_mascote_cache: dict[str, Image.Image] = {}

# Trilha de fundo 100% original, sintetizada em runtime - ver
# assets/musica/gerar_musica.py. Se a pasta estiver vazia (gerador ainda
# não rodou), o vídeo sai só com a narração (sem travar).
MUSICA_VOLUME = 0.10  # bem baixo, pra não competir com a narração


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _load_mascote(pose_filename: str) -> Image.Image | None:
    if pose_filename in _mascote_cache:
        return _mascote_cache[pose_filename]
    path = config.ASSETS_DIR / "mascote" / pose_filename
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    _mascote_cache[pose_filename] = img
    return img


def _desenhar_mascote(img: Image.Image, index: int, bar_h: int, w: int, h: int) -> None:
    pose_filename = MASCOTE_POSES[index % len(MASCOTE_POSES)]
    mascote = _load_mascote(pose_filename)
    if mascote is None:
        return
    alvo_h = int(h * 0.26)
    escala = alvo_h / mascote.height
    novo_tam = (int(mascote.width * escala), alvo_h)
    mascote_r = mascote.resize(novo_tam, Image.LANCZOS)
    margin_x = int(w * 0.04)
    x = margin_x
    y = h - bar_h - novo_tam[1] - int(h * 0.015)
    img.paste(mascote_r, (x, max(y, 0)), mascote_r)


def _background_image(kind: str, index: int) -> Image.Image:
    w, h = RESOLUTIONS[kind]
    broll_dir = config.ASSETS_DIR / "broll_oficial"
    images = sorted(broll_dir.glob("*.jpg")) + sorted(broll_dir.glob("*.png"))
    if images:
        src = Image.open(images[index % len(images)]).convert("RGB")
        # cobre o frame mantendo proporção (crop central)
        src_ratio, target_ratio = src.width / src.height, w / h
        if src_ratio > target_ratio:
            new_w = int(src.height * target_ratio)
            src = src.crop(((src.width - new_w) // 2, 0, (src.width + new_w) // 2, src.height))
        else:
            new_h = int(src.width / target_ratio)
            src = src.crop((0, (src.height - new_h) // 2, src.width, (src.height + new_h) // 2))
        return src.resize((w, h))
    # placeholder neutro até você colocar imagens oficiais em assets/broll_oficial/
    return Image.new("RGB", (w, h), (18, 18, 24))


def _wrap_by_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Quebra linha medindo largura real do texto renderizado (não por
    contagem de caracteres) — evita legenda vazando pra fora do frame."""
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
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def _frame_with_caption(kind: str, index: int, titulo: str, caption: str) -> Path:
    w, h = RESOLUTIONS[kind]
    img = _background_image(kind, index)
    draw = ImageDraw.Draw(img, "RGBA")
    margin_x = int(w * 0.06)
    text_max_width = w - 2 * margin_x

    # tarja escura + legenda embaixo (estilo legenda de vídeo)
    caption_font = _load_font(int(h * 0.038))
    wrapped = _wrap_by_pixels(draw, caption, caption_font, text_max_width)
    line_h = int(h * 0.05)
    bar_h = line_h * len(wrapped) + int(h * 0.05)
    draw.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0, 180))
    y = h - bar_h + int(h * 0.02)
    for line in wrapped:
        draw.text((margin_x, y), line, font=caption_font, fill=(255, 255, 255, 255))
        y += line_h

    # mascote original do canal, "falando" (alterna pose a cada frase)
    _desenhar_mascote(img, index, bar_h, w, h)

    # nome/título discreto no topo (mantém identidade do canal em todo vídeo)
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


def _escolher_musica() -> Path | None:
    musica_dir = config.ASSETS_DIR / "musica"
    faixas = sorted(musica_dir.glob("*.wav")) + sorted(musica_dir.glob("*.mp3"))
    if not faixas:
        return None
    return random.choice(faixas)


def _misturar_musica(video_sem_musica: Path, out_path: Path) -> None:
    faixa = _escolher_musica()
    if faixa is None:
        # sem trilha disponível ainda - usa o vídeo só com narração
        video_sem_musica.replace(out_path)
        return
    _run([
        "ffmpeg", "-y",
        "-i", str(video_sem_musica),
        "-stream_loop", "-1", "-i", str(faixa),
        "-filter_complex",
        f"[1:a]volume={MUSICA_VOLUME}[musica];[0:a][musica]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ])


def render_video(kind: str, titulo: str, segments: list[Segment], out_path: Path) -> Path:
    if not segments:
        raise ValueError("Nenhum segmento de narração pra montar o vídeo.")

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
    sem_musica_path = clip_dir / "concat_sem_musica.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(sem_musica_path),
    ])
    _misturar_musica(sem_musica_path, out_path)
    return out_path
