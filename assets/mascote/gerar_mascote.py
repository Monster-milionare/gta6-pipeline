"""
Gera o mascote original do canal: um "protagonista" estilo cartaz de Vice
City/Miami — ilustracao flat/vetorial de busto (cabeca + ombros), oculos
escuros, visual confiante e "serio" (nao cartunesco). 100% desenhado do
zero com formas geometricas (Pillow). Nao usa nenhum asset, personagem,
fonte ou elemento da Rockstar/Take-Two - e so uma ilustracao original no
estilo "flat design" com paleta neon (rosa/ciano/roxo), que e so uma
paleta de cores, livre de uso.

Gera 3 poses (fundo transparente, 800x800):
  - idle.png       : boca fechada, parado (cena padrao)
  - falando_a.png  : boca entreaberta (quadro de fala 1)
  - falando_b.png  : boca aberta (quadro de fala 2)
As poses falando_a/falando_b alternam quadro a quadro durante a narracao
pra dar ilusao de "boca mexendo" (lip-sync simples).
"""
from PIL import Image, ImageDraw, ImageFilter
import math
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
W, H = 800, 800

# Paleta: tons quentes (pele estilizada, nao-naturalista) + neon rosa/ciano/roxo.
PELE = (224, 160, 110, 255)
PELE_SOMBRA = (190, 128, 86, 255)
CABELO = (30, 24, 28, 255)
ROXO = (64, 30, 96, 255)
ROXO_ESCURO = (40, 18, 64, 255)
ROSA = (255, 45, 130, 255)
CIANO = (50, 220, 220, 255)
PRETO = (18, 16, 22, 255)
BRANCO = (248, 248, 255, 255)
DOURADO = (235, 190, 90, 255)


def _base_canvas():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _glow(img, cx, cy, r, cor, blur=18):
    """Brilho neon suave atras de um elemento (ex.: aro dos oculos)."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(layer)


def _draw_shoulders_jacket(draw):
    # Ombros/torso - jaqueta aberta roxa sobre camiseta escura, estilo
    # "cartaz de noite em Miami": silhueta larga, confiante.
    draw.polygon([
        (120, 800), (120, 560), (230, 470), (400, 440), (570, 470),
        (680, 560), (680, 800),
    ], fill=ROXO_ESCURO)
    # lapela/abertura da jaqueta revelando camiseta escura por baixo
    draw.polygon([(330, 490), (400, 470), (470, 490), (430, 800), (370, 800)], fill=PRETO)
    # detalhe lapela (linhas da jaqueta)
    draw.line([(330, 490), (300, 800)], fill=(90, 50, 130, 255), width=10)
    draw.line([(470, 490), (500, 800)], fill=(90, 50, 130, 255), width=10)
    # corrente dourada simples
    draw.line([(365, 560), (400, 610), (435, 560)], fill=DOURADO, width=6, joint="curve")


def _draw_neck(draw):
    draw.polygon([(340, 430), (460, 430), (450, 500), (350, 500)], fill=PELE_SOMBRA)


def _draw_head(draw):
    # Cabeca (formato levemente quadrado/mandibula marcada = visual "serio")
    draw.polygon([
        (290, 230), (300, 180), (340, 145), (400, 135), (460, 145),
        (500, 180), (510, 230), (505, 330), (480, 400), (440, 430),
        (400, 440), (360, 430), (320, 400), (295, 330),
    ], fill=PELE)
    # sombra lateral sutil (dá volume sem precisar de gradiente complexo)
    draw.polygon([
        (480, 230), (505, 260), (500, 340), (478, 400), (440, 428),
        (455, 370), (470, 300),
    ], fill=PELE_SOMBRA)

    # Cabelo curto penteado pra tras
    draw.polygon([
        (288, 230), (295, 165), (330, 128), (400, 112), (470, 128),
        (508, 168), (512, 235), (495, 210), (460, 165), (400, 150),
        (340, 165), (305, 210),
    ], fill=CABELO)
    # costeleta
    draw.polygon([(300, 220), (320, 215), (315, 300), (298, 290)], fill=CABELO)
    draw.polygon([(500, 220), (480, 215), (485, 300), (502, 290)], fill=CABELO)

    # sobrancelha (confiante, levemente franzida) - um pouco acima da armacao
    draw.line([(320, 232), (372, 226)], fill=CABELO, width=9)
    draw.line([(428, 226), (480, 232)], fill=CABELO, width=9)


def _draw_oculos(draw, img):
    # Oculos aviador espelhado - unico elemento "neon" no rosto, reforca
    # a identidade visual do canal sem parecer cartunesco.
    _glow(img, 340, 278, 38, (255, 45, 130, 55), blur=12)
    _glow(img, 462, 278, 38, (50, 220, 220, 55), blur=12)
    draw = ImageDraw.Draw(img, "RGBA")
    # armacao
    draw.rounded_rectangle([285, 250, 400, 308], radius=26, fill=PRETO)
    draw.rounded_rectangle([402, 250, 517, 308], radius=26, fill=PRETO)
    draw.line([(400, 272), (402, 272)], fill=PRETO, width=14)
    # lentes espelhadas (gradiente simples de 2 tons por lente)
    draw.rounded_rectangle([294, 258, 392, 300], radius=20, fill=(60, 30, 70, 230))
    draw.rounded_rectangle([410, 258, 508, 300], radius=20, fill=(20, 110, 120, 230))
    draw.line([(305, 265), (345, 268)], fill=ROSA, width=6)
    draw.line([(421, 265), (461, 268)], fill=CIANO, width=6)
    # hastes
    draw.line([(285, 270), (265, 255)], fill=PRETO, width=8)
    draw.line([(517, 270), (537, 255)], fill=PRETO, width=8)
    return draw


def _draw_nariz_e_sombra(draw):
    draw.line([(398, 300), (392, 350), (405, 358)], fill=PELE_SOMBRA, width=6, joint="curve")


def _draw_boca(draw, abertura):
    """abertura: 0 = fechada (serio), 1 = entreaberta, 2 = aberta (falando)."""
    cx, cy = 400, 392
    if abertura == 0:
        draw.line([(368, cy), (432, cy - 4)], fill=(120, 60, 60, 255), width=7)
        draw.line([(368, cy + 3), (432, cy - 1)], fill=PELE_SOMBRA, width=2)
    elif abertura == 1:
        draw.rounded_rectangle([370, cy - 10, 430, cy + 12], radius=10, fill=(90, 35, 40, 255))
        draw.rectangle([374, cy - 8, 426, cy - 2], fill=BRANCO)
    else:
        draw.rounded_rectangle([365, cy - 18, 435, cy + 22], radius=14, fill=(70, 25, 30, 255))
        draw.rectangle([370, cy - 15, 430, cy - 5], fill=BRANCO)
        draw.rounded_rectangle([376, cy + 4, 424, cy + 16], radius=8, fill=(150, 60, 65, 255))


def gerar_pose(nome, abertura_boca):
    img = _base_canvas()
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_shoulders_jacket(draw)
    _draw_neck(draw)
    _draw_head(draw)
    draw = _draw_oculos(draw, img)
    _draw_nariz_e_sombra(draw)
    _draw_boca(draw, abertura_boca)
    path = os.path.join(OUT_DIR, nome)
    img.save(path)
    print(f"gerado: {path}")


if __name__ == "__main__":
    gerar_pose("idle.png", 0)
    gerar_pose("falando_a.png", 1)
    gerar_pose("falando_b.png", 2)
