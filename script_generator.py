"""
Gera o lote diário de roteiros (1 longo + N shorts) usando a API grátis da
Groq (console.groq.com — sem cartão de crédito, API compatível com
OpenAI), restrito ao que está em knowledge_base.json — o modelo é
proibido de inventar fatos novos sobre o jogo (evita alucinar "leak"
falso).
"""
import json
import random
from datetime import date as date_cls

from openai import OpenAI

import config
from content_batch import ContentItem, DailyBatch
import unicidade
from quality_gate import (MAX_LONG_WORDS, MAX_SHORT_WORDS, MIN_LONG_WORDS, MIN_SHORT_WORDS,
                          RED_FLAGS)

SYSTEM_PROMPT = """\
Você roteiriza um canal de curiosidades/análise sobre GTA VI.

Regras rígidas:
1. Use APENAS os fatos fornecidos em <fatos_confirmados> abaixo. Nunca
   invente detalhe de jogo, personagem, mecânica ou "vazamento" que não
   esteja lá — mesmo que pareça plausível. Se não houver fato suficiente
   para um ângulo, escolha outro ângulo (opinião, comparação entre
   trailers, contexto de mercado, curiosidade sobre a franquia) em vez de
   inventar conteúdo do jogo.
2. Nunca trate rumor/leak não-oficial como fato.
3. Cada roteiro precisa ter um ângulo/gancho diferente dos outros do
   mesmo lote — nada de repetir a mesma estrutura "Top 5 curiosidades"
   em todos. Varie formato: pergunta, comparação, contagem regressiva,
   reação a um detalhe específico, contexto histórico da franquia etc.
4. Roteiro do vídeo longo: 1300-1900 palavras (dá ~8-12 min falado).
5. Roteiro de cada short: 80-150 palavras (30-60s falado).
6. Escreva em frases curtas e diretas (facilita a narração em TTS e a
   sincronização de legenda frase a frase).
7. Escreva em português do Brasil.
8. Responda SOMENTE com um JSON válido no formato pedido, sem markdown,
   sem texto fora do JSON.
9. Título com NO MÁXIMO 60 caracteres (incluindo espaços). Pesquisa de
   mercado sobre YouTube (Metricool, estudo 2026 com ~800 mil vídeos)
   mostra títulos mais curtos performando consistentemente melhor —
   títulos longos cortam no feed/busca e perdem o gancho.
10. A PRIMEIRA frase do roteiro precisa ser o gancho mais forte do texto
    (uma pergunta, um fato surpreendente ou uma afirmação direta) — nunca
    comece com introdução genérica tipo "Hoje vamos falar sobre...". Os
    primeiros segundos decidem se quem está assistindo continua ou sai.
"""

USER_PROMPT_TEMPLATE = """\
<fatos_confirmados>
{fatos}
</fatos_confirmados>

<temas_ja_publicados>
{historico}
</temas_ja_publicados>
REGRA ABSOLUTA: nenhum titulo ou assunto novo pode repetir ou parafrasear algo da
lista acima nem de outro roteiro deste mesmo lote. Cada um precisa de um tema
DIFERENTE (personagem, mapa, trailer, plataforma, pre-carga, preco, historia
da franquia, comparacao, bastidores, etc.).

Gere o lote de hoje ({data}) com:
- 1 roteiro de vídeo longo
- {n_shorts} roteiros de shorts, cada um com ângulo diferente

Formato de resposta (JSON estrito, sem ```):
{{
  "long": {{"titulo": "...", "roteiro": "..."}},
  "shorts": [
    {{"titulo": "...", "roteiro": "..."}}
  ]
}}
"""


def _load_knowledge_base() -> str:
    if not config.KNOWLEDGE_BASE_FILE.exists():
        raise FileNotFoundError(
            "knowledge_base.json não encontrado. Copie knowledge_base.example.json "
            "e preencha com fatos oficiais confirmados antes de gerar conteúdo."
        )
    return config.KNOWLEDGE_BASE_FILE.read_text(encoding="utf-8")


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    return json.loads(text)


def _chat(client, prompt: str, temperatura: float = 0.9) -> dict:
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temperatura,
    )
    return _extract_json(response.choices[0].message.content)


