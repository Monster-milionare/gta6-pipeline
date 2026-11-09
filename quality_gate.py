"""
Trava de qualidade automatica - substitui a revisao manual diaria por um
conjunto de checagens programaticas, pra reduzir o risco do padrao que o
sistema anti-spam do YouTube (S-CTS) usa pra agrupar/banir canais em
massa: alta frequencia nao-humana + mesmo padrao semantico repetido.

Pipeline 100% autonomo (sem humano no loop, por pedido explicito do
dono do canal): o lote do dia e SEMPRE aprovado sozinho (Status:
APROVADO) e publish.py processa sem ninguem precisar abrir nada.

A unica excecao e um BLOQUEANTE real: uma claim que parece vazamento/
rumor nao verificavel (ver RED_FLAGS) - o mesmo tipo de coisa que
motivou a notificacao extrajudicial da Take-Two contra outros criadores.
Isso ainda trava o lote em PENDENTE, porque e risco legal, nao so
qualidade de texto.

Problemas "leves" (roteiro fora da faixa de palavras ideal, titulo
parecido com um anterior, roteiros parecidos demais dentro do mesmo
lote) NAO bloqueiam mais a aprovacao - ficam so registrados em
"## Observacoes da trava de qualidade" no proprio review/<data>.md,
pra quem quiser dar uma olhada depois, sem travar a publicacao.
"""
import difflib
import re

import config
from content_batch import DailyBatch

# Expressoes que indicam uma claim nao-verificavel (vazamento, fonte
# anonima, "dizem que") - sinal de que o roteiro pode estar inventando
# algo fora do knowledge_base.json, mesmo com a instrucao do prompt em
# script_generator.py. Melhor travar e avisar do que arriscar o tipo de
# "leak falso" que motivou a notificacao da Take-Two contra outros
# criadores (ver README). Este e o UNICO tipo de problema que ainda
# bloqueia a aprovacao automatica (ver avaliar_lote).
RED_FLAGS = [
    "vazou", "vazamento exclusivo", "fonte anonima", "fonte anônima",
    "segundo um insider", "ouvi dizer", "dizem que",
    "nao e oficial, mas", "não é oficial, mas", "ainda nao confirmado, mas",
    "ainda não confirmado, mas",
]

MIN_LONG_WORDS, MAX_LONG_WORDS = 1100, 2200
MIN_SHORT_WORDS, MAX_SHORT_WORDS = 60, 200

# Acima desse limiar, dois roteiros do MESMO lote soam como "a mesma
# receita" (risco de padrao semantico repetido). Abaixo de 1.0 sempre,
# porque dois textos identicos teriam ratio 1.0.
SIMILARITY_LIMIT_LOTE = 0.62

# Pra titulo entre DIAS diferentes: mais tolerante (0.0-1.0), so pega
# titulo quase idêntico repetido dia apos dia.
SIMILARITY_LIMIT_HISTORICO = 0.80
DIAS_HISTORICO = 7

def _wordcount(texto: str) -> int:
    return len(texto.split())

def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _historico_titulos(data_atual: str, dias: int = DIAS_HISTORICO) -> list[str]:
    """Titulos de lotes anteriores (pra pegar repeticao entre dias, nao so
    dentro do mesmo lote)."""
    titulos = []
    if not config.REVIEW_DIR.exists():
        return titulos
    for arq in sorted(config.REVIEW_DIR.glob("*.md"), reverse=True):
        if arq.stem == data_atual:
            continue
        if len(titulos) >= dias * 6:  # ~6 itens/dia, corta cedo
            break
        texto = arq.read_text(encoding="utf-8")
        titulos += re.findall(r"^Titulo:\s*(.+)$", texto, re.MULTILINE)
    return titulos

def avaliar_lote(batch: DailyBatch) -> tuple[list[str], list[str]]:
    """Retorna (bloqueantes, avisos).

    bloqueantes: risco real (claim nao verificavel) - trava o lote em
    PENDENTE, porque e risco legal/reputacional, nao so estetico.
    avisos: problemas leves (tamanho de roteiro, titulo/roteiro
    parecido) - so ficam registrados no arquivo, nao travam nada.
    """
    bloqueantes = []
    avisos = []

    for item in batch.items:
        n = _wordcount(item.roteiro)
        if item.kind == "long" and not (MIN_LONG_WORDS <= n <= MAX_LONG_WORDS):
            avisos.append(
                f"{item.item_id}: roteiro longo com {n} palavras "
                f"(esperado {MIN_LONG_WORDS}-{MAX_LONG_WORDS})."
            )
        if item.kind == "short" and not (MIN_SHORT_WORDS <= n <= MAX_SHORT_WORDS):
            avisos.append(
                f"{item.item_id}: short com {n} palavras "
                f"(esperado {MIN_SHORT_WORDS}-{MAX_SHORT_WORDS})."
            )

        texto_lower = item.roteiro.lower()
        for flag in RED_FLAGS:
            if flag in texto_lower:
                bloqueantes.append(
                    f"{item.item_id}: contem expressao de claim nao verificavel "
                    f"('{flag}') - confirme que e so um fato do knowledge_base.json."
                )

    # similaridade entre itens do MESMO lote (mesmo angulo/formato repetido)
    for i in range(len(batch.items)):
        for j in range(i + 1, len(batch.items)):
            a, b = batch.items[i], batch.items[j]
            sim = _similar(a.roteiro, b.roteiro)
            if sim >= SIMILARITY_LIMIT_LOTE:
                avisos.append(
                    f"{a.item_id} e {b.item_id}: roteiros {sim:.0%} similares "
                    f"(angulo repetido dentro do mesmo lote)."
                )

    # titulo muito parecido com algo ja publicado em dias anteriores
    historico = _historico_titulos(batch.date)
    for item in batch.items:
        for titulo_antigo in historico:
            if _similar(item.titulo, titulo_antigo) >= SIMILARITY_LIMIT_HISTORICO:
                avisos.append(
                    f"{item.item_id}: titulo muito parecido com um ja usado "
                    f"('{titulo_antigo.strip()}')."
                )
                break

    return bloqueantes, avisos

def auto_aprovar_ou_sinalizar(batch: DailyBatch) -> tuple[DailyBatch, list[str]]:
    """Aplica a trava de qualidade e decide o Status do lote.

    Pipeline autonomo: so um BLOQUEANTE real (claim nao verificavel,
    risco legal) deixa o lote PENDENTE. Qualquer outro problema
    ("aviso" - tamanho de roteiro, titulo parecido) e so registrado no
    arquivo, mas o lote sai APROVADO mesmo assim e publish.py roda sem
    precisar de ninguem aprovar manualmente.
    """
    bloqueantes, avisos = avaliar_lote(batch)
    batch.status = "PENDENTE" if bloqueantes else "APROVADO"
    # bloqueantes primeiro (mais importante), depois avisos - tudo fica
    # registrado no arquivo de qualquer forma, bloqueando ou nao.
    return batch, bloqueantes + avisos
