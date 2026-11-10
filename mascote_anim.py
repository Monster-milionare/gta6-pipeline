"""
Mascote do canal, versão ANIMÁVEL (corpo inteiro, desenhado por código).

O mascote antigo (assets/mascote/*.png) era um busto com 4 poses fixas — só
dava pra trocar a boca. Este aqui é paramétrico: cada quadro é montado a
partir de ângulos (braços, pernas) e estados (boca, sobrancelha), então ele
ANDA de verdade (ciclo de pernas), levanta a mão, aponta, fala com a boca
sincronizada e balança o corpo. render.py pede um sprite por quadro; os
sprites são cacheados por combinação de parâmetros, então custa quase nada.

100% original: formas geométricas em Pillow, estilo flat com contorno
escuro (mesma identidade do busto antigo: jaqueta roxa, corrente dourada,
óculos escuros com reflexo neon rosa/ciano). Nenhum asset de terceiros.
"""
import math
from functools import lru_cache

from PIL import Image, ImageDraw

# Canvas lógico (unidades). O sprite final é escalado pra altura pedida.
LW, LH = 440, 540
CHAO_Y = 520

CONTORNO = (22, 16, 30, 255)
PELE = (232, 168, 118, 255)
PELE_SOMBRA = (198, 134, 90, 255)
CABELO = (34, 26, 32, 255)
JAQUETA = (108, 52, 170, 255)
JAQUETA_ESC = (78, 34, 128, 255)
CAMISETA = (26, 22, 34, 255)
CALCA = (38, 40, 66, 255)
TENIS = (246, 246, 252, 255)
DOURADO = (240, 196, 84, 255)
ROSA = (255, 45, 130, 255)
CIANO = (50, 220, 220, 255)
BRANCO = (250, 250, 255, 255)
BOCA_ESC = (92, 30, 38, 255)
LINGUA = (226, 92, 104, 255)

_O = 7  # espessura do contorno (unidades lógicas)


