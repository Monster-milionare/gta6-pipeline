"""
Atualizacao 2.0 - estilos de edicao e "pegadas" de roteiro que ROTACIONAM.

Ideia: nenhum video pode parecer o anterior. Cada item do dia recebe
  - um ESTILO de edicao (ritmo de corte, legenda, HUD, mascote, filtro de cor...),
  - uma PEGADA de roteiro (o jeito de contar: numero chocante, alerta, A ou B...).
A escolha e sorteada com PESOS que vem de state/pesos.json, que o placar
(metricas.py) recalcula todo dia olhando as views reais: o que deu certo
aparece mais, mas nada some de vez (piso de exploracao).

Tudo aqui e puro Python (sem rede) e nunca levanta erro pra fora: se algo
falhar, devolve o estilo/pegada padrao e o video sai normal.
"""
import json
import random
from dataclasses import dataclass
from pathlib import Path

import config

PESOS_ARQ = config.STATE_DIR / "pesos.json"
VIDEOS_ARQ = config.STATE_DIR / "videos.json"

AMARELO = (255, 208, 20)
BRANCO = (255, 255, 255)
VERMELHO = (232, 48, 42)
CIANO = (60, 235, 255)
MAGENTA = (255, 70, 200)
VERDE = (120, 255, 120)


@dataclass(frozen=True)
class Estilo:
    nome: str
    descricao: str
    ritmo: str                      # "turbo" | "rapido" | "medio" | "lento"
    corte_max: float = 1.8          # duracao maxima de um plano (short)
    plano_max: float = 2.3
    soco: float = 0.12              # zoom de "soco" no corte (0 = sem)
    flash: float = 1.0              # intensidade do flash branco no corte
    glitch: bool = False            # separacao RGB nos cortes
    deriva: float = 0.0             # zoom lento continuo dentro de cada plano
    legenda_y: float = 0.545        # posicao vertical (fracao da altura, short)
    legenda_escala: float = 1.0
    legenda_palavra_a_palavra: bool = False
    legenda_cor_forte: tuple = AMARELO
    legenda_cor_alt: tuple | None = None   # alterna com a cor forte (neon)
    legenda_caixa: tuple | None = None     # (r,g,b,a) caixa atras da legenda
    hud: str = "completo"           # "completo" | "minimo" | "nenhum"
    mascote: bool = True
    carimbos: bool = True
    cartao_titulo: bool = True
    grade: str = "normal"           # normal | quente | frio | neon | vhs | pb
    vinheta: float = 0.0            # 0..1
    faixa: str | None = None        # texto fixo em faixa (ex.: VAZAMENTO)
    faixa_cor: tuple = VERMELHO
    ticker: bool = False            # faixa rolando com o titulo
    musica: float = 0.11
    tipos: tuple = ("short", "long", "teoria")   # onde o estilo pode ser sorteado


ESTILOS: dict = {e.nome: e for e in [
    Estilo("padrao", "O visual que o canal ja tinha: HUD, mascote, carimbos, corte medio.",
           "medio", 1.9, 2.4, 0.12, 1.0, tipos=()),   # aposentado na 3.0: nunca mais sorteado
    Estilo("turbo", "Cortes de ~1s, soco de zoom forte, glitch RGB, 1 palavra por vez, tudo em movimento.",
           "turbo", 1.05, 1.4, 0.20, 1.4, glitch=True, deriva=0.05, legenda_y=0.50,
           legenda_escala=1.25, legenda_palavra_a_palavra=True, musica=0.14,
           tipos=("short", "teoria")),
    Estilo("neon", "Filtro neon (ciano/magenta), legenda alternando cor, pulso de zoom, sem mascote.",
           "rapido", 1.5, 1.9, 0.15, 0.8, glitch=True, deriva=0.04, legenda_y=0.52,
           legenda_cor_forte=CIANO, legenda_cor_alt=MAGENTA, hud="minimo", mascote=False,
           grade="neon", vinheta=0.45, musica=0.13, tipos=("short", "teoria", "long")),
    Estilo("jornal", "Plantao de noticia: faixa URGENTE com titulo rolando, legenda em caixa vermelha.",
           "rapido", 1.7, 2.1, 0.10, 0.7, legenda_y=0.60, legenda_caixa=(190, 24, 24, 235),
           legenda_cor_forte=BRANCO, hud="minimo", mascote=False, ticker=True,
           faixa="URGENTE", tipos=("short", "long")),
    Estilo("cinema", "Mais calmo e 'fixo': cortes lentos, push-in suave, vinheta, tom quente, sem mascote.",
           "lento", 2.8, 3.3, 0.0, 0.0, deriva=0.07, legenda_y=0.70, legenda_escala=0.82,
           legenda_cor_forte=BRANCO, hud="minimo", mascote=False, carimbos=False, grade="quente",
           vinheta=0.7, musica=0.09, tipos=("short", "long", "teoria")),
    Estilo("limpo", "Visual limpo e fixo: so legenda e o contador, cortes medios, sem efeitos.",
           "medio", 2.3, 2.9, 0.0, 0.0, legenda_y=0.62, hud="minimo", mascote=False, carimbos=False,
           cartao_titulo=False, musica=0.10, tipos=("short", "long", "teoria")),
    Estilo("leak", "Arquivo vazado: VHS (grao, linhas, REC), faixa NAO CONFIRMADO, tom frio, glitch.",
           "rapido", 1.6, 2.0, 0.12, 0.6, glitch=True, deriva=0.03, legenda_y=0.60,
           legenda_caixa=(0, 0, 0, 215), legenda_cor_forte=VERDE, hud="minimo", mascote=False,
           grade="vhs", vinheta=0.5, faixa="VAZAMENTO - NAO CONFIRMADO", musica=0.12,
           tipos=("vazamento",)),
]}
PADRAO = ESTILOS["padrao"]