def _problema_individual(kind: str, titulo: str, roteiro: str):
    """Motivo pelo qual o item nao pode ir ao ar (None = ok)."""
    n = len(roteiro.split())
    if kind == "long" and not (MIN_LONG_WORDS <= n <= MAX_LONG_WORDS):
        return f"roteiro longo com {n} palavras"
    if kind == "short" and not (MIN_SHORT_WORDS <= n <= MAX_SHORT_WORDS):
        return f"short com {n} palavras"
    if not titulo.strip():
        return "titulo vazio"
    baixo = roteiro.lower()
    for flag in RED_FLAGS:
        if flag in baixo:
            return f"expressao de claim nao verificavel ('{flag}')"
    return None


def _validar(kind: str, titulo: str, roteiro: str, historico: list, aceitos: list):
    """None = item aprovado; senao o motivo da recusa."""
    motivo = _problema_individual(kind, titulo, roteiro)
    if motivo:
        return motivo
    return unicidade.achar_repeticao(titulo, roteiro, historico + aceitos)


def _regenerar_um(client, kind: str, fatos: str, proibidos: list, motivo: str):
    """Pede UM roteiro novo, com tema diferente de tudo que ja existe."""
    alvo = ("1 roteiro de video longo (1300-1900 palavras)" if kind == "long"
            else "1 roteiro de short (80-150 palavras)")
    lista = "\n".join(f"- {t}" for t in proibidos[-80:]) or "(nenhum)"
    prompt = (
        f"<fatos_confirmados>\n{fatos}\n</fatos_confirmados>\n\n"
        f"<temas_ja_usados>\n{lista}\n</temas_ja_usados>\n\n"
        f"O roteiro anterior foi recusado: {motivo}. Gere {alvo} sobre um assunto "
        f"COMPLETAMENTE DIFERENTE de todos os temas ja usados acima. Formato "
        f'(JSON estrito): {{"titulo": "...", "roteiro": "..."}}'
    )
    data = _chat(client, prompt, temperatura=1.0)
    return str(data["titulo"]).strip(), str(data["roteiro"]).strip()


def generate_daily_content(date_str: str | None = None) -> DailyBatch:
    date_str = date_str or date_cls.today().isoformat()
    fatos = _load_knowledge_base()

    if not config.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY não configurada no .env. Crie uma chave grátis em "
            "https://console.groq.com/keys (não pede cartão)."
        )

    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

    # Todo o historico (qualquer dia): nada que ja foi feito pode voltar.
    historico = unicidade.carregar_historico(excluir_data=date_str)
    titulos_hist = [t for _i, t, _r in historico]
    lista_hist = "\n".join(f"- {t}" for t in titulos_hist[-80:]) or "(nenhum ainda)"

    prompt = USER_PROMPT_TEMPLATE.format(
        fatos=fatos, data=date_str, n_shorts=config.SHORTS_PER_DAY, historico=lista_hist)
    data = _chat(client, prompt)

    candidatos = [("long", f"long-{date_str}", data["long"]["titulo"], data["long"]["roteiro"])]
    for i, short in enumerate(data["shorts"], start=1):
        candidatos.append(("short", f"short-{date_str}-{i:02d}", short["titulo"], short["roteiro"]))

    itens, aceitos, descartados = [], [], []
    for kind, item_id, titulo, roteiro in candidatos:
        titulo, roteiro = str(titulo).strip(), str(roteiro).strip()
        motivo = _validar(kind, titulo, roteiro, historico, aceitos)
        tentativa = 0
        while motivo and tentativa < 4:
            tentativa += 1
            print(f"[generate] {item_id} recusado ({motivo}) - regenerando ({tentativa}/4).", flush=True)
            proibidos = titulos_hist + [a[1] for a in aceitos] + [titulo]
            try:
                titulo, roteiro = _regenerar_um(client, kind, fatos, proibidos, motivo)
            except Exception as exc:
                print(f"[generate] falha ao regenerar {item_id}: {exc!r}", flush=True)
                continue
            motivo = _validar(kind, titulo, roteiro, historico, aceitos)
        if motivo:
            print(f"[generate] {item_id} DESCARTADO: {motivo}", flush=True)
            descartados.append(f"{item_id}: {motivo}")
            continue
        aceitos.append((item_id, titulo, roteiro))
        itens.append(ContentItem(item_id=item_id, kind=kind, titulo=titulo, roteiro=roteiro))

    if not itens:
        raise RuntimeError("Nenhum roteiro valido e inedito foi gerado: " + "; ".join(descartados))
    batch = DailyBatch(date=date_str, status="PENDENTE", items=itens)
    batch.descartados = descartados  # so informativo (generate.py anota no arquivo)
    return batch
