"""
Montagem 100% grátis com ffmpeg + Pillow (sem API paga de render).

Formato: "slideshow narrado" — cada frase do roteiro vira 1 cena com uma
imagem de fundo (assets/broll_oficial/) + legenda da própria frase + a
narração daquela frase (ver tts.py). Isso é propositalmente o oposto do
padrão que o YouTube pune ("AI slideshow SEM comentário/narração", ver
README): aqui toda cena tem narração real de um roteiro checado por você.

DINAMISMO DE EDIÇÃO (pedido explícito: "estilo Mr. Beast", sempre ter algo
acontecendo na tela, personagem não pode ficar grudado parado no mesmo
canto o vídeo inteiro):
- O mascote alterna de lado (esquerda/direita) cena a cena (_lado_da_cena)
  em vez de ficar sempre no mesmo canto — já tira boa parte da sensação de
  "imagem estática com boca mexendo".
- A cada DESTAQUE_A_CADA frases (que não sejam CTA), a cena vira um
  "destaque" full-bleed: a imagem de broll ocupa a tela quase toda (tarja
  de legenda bem menor) e o mascote encolhe pra um canto na pose
  "apontando", como se estivesse mostrando/revelando aquele print pro
  espectador — é a versão possível, com os assets que realmente existem
  no repo, do pedido de "ele aponta pra trás e aparece um trecho do
  trailer": aqui é sempre um print OFICIAL já salvo em broll_oficial/,
  nunca um clipe de vídeo (não existe no repo) nem uma alegação de "leak"
  inventada (isso o quality_gate.py já bloqueia de propósito — ver
  quality_gate.py e README, é o tipo de conteúdo que gerou processo da
  Take-Two contra outros canais).
- A trilha sonora de fundo já roda por baixo do vídeo inteiro (ver
  _misturar_musica) e as frases de impacto/CTA já saem com a voz mais
  "animada" (ver tts.py) — ajuda a dar a sensação de ritmo mesmo sem
  efeito de câmera (zoom/pan tipo Ken Burns foi avaliado e descartado por
  enquanto: é frágil em cima de ffmpeg puro e arriscava quebrar TODOS os
  renders de uma vez só sem forma fácil de testar antes).

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
# assets binarios versionados no repo). Alterna as poses "falando_a"/
# "falando_b" dentro de CADA frase (não mais 1 pose por frase inteira) pra
# simular boca mexendo de verdade enquanto a narração toca - estilo
# stop-motion, trocando a cada MOUTH_FRAME_SEC segundos. Na frase de CTA
# (pedido de like/inscrição) usa a pose "apontando" fixa + gráfico.
MOUTH_CYCLE_POSES = ["falando_a.png", "falando_b.png"]
MOUTH_FRAME_SEC = 0.28
CTA_POSE = "apontando.png"
# Posição aproximada (no canvas 800x800 de gerar_mascote.py) da ponta do
# dedo indicador na pose "apontando" - usada pra ancorar o gráfico de
# like/inscrição exatamente onde o mascote está apontando. Só vale pra
# pose desenhada sem flip (lado "esquerda") - por isso CTA sempre fica
# desse lado (ver _frame_with_caption).
_CTA_FINGERTIP_REL = (724, 194)
_mascote_cache: dict[str, Image.Image] = {}

# Lado que o mascote fica em cada cena "normal" (fala contínua) - alterna
# cena a cena pra dar sensação de posição mudando (ver docstring do
# módulo). CTA e cenas de "destaque" têm posição própria, não usam isso.
_LADOS = ("esquerda", "direita")

def _lado_da_cena(index: int) -> str:
    return _LADOS[index % len(_LADOS)]

# A cada quantas frases (não-CTA) insere uma cena de "destaque" full-bleed
# (ver docstring do módulo). 4 funciona bem tanto pros shorts curtos (pelo
# menos 1 destaque aparece) quanto pro vídeo longo (não vira repetitivo).
DESTAQUE_A_CADA = 4

def _mouth_poses_for_duration(duration_sec: float) -> list[str]:
    """Lista de poses (boca) a percorrer ao longo da frase, pra dar
    sensação de fala contínua em vez de 1 pose congelada por frase."""
    n = max(2, round(duration_sec / MOUTH_FRAME_SEC))
    return [MOUTH_CYCLE_POSES[i % len(MOUTH_CYCLE_POSES)] for i in range(n)]

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

def _desenhar_mascote(img: Image.Image, pose_filename: str, bar_h: int, w: int, h: int, lado: str = "esquerda") -> tuple[int, int, float] | None:
    """Desenha o mascote na pose indicada, no lado pedido ("esquerda" ou
    "direita" - cena a cena, pra dar sensação de posição mudando em vez de
    personagem grudado sempre no mesmo canto). Retorna (x, y, escala) de
    onde ele foi desenhado - usado pra alinhar o gráfico de CTA com o dedo
    que aponta na pose "apontando" (CTA sempre chama isso com lado
    "esquerda", pra manter essa matemática simples e confiável)."""
    mascote = _load_mascote(pose_filename)
    if mascote is None:
        return None
    alvo_h = int(h * 0.26)
    escala = alvo_h / mascote.height
    novo_tam = (int(mascote.width * escala), alvo_h)
    mascote_r = mascote.resize(novo_tam, Image.LANCZOS)
    margin_x = int(w * 0.04)
    if lado == "direita":
        mascote_r = mascote_r.transpose(Image.FLIP_LEFT_RIGHT)
        x = w - margin_x - novo_tam[0]
    else:
        x = margin_x
    y = max(h - bar_h - novo_tam[1] - int(h * 0.015), 0)
    img.paste(mascote_r, (x, y), mascote_r)
    return (x, y, escala)

def _draw_cta_grafico(draw: ImageDraw.ImageDraw, posicao: tuple[int, int, float], w: int, h: int) -> None:
    """Gráfico de "curta e se inscreva" ancorado no dedo apontando do
    mascote (pose CTA_POSE) - sem usar o logo/ícone oficial do YouTube,
    só formas geométricas originais (coração/joia estilizada + texto)."""
    x, y, escala = posicao
    fx = x + _CTA_FINGERTIP_REL[0] * escala
    fy = y + _CTA_FINGERTIP_REL[1] * escala

    # Mede o texto de verdade (igual _wrap_by_pixels/_truncate_by_pixels já
    # fazem pra legenda) e encolhe a fonte se precisar, em vez de supor uma
    # largura fixa de caixa — no formato vertical (short, w menor) um texto
    # fixo com fonte fixa vazava pra fora do frame.
    margin = int(w * 0.04)
    max_box_w = w - 2 * margin
    box_h = int(h * 0.072)
    icon_r = int(box_h * 0.30)
    icon_left_pad = int(box_h * 0.30)
    texto_pad_left = int(box_h * 1.05)
    texto_pad_right = int(box_h * 0.35)
    texto = "CURTA E SE INSCREVA"

    font_size = int(box_h * 0.40)
    font = _load_font(font_size)
    texto_w = draw.textlength(texto, font=font)
    box_w = texto_pad_left + texto_w + texto_pad_right
    while box_w > max_box_w and font_size > 14:
        font_size -= 2
        font = _load_font(font_size)
        texto_w = draw.textlength(texto, font=font)
        box_w = texto_pad_left + texto_w + texto_pad_right
    box_w = min(int(box_w), max_box_w)

    bx = int(fx - box_w * 0.35)
    bx = min(max(bx, margin), w - box_w - margin)
    by = max(int(fy - box_h * 1.3), int(h * 0.075))

    draw.rounded_rectangle(
        [bx, by, bx + box_w, by + box_h], radius=int(box_h * 0.25),
        fill=(220, 20, 60, 235), outline=(255, 255, 255, 255), width=4,
    )
    icon_cx, icon_cy = bx + icon_left_pad + icon_r, by + box_h // 2
    draw.ellipse(
        [icon_cx - icon_r, icon_cy - icon_r, icon_cx + icon_r, icon_cy + icon_r],
        fill=(255, 255, 255, 255),
    )
    draw.polygon([
        (icon_cx - icon_r * 0.4, icon_cy + icon_r * 0.55),
        (icon_cx - icon_r * 0.1, icon_cy - icon_r * 0.55),
        (icon_cx + icon_r * 0.1, icon_cy - icon_r * 0.55),
        (icon_cx + icon_r * 0.4, icon_cy + icon_r * 0.55),
    ], fill=(220, 20, 60, 255))

    tx = bx + texto_pad_left
    bbox = draw.textbbox((0, 0), texto, font=font)
    text_h = bbox[3] - bbox[1]
    ty = by + (box_h - text_h) // 2 - bbox[1]
    draw.text((tx, ty), texto, font=font, fill=(255, 255, 255, 255))

    # linha pontilhada ligando o gráfico ao dedo (reforça o "apontando pra
    # isso aqui" em vez de só coincidir visualmente por acaso)
    origem = (bx + box_w * 0.3, by + box_h)
    passos = 9
    for s in range(passos):
        if s % 2 == 0:
            continue
        t0, t1 = s / passos, (s + 1) / passos
        p0 = (origem[0] + (fx - origem[0]) * t0, origem[1] + (fy - origem[1]) * t0)
        p1 = (origem[0] + (fx - origem[0]) * t1, origem[1] + (fy - origem[1]) * t1)
        draw.line([p0, p1], fill=(255, 255, 255, 200), width=4)

def _background_image(kind: str, index: int, offset: int = 0) -> Image.Image:
    w, h = RESOLUTIONS[kind]
    broll_dir = config.ASSETS_DIR / "broll_oficial"
    images = sorted(broll_dir.glob("*.jpg")) + sorted(broll_dir.glob("*.png"))
    if images:
        src = Image.open(images[(index + offset) % len(images)]).convert("RGB")
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

def _frame_with_caption(
    kind: str, index: int, titulo: str, caption: str,
    pose_filename: str, cta: bool = False, sub: int = 0, lado: str = "esquerda",
) -> Path:
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

    # mascote original do canal, na pose pedida (alterna boca dentro da
    # própria frase pra dar sensação de fala contínua; na frase de CTA
    # fica fixo na pose "apontando"). CTA sempre do lado esquerdo (ver
    # _CTA_FINGERTIP_REL); fora isso, alterna lado cena a cena.
    posicao = _desenhar_mascote(img, pose_filename, bar_h, w, h, lado=("esquerda" if cta else lado))

    # nome/título discreto no topo (mantém identidade do canal em todo vídeo)
    title_font = _load_font(int(h * 0.028))
    draw.rectangle([0, 0, w, int(h * 0.065)], fill=(0, 0, 0, 140))
    title_fit = _truncate_by_pixels(draw, titulo, title_font, text_max_width)
    draw.text((margin_x, int(h * 0.017)), title_fit, font=title_font, fill=(255, 255, 255, 255))

    if cta and posicao is not None:
        _draw_cta_grafico(draw, posicao, w, h)

    tmp_dir = config.ASSETS_DIR / "tmp" / "frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"{kind}_{index:03d}_{sub:02d}.png"
    img.save(out_path)
    return out_path

def _frame_destaque(kind: str, index: int, titulo: str, caption: str, pose_filename: str) -> Path:
    """Cena de "destaque" full-bleed: o print de broll ocupa a tela quase
    toda (tarja de legenda bem menor que o normal) e o mascote encolhe pra
    um canto, na pose "apontando" — como se estivesse revelando/mostrando
    aquele print pro espectador. Usada periodicamente (DESTAQUE_A_CADA)
    pra quebrar a repetição visual da cena "padrão" (mascote grande +
    legenda grande), sem inventar clipe de trailer que não existe no repo
    nem reaproveitar a mesma imagem da cena vizinha (ver offset em
    _background_image)."""
    w, h = RESOLUTIONS[kind]
    img = _background_image(kind, index, offset=7)
    draw = ImageDraw.Draw(img, "RGBA")
    margin_x = int(w * 0.06)
    text_max_width = w - 2 * margin_x

    caption_font = _load_font(int(h * 0.034))
    wrapped = _wrap_by_pixels(draw, caption, caption_font, text_max_width)
    line_h = int(h * 0.046)
    bar_h = line_h * len(wrapped) + int(h * 0.035)
    draw.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0, 165))
    y = h - bar_h + int(h * 0.015)
    for line in wrapped:
        draw.text((margin_x, y), line, font=caption_font, fill=(255, 255, 255, 255))
        y += line_h

    # mascote pequeno no canto direito (oposto da legenda), na pose
    # apontando - sempre com flip, encarando pro centro da imagem como se
    # estivesse mostrando o print atrás dele.
    mascote = _load_mascote(pose_filename)
    if mascote is not None:
        alvo_h = int(h * 0.16)
        escala = alvo_h / mascote.height
        novo_tam = (int(mascote.width * escala), alvo_h)
        mascote_r = mascote.resize(novo_tam, Image.LANCZOS).transpose(Image.FLIP_LEFT_RIGHT)
        mx = w - int(w * 0.04) - novo_tam[0]
        my = max(h - bar_h - novo_tam[1] - int(h * 0.02), 0)
        img.paste(mascote_r, (mx, my), mascote_r)

    title_font = _load_font(int(h * 0.028))
    draw.rectangle([0, 0, w, int(h * 0.065)], fill=(0, 0, 0, 140))
    title_fit = _truncate_by_pixels(draw, titulo, title_font, text_max_width)
    draw.text((margin_x, int(h * 0.017)), title_fit, font=title_font, fill=(255, 255, 255, 255))

    tmp_dir = config.ASSETS_DIR / "tmp" / "frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"{kind}_{index:03d}_destaque.png"
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
        clip_path = clip_dir / f"clip_{i:03d}.mp4"
        w, h = RESOLUTIONS[kind]
        eh_destaque = (not seg.is_cta) and i > 0 and (i % DESTAQUE_A_CADA == DESTAQUE_A_CADA - 1)

        if seg.is_cta:
            # frase de CTA: 1 frame só (pose "apontando" + gráfico de
            # like/inscrição), igual ao esquema antigo - não precisa de
            # boca mexendo nesse trecho, o importante é o dedo + gráfico
            # ficarem parados e legíveis.
            frame_path = _frame_with_caption(kind, i, titulo, seg.text, CTA_POSE, cta=True)
            _run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(frame_path),
                "-i", str(seg.audio_path),
                "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
                "-b:a", "192k", "-pix_fmt", "yuv420p",
                "-t", str(seg.duration_sec),
                "-vf", f"scale={w}:{h}",
                str(clip_path),
            ])
        elif eh_destaque:
            # cena de "destaque" full-bleed periódica (ver _frame_destaque
            # e docstring do módulo) - quebra a repetição visual, estilo
            # "sempre tem algo acontecendo na tela".
            frame_path = _frame_destaque(kind, i, titulo, seg.text, CTA_POSE)
            _run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(frame_path),
                "-i", str(seg.audio_path),
                "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
                "-b:a", "192k", "-pix_fmt", "yuv420p",
                "-t", str(seg.duration_sec),
                "-vf", f"scale={w}:{h}",
                str(clip_path),
            ])
        else:
            # frase normal: gera vários sub-quadros trocando a pose da boca
            # (falando_a/falando_b) ao longo da própria frase, concatenados
            # num mini-vídeo mudo via ffmpeg concat demuxer, e só depois
            # junta com o áudio da frase - dá a sensação de boca mexendo
            # continuamente em vez de 1 pose travada por frase inteira.
            # Lado do mascote alterna cena a cena (ver _lado_da_cena).
            lado = _lado_da_cena(i)
            poses = _mouth_poses_for_duration(seg.duration_sec)
            frame_paths = [
                _frame_with_caption(kind, i, titulo, seg.text, pose, sub=j, lado=lado)
                for j, pose in enumerate(poses)
            ]
            sub_dur = seg.duration_sec / len(frame_paths)
            lista_path = clip_dir / f"mouth_list_{i:03d}.txt"
            linhas = []
            for p in frame_paths:
                linhas.append(f"file '{p.resolve()}'")
                linhas.append(f"duration {sub_dur:.3f}")
            linhas.append(f"file '{frame_paths[-1].resolve()}'")  # concat demuxer exige repetir o último
            lista_path.write_text("\n".join(linhas), encoding="utf-8")

            video_mudo = clip_dir / f"mouth_{i:03d}.mp4"
            _run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista_path),
                "-vf", f"scale={w}:{h}", "-pix_fmt", "yuv420p",
                "-c:v", "libx264", "-fps_mode", "vfr",
                str(video_mudo),
            ])
            _run([
                "ffmpeg", "-y",
                "-i", str(video_mudo), "-i", str(seg.audio_path),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", str(seg.duration_sec),
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
