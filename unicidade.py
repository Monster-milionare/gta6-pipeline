"""
Garantia de que o canal NUNCA repete tema.

Tres camadas usam este modulo:
1. script_generator.py - ao gerar o lote, compara cada roteiro com TODO o
   historico (qualquer dia) e com os outros do mesmo lote; repetido e
   regenerado com outro angulo (ou descartado se nao der).
2. publish.py - ultima trava antes de subir: se o item e igual a algo que
   ja foi publicado (de qualquer dia), ele e pulado em vez de ir ao ar.
3. quality_gate.py continua olhando o lote como um todo.

A comparacao ignora acento, pontuacao e palavras genericas, entao
"Trailer 1: o que o primeiro video revelou?" e
"O que o primeiro vídeo do Trailer 1 revelou" contam como a mesma coisa.
"""
import difflib
import re
import unicodedata

import config

LIMITE_TITULO = 0.60
LIMITE_GANCHO = 0.70
LIMITE_ROTEIRO_UNI = 0.55
LIMITE_ROTEIRO_TRI = 0.12

# Palavras que nao dizem nada sobre o TEMA (todo titulo do canal tem "GTA VI").
_GENERICAS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "que", "se", "por", "para", "pra", "com", "sem", "ao", "aos", "ja", "mais",
    "ate", "como", "sobre", "foi", "vai", "sao", "ser", "tem", "ter", "isso", "essa", "esse",
    "voce", "seu", "sua", "nao", "mas", "ou", "so", "tudo", "todo", "toda", "muito", "ainda",
    "gta", "vi", "rockstar", "games", "jogo", "novo", "nova", "canal", "video",
}


def _sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def normalizar(txt: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", _sem_acento(txt.lower())).strip()


def _tokens(txt: str) -> list:
    return [t for t in normalizar(txt).split() if t not in _GENERICAS and (len(t) > 1 or t.isdigit())]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def sim_titulo(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    jac = _jaccard(ta, tb)
    contido = (len(ta & tb) / min(len(ta), len(tb))) if ta and tb and min(len(ta), len(tb)) >= 3 else 0.0
    razao = difflib.SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()
    return max(jac, contido * 0.95, razao * 0.8)


def _gancho(roteiro: str) -> str:
    primeira = re.split(r"(?<=[.!?])\s+", roteiro.strip(), maxsplit=1)[0]
    return primeira


def sim_gancho(a: str, b: str) -> float:
    """So conta palavras de conteudo (frases com a mesma moldura, tipo 'Voce
    sabia que...?', nao sao o mesmo gancho)."""
    return _jaccard(set(_tokens(_gancho(a))), set(_tokens(_gancho(b))))


def _trigramas(txt: str) -> set:
    t = _tokens(txt)
    return {tuple(t[i:i + 3]) for i in range(len(t) - 2)}


def sim_roteiro(a: str, b: str) -> tuple:
    uni = _jaccard(set(_tokens(a)), set(_tokens(b)))
    tri = _jaccard(_trigramas(a), _trigramas(b))
    return uni, tri


def _entidades(txt: str) -> set:
    """Nomes proprios e numeros do roteiro (Lucia, Vice City, Leonida, 150 GB...)
    - e o que mais identifica 'sobre o que' o video e, mesmo reescrito."""
    saida = set()
    for frase in re.split(r"(?<=[.!?])\s+", txt.strip()):
        primeira = frase.lstrip()[:1]
        for m in re.finditer(r"\b[A-ZÀ-Ú][\wÀ-ú]+|\b\d[\d.,]*\b", frase):
            if m.start() <= len(frase) - len(frase.lstrip()) and not m.group().isdigit() and primeira.isupper():
                continue  # primeira palavra da frase (maiuscula so por ser inicio)
            n = normalizar(m.group())
            if n and n not in _GENERICAS:
                saida.add(n)
    return saida


def motivo_repeticao(titulo: str, roteiro: str, outro_titulo: str, outro_roteiro: str = ""):
    """Retorna o motivo (texto) se forem o mesmo tema; None se forem diferentes."""
    s = sim_titulo(titulo, outro_titulo)
    if s >= LIMITE_TITULO:
        return f"titulo parecido ({s:.0%}) com '{outro_titulo}'"
    if roteiro and outro_roteiro:
        g = sim_gancho(roteiro, outro_roteiro)
        if g >= LIMITE_GANCHO:
            return f"mesmo gancho ({g:.0%}) de '{outro_titulo}'"
        uni, tri = sim_roteiro(roteiro, outro_roteiro)
        ent = _jaccard(_entidades(roteiro), _entidades(outro_roteiro))
        if ent >= 0.60 and uni >= 0.30:
            return f"mesmo assunto (nomes {ent:.0%}, palavras {uni:.0%}) de '{outro_titulo}'"
        if uni >= LIMITE_ROTEIRO_UNI and tri >= LIMITE_ROTEIRO_TRI:
            return f"roteiro quase igual (palavras {uni:.0%}, trechos {tri:.0%}) ao de '{outro_titulo}'"
    return None


def carregar_historico(excluir_data: str | None = None, so_publicados: bool = False) -> list:
    """[(item_id, titulo, roteiro)] de TODOS os lotes em review/ (qualquer dia)."""
    from content_batch import load_batch

    saida = []
    if not config.REVIEW_DIR.exists():
        return saida
    for arq in sorted(config.REVIEW_DIR.glob("*.md")):
        if excluir_data and arq.stem == excluir_data:
            continue
        try:
            lote = load_batch(arq, arq.stem)
        except Exception:
            continue
        for it in lote.items:
            if so_publicados and not it.publicado:
                continue
            saida.append((it.item_id, it.titulo, it.roteiro))
    return saida


def achar_repeticao(titulo: str, roteiro: str, historico: list, ignorar_id: str | None = None):
    for item_id, t, r in historico:
        if ignorar_id and item_id == ignorar_id:
            continue
        motivo = motivo_repeticao(titulo, roteiro, t, r)
        if motivo:
            return f"{motivo} [{item_id}]"
    return None