class _Pincel:
    """Desenha em unidades lógicas num canvas supersampled (antialias)."""

    def __init__(self, k: float):
        self.k = k
        self.img = Image.new("RGBA", (int(LW * k), int(LH * k)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _p(self, x, y):
        return (x * self.k, y * self.k)

    def capsula(self, p0, p1, larg, cor, contorno=True):
        def linha(l, c):
            r = l / 2
            self.d.line([self._p(*p0), self._p(*p1)], fill=c, width=max(1, int(l * self.k)))
            for (x, y) in (p0, p1):
                self.d.ellipse([*self._p(x - r, y - r), *self._p(x + r, y + r)], fill=c)
        if contorno:
            linha(larg + 2 * _O, CONTORNO)
        linha(larg, cor)

    def elipse(self, cx, cy, rx, ry, cor, contorno=True):
        if contorno:
            self.d.ellipse([*self._p(cx - rx - _O, cy - ry - _O), *self._p(cx + rx + _O, cy + ry + _O)], fill=CONTORNO)
        self.d.ellipse([*self._p(cx - rx, cy - ry), *self._p(cx + rx, cy + ry)], fill=cor)

    def caixa(self, x0, y0, x1, y1, raio, cor, contorno=True):
        if contorno:
            self.d.rounded_rectangle([*self._p(x0 - _O, y0 - _O), *self._p(x1 + _O, y1 + _O)],
                                     radius=(raio + _O) * self.k, fill=CONTORNO)
        self.d.rounded_rectangle([*self._p(x0, y0), *self._p(x1, y1)], radius=raio * self.k, fill=cor)

    def poligono(self, pts, cor):
        self.d.polygon([self._p(*p) for p in pts], fill=cor)

    def linha(self, pts, cor, larg):
        self.d.line([self._p(*p) for p in pts], fill=cor, width=max(1, int(larg * self.k)), joint="curve")


def _ponta(origem, ang_graus, comprimento):
    """Ângulo 0 = apontando pra baixo; positivo = abre pro lado de fora
    (pro braço direito da tela = sentido anti-horário visual)."""
    a = math.radians(ang_graus)
    return (origem[0] + math.sin(a) * comprimento, origem[1] + math.cos(a) * comprimento)


def _braco(p: _Pincel, ombro, ang, lado: int, aponta: bool):
    """lado: -1 = braço da esquerda da tela, +1 = da direita."""
    cotovelo = _ponta(ombro, ang * lado, 62)
    # antebraço dobra um pouco mais pra cima quando o braço está levantado
    dobra = ang + (28 if ang > 60 else 6)
    mao = _ponta(cotovelo, dobra * lado, 58)
    p.capsula(ombro, cotovelo, 40, JAQUETA)
    p.capsula(cotovelo, mao, 36, JAQUETA)
    if aponta:
        dedo = _ponta(mao, dobra * lado, 46)
        p.capsula(mao, dedo, 17, PELE)
    p.elipse(mao[0], mao[1], 23, 23, PELE)
    return mao


def _perna(p: _Pincel, quadril, ang, levanta):
    joelho = _ponta(quadril, ang, 52)
    pe = _ponta(joelho, ang * 0.55, 50 - levanta)
    p.capsula(quadril, joelho, 44, CALCA)
    p.capsula(joelho, pe, 40, CALCA)
    # tênis (aponta levemente pra frente/direita da tela)
    p.caixa(pe[0] - 30, pe[1] - 2, pe[0] + 42, pe[1] + 28, 14, TENIS)
    p.linha([(pe[0] - 22, pe[1] + 20), (pe[0] + 36, pe[1] + 20)], (200, 200, 214, 255), 5)


def _boca(p: _Pincel, cx, cy, boca: int):
    if boca == 0:  # sorriso de canto, fechado
        p.linha([(cx - 30, cy - 2), (cx - 6, cy + 9), (cx + 30, cy - 6)], CONTORNO, 8)
    elif boca == 1:  # entreaberta
        p.caixa(cx - 28, cy - 11, cx + 28, cy + 13, 12, BOCA_ESC)
        p.caixa(cx - 20, cy - 9, cx + 20, cy - 2, 3, BRANCO, contorno=False)
    else:  # bem aberta
        p.caixa(cx - 32, cy - 20, cx + 32, cy + 26, 20, BOCA_ESC)
        p.caixa(cx - 23, cy - 17, cx + 23, cy - 7, 4, BRANCO, contorno=False)
        p.elipse(cx, cy + 16, 17, 9, LINGUA, contorno=False)


@lru_cache(maxsize=512)
def sprite(altura: int, boca: int = 0, braco_e: int = 12, braco_d: int = 12,
           aponta: int = 0, fase: int = -1, sobrancelha: int = 0) -> Image.Image:
    """Sprite RGBA do mascote com `altura` px.

    boca: 0 fechada, 1 entreaberta, 2 aberta
    braco_e / braco_d: ângulo em graus (0 = pra baixo, 150 = lá em cima)
    aponta: 0 nada, -1 dedo esticado no braço esquerdo, +1 no direito
    fase: -1 parado; 0..7 = quadro do ciclo de caminhada
    sobrancelha: 0 normal, 1 levantada (ênfase)
    """
    k = altura / LH * 2  # desenha em 2x e reduz (antialias)
    p = _Pincel(k)

    # ciclo de caminhada: pernas alternam, corpo sobe/desce um pouco
    if fase >= 0:
        fi = fase / 8 * 2 * math.pi
        ang_a, ang_b = 26 * math.sin(fi), -26 * math.sin(fi)
        lev_a, lev_b = max(0, 14 * math.cos(fi)), max(0, -14 * math.cos(fi))
        pulo = 6 * abs(math.sin(fi))
    else:
        ang_a = ang_b = 0
        lev_a = lev_b = 0
        pulo = 0

    cy0 = -pulo  # deslocamento vertical do tronco/cabeça

    # sombra no chão
    p.d.ellipse([*p._p(110, CHAO_Y - 6), *p._p(330, CHAO_Y + 18)], fill=(0, 0, 0, 70))

    # pernas (atrás do tronco)
    _perna(p, (190, 392 + cy0), ang_a, lev_a)
    _perna(p, (250, 392 + cy0), ang_b, lev_b)

    # braço de trás (o que NÃO está apontando fica atrás quando abaixado)
    ombro_e, ombro_d = (158, 286 + cy0), (282, 286 + cy0)
    if braco_e <= 60:
        _braco(p, ombro_e, braco_e, -1, aponta == -1)
    if braco_d <= 60:
        _braco(p, ombro_d, braco_d, +1, aponta == 1)

    # tronco: jaqueta aberta + camiseta + corrente
    p.caixa(150, 258 + cy0, 290, 408 + cy0, 44, JAQUETA)
    p.poligono([(196, 262 + cy0), (244, 262 + cy0), (236, 408 + cy0), (204, 408 + cy0)], CAMISETA)
    p.linha([(196, 262 + cy0), (204, 408 + cy0)], JAQUETA_ESC, 7)
    p.linha([(244, 262 + cy0), (236, 408 + cy0)], JAQUETA_ESC, 7)
    p.linha([(200, 290 + cy0), (220, 318 + cy0), (240, 290 + cy0)], DOURADO, 6)
    p.elipse(220, 322 + cy0, 7, 7, DOURADO, contorno=False)

    # cabeça
    hx, hy = 220, 150 + cy0
    p.elipse(hx - 112, hy + 14, 20, 26, PELE)          # orelhas
    p.elipse(hx + 112, hy + 14, 20, 26, PELE)
    p.elipse(hx, hy, 112, 108, PELE)
    # sombra leve na lateral do rosto
    p.d.chord([*p._p(hx - 112, hy - 108), *p._p(hx + 112, hy + 108)], -55, 75, fill=PELE_SOMBRA)
    p.elipse(hx - 12, hy - 4, 100, 102, PELE, contorno=False)
    # cabelo: topete penteado pra trás
    p.d.chord([*p._p(hx - 119, hy - 115), *p._p(hx + 119, hy + 115)], 180, 360, fill=CONTORNO)
    p.d.chord([*p._p(hx - 112, hy - 108), *p._p(hx + 112, hy + 100)], 186, 354, fill=CABELO)
    p.poligono([(hx - 112, hy - 4), (hx - 60, hy - 52), (hx + 20, hy - 66), (hx + 112, hy - 6),
                (hx + 112, hy - 40), (hx - 112, hy - 40)], CABELO)
    p.poligono([(hx - 70, hy - 96), (hx - 10, hy - 140), (hx + 84, hy - 118), (hx + 40, hy - 84)], CONTORNO)
    p.poligono([(hx - 58, hy - 96), (hx - 8, hy - 131), (hx + 68, hy - 114), (hx + 36, hy - 88)], CABELO)

    # sobrancelhas (sobem na ênfase)
    sb = -9 if sobrancelha else 0
    p.linha([(hx - 86, hy - 28 + sb), (hx - 30, hy - 36 + sb)], CONTORNO, 10)
    p.linha([(hx + 30, hy - 36 + sb), (hx + 86, hy - 28 + sb)], CONTORNO, 10)

    # óculos escuros com reflexo neon (identidade do canal)
    p.caixa(hx - 98, hy - 14, hx - 10, hy + 36, 20, (20, 16, 26, 255))
    p.caixa(hx + 10, hy - 14, hx + 98, hy + 36, 20, (20, 16, 26, 255))
    p.linha([(hx - 12, hy + 4), (hx + 12, hy + 4)], CONTORNO, 12)
    p.linha([(hx - 84, hy), (hx - 46, hy + 3)], ROSA, 7)
    p.linha([(hx + 26, hy), (hx + 64, hy + 3)], CIANO, 7)

    _boca(p, hx, hy + 68, boca)

    # braços levantados ficam na frente de tudo
    if braco_e > 60:
        _braco(p, ombro_e, braco_e, -1, aponta == -1)
    if braco_d > 60:
        _braco(p, ombro_d, braco_d, +1, aponta == 1)

    w_final = int(round(LW * altura / LH))
    return p.img.resize((w_final, altura), Image.LANCZOS)


if __name__ == "__main__":
    # folha de poses pra conferir o desenho: python mascote_anim.py
    poses = [
        dict(), dict(boca=1), dict(boca=2, sobrancelha=1),
        dict(boca=2, braco_d=150, aponta=1), dict(boca=1, braco_e=140),
        dict(fase=0), dict(fase=2, boca=1), dict(fase=4), dict(fase=6, boca=2),
    ]
    folha = Image.new("RGBA", (len(poses) * 330, 420), (60, 90, 120, 255))
    for i, kw in enumerate(poses):
        s = sprite(400, **kw)
        folha.alpha_composite(s, (i * 330, 10))
    folha.save("mascote_poses.png")
    print("ok: mascote_poses.png")
