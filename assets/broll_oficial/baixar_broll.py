"""
Baixa screenshots 100% OFICIAIS de GTA VI direto do site oficial da
Rockstar Games (rockstargames.com/VI/media/screenshots) pra servir de
fundo real nos videos - no lugar do placeholder neutro.

IMPORTANTE (seguranca juridica, ver README): estas sao URLs de imagem
hospedadas no proprio dominio rockstargames.com (CDN oficial da
Rockstar/Take-Two), coletadas diretamente da galeria oficial de
screenshots do jogo (138 imagens no total - aqui esta uma amostra de
~69, cobrindo todos os personagens/locais, pra manter o arquivo leve).
NUNCA adicione aqui imagem gerada por IA fingindo ser cena do jogo, nem
imagem de site terceiro (fansite) - so URL direta do dominio oficial
rockstargames.com.

Roda no runtime (CI), baixa pra assets/broll_oficial/ se ainda nao
existir localmente - assim o repo continua 100% texto (sem binario
versionado) e as imagens ficam sempre as mesmas (nomeadas de forma
deterministica a partir da URL) entre execucoes.

Se o download de alguma imagem falhar (rede instavel, URL expirada, etc)
o script so avisa e continua com as outras - nunca trava o pipeline por
causa disso. Se NENHUMA imagem estiver disponivel, render.py ja tem um
fallback de fundo neutro (ver _background_image em render.py).
"""
import os
import re
import sys

import requests

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_SEC = 20

# URLs oficiais (rockstargames.com/VI/media/screenshots) - imwidth=1920
# pra pegar uma resolucao boa o bastante pra fundo de video 1080p/1920x1080.
URLS = [
    'https://www.rockstargames.com/VI/_next/static/media/Jason_and_Lucia_14.10e7v.06pcm_t.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_and_Lucia_18.0kjv.et7330m_.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_and_Lucia_02.0uig00eojlokf.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_and_Lucia_06.1035xf1yo78.b.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_and_Lucia_10.0cauoz34524-..jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_Duval_11.019l5gj6~0~0v.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_Duval_14.0eczq557_iuqo.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_Duval_17.0tp7hiuz.e385.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_Duval_07.0ca326xbl~oyh.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Jason_Duval_10.14zid5kee4hy..jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_11.0j617-ylicowx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_13.08dd3_zn0g59u.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_07.0.c7un8ro7_p2.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_09.0pd.ppokmi8-n.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Lucia_Caminos_01.0a7yqvewctkfp.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Vice_City_13.0iq8ff474tsdx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Vice_City_18.001ebutl6h-9w.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Vice_City_23.183sae.altxv3.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Vice_City_10.0f1q-xa_4q8r2.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Vice_City_03.0nqz~lrqdmlze.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Leonida_Keys_07.0z9tb69ssp4rq.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Leonida_Keys_06.0eapr3hbeyewx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Leonida_Keys_01.0zgz7tveur6y8.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Leonida_Keys_02.0~ptk-53gl0lq.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Leonida_Keys_03.0v_3~-9ceyixc.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Port_Gellhorn_07.053ldlg0m.2r..jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Port_Gellhorn_06.13ghhmb440r6e.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Port_Gellhorn_01.0fmisvza-5-cq.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Port_Gellhorn_02.00e7cz6lwrup-.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Port_Gellhorn_03.00c2b0eh7sm~q.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Grassrivers_07.0txitddjiq5o1.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Grassrivers_08.0x-z0h-he35zo.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Grassrivers_05.0.dx9~67tljry.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Grassrivers_06.0bdeicllwisnc.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Grassrivers_01.1096rw4lbjur_.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Ambrosia_06.0j9c7-8nfb_xf.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Ambrosia_01.0rqphs0gazkm..jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Ambrosia_02.0wtqs05ozl.ym.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Ambrosia_03.0vt46a.1s.7-y.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Ambrosia_04.0.2cefoguu-tt.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Cal_Hampton_01.0xlil231_osh4.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Cal_Hampton_02.05r2t_mck65fe.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Cal_Hampton_03.0.q68~pt1to9z.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Cal_Hampton_04.0-78dep86yx2q.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Boobie_Ike_01.0-wji2pg5anfs.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Boobie_Ike_02.0sp9mtc.1cdzs.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Boobie_Ike_03.0neka36~z25b5.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Boobie_Ike_04.0~1fr6ijgvnzx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/DreQuan_Priest_01.0_0~wi-ipdj35.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/DreQuan_Priest_02.02u69e~nkk3eo.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/DreQuan_Priest_03.0zbl4i_x_1biu.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/DreQuan_Priest_04.0n~kj~px_fn8t.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Real_Dimez_01.0djwwboo8-glx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Real_Dimez_02.1366u9.x.yp0_.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Real_Dimez_03.02o2si7.op.ye.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Real_Dimez_04.0wa3vo07lz4e2.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Raul_Bautista_01.0md1ii-yrn96r.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Raul_Bautista_02.10ddy6ogywu-t.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Raul_Bautista_03.0-x4xbav_6c40.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Raul_Bautista_04.0qx77gyvykvv5.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Brian_Heder_01.0r.ute88os9k-.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Brian_Heder_02.0kmg6iw38f-9o.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Brian_Heder_03.10ntuqh2h6upf.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Brian_Heder_04.0z3o0t88jw54l.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Mount_Kalaga_National_Park_01.0v5fl0f83hjv_.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Mount_Kalaga_National_Park_02.0f24dhopdprvx.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Mount_Kalaga_National_Park_03.037k2s87rwuxc.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Mount_Kalaga_National_Park_04.0e1sxnp1mln2u.jpg?akim=1&imdensity=1&imwidth=1920',
    'https://www.rockstargames.com/VI/_next/static/media/Mount_Kalaga_National_Park_05.0_~vto-o2zxok.jpg?akim=1&imdensity=1&imwidth=1920',
]


def _nome_arquivo(url: str) -> str:
    """Deriva um nome de arquivo estavel e legivel a partir do path da URL."""
    path = url.split("?")[0]
    base = os.path.basename(path)
    m = re.match(r"^(.+?)\.[^.]+\.(jpg|jpeg|png|webp)$", base, re.IGNORECASE)
    if m:
        return f"{m.group(1)}.{m.group(2).lower()}"
    return base


def baixar_todas() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    baixadas = 0
    for url in URLS:
        nome = _nome_arquivo(url)
        destino = os.path.join(OUT_DIR, nome)
        if os.path.exists(destino) and os.path.getsize(destino) > 0:
            baixadas += 1
            continue
        try:
            resp = requests.get(url, timeout=TIMEOUT_SEC, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            with open(destino, "wb") as f:
                f.write(resp.content)
            baixadas += 1
            print(f"baixado: {nome}")
        except Exception as exc:
            print(f"[aviso] falhou {nome}: {exc}", file=sys.stderr)
    print(f"[baixar_broll] {baixadas}/{len(URLS)} imagens oficiais disponiveis em {OUT_DIR}")
    return baixadas


if __name__ == "__main__":
    baixar_todas()