def obter(nome: str | None) -> Estilo:
    return ESTILOS.get((nome or "").strip().lower(), PADRAO)


# --------------------------------------------------------------- pegadas de roteiro

PEGADAS: dict = {
    "numero": "ABRA com um numero ou recorde confirmado que choque; cada frase seguinte entrega um desdobramento desse numero.",
    "pergunta": "ABRA com uma pergunta especifica que o fa se faz; responda so no final, depois de 2 pequenas viradas.",
    "alerta": "tom de ALERTA/urgencia (\"atencao\", \"antes de sexta\"): o que o fa precisa saber ou fazer agora, em passos curtos.",
    "ab": "DEBATE A ou B: apresente as duas opcoes com um argumento factual cada e peca o voto nos comentarios.",
    "lista3": "LISTA de exatamente 3 itens, anunciados como 'primeiro', 'segundo', 'terceiro', com o mais forte por ultimo.",
    "mito": "VERDADE OU MITO: enuncie uma crenca comum, desmonte com fato confirmado e termine com o veredito.",
    "detalhe": "DETALHE QUE QUASE NINGUEM NOTOU: descreva uma cena/elemento confirmado, o que ele significa e peca que o fa reveja.",
    "contagem": "CONTAGEM REGRESSIVA: use o numero exato de dias, diga o que ja e oficial e o que ainda falta ser dito.",
}
PEGADA_VAZAMENTO = "vazamento"
PEGADA_PADRAO = "pergunta"


# --------------------------------------------------------------- pesos (metricas)

def ler_pesos() -> dict:
    try:
        d = json.loads(PESOS_ARQ.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _peso(tabela: dict, nome: str) -> float:
    try:
        return min(2.5, max(0.4, float(tabela.get(nome, 1.0))))
    except Exception:
        return 1.0


def _sortear(rng: random.Random, candidatos: list, tabela: dict, evitar: list) -> str:
    pool = [c for c in candidatos if c not in evitar] or list(candidatos)
    pesos = [_peso(tabela, c) for c in pool]
    return rng.choices(pool, weights=pesos, k=1)[0]


def tipo_do_item(item_id: str, kind: str) -> str:
    if item_id.startswith("vazamento-"):
        return "vazamento"
    if item_id.startswith("teoria-"):
        return "teoria"
    return "long" if kind == "long" else "short"


def planejar_dia(vagas: list, data_iso: str, pesos: dict | None = None) -> list:
    """vagas = [(item_id, kind)] na ordem do dia. Devolve [(estilo, pegada)]
    com rotacao: estilo/pegada nao repetem em itens vizinhos e nenhum passa de
    2 usos no dia (quando houver alternativa)."""
    pesos = ler_pesos() if pesos is None else pesos
    pe, pp = pesos.get("estilos", {}), pesos.get("pegadas", {})
    rng = random.Random(f"gta6-2.0-{data_iso}")
    usados_e, usados_p, saida = [], [], []
    for item_id, kind in vagas:
        tipo = tipo_do_item(item_id, kind)
        try:
            if tipo == "vazamento":
                cand_e = [c for c in ["leak", "leak", "leak", "jornal"] if c not in usados_e[-1:]] or ["leak"]
                estilo = rng.choice(cand_e)
                pegada = PEGADA_VAZAMENTO
            else:
                cand_e = [n for n, e in ESTILOS.items() if tipo in e.tipos]
                evitar = [x for x in usados_e[-1:]] + [x for x in set(usados_e) if usados_e.count(x) >= 2]
                estilo = _sortear(rng, cand_e, pe, evitar)
                cand_p = list(PEGADAS)
                evitar_p = [x for x in usados_p[-2:]] + [x for x in set(usados_p) if usados_p.count(x) >= 2]
                pegada = _sortear(rng, cand_p, pp, evitar_p)
        except Exception:
            estilo, pegada = "padrao", PEGADA_PADRAO
        usados_e.append(estilo)
        usados_p.append(pegada)
        saida.append((estilo, pegada))
    return saida


def pegada_texto(nome: str) -> str:
    return PEGADAS.get(nome, PEGADAS[PEGADA_PADRAO])


# --------------------------------------------------------------- registro de videos

def registrar_video(item, video_id: str, quando_iso: str) -> None:
    """Anota o video publicado em state/videos.json (usado pelo placar)."""
    try:
        try:
            dados = json.loads(VIDEOS_ARQ.read_text(encoding="utf-8"))
        except Exception:
            dados = []
        dados = [d for d in dados if d.get("video_id") != video_id]
        dados.append({
            "video_id": video_id, "item_id": item.item_id, "kind": item.kind,
            "tipo": tipo_do_item(item.item_id, item.kind), "titulo": item.titulo,
            "estilo": getattr(item, "estilo", "") or "padrao",
            "pegada": getattr(item, "pegada", "") or "",
            "publicado_em": quando_iso,
        })
        VIDEOS_ARQ.parent.mkdir(exist_ok=True)
        VIDEOS_ARQ.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:
        print(f"[estilos] aviso: nao consegui registrar {video_id}: {exc!r}")
