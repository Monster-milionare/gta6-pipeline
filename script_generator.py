"""
Gera o lote diário de roteiros (1 longo + N shorts) usando a API grátis da
Groq (console.groq.com — sem cartão de crédito, API compatível com
OpenAI), restrito ao que está em knowledge_base.json — o modelo é
proibido de inventar fatos novos sobre o jogo (evita alucinar "leak"
falso).
"""
import json
from datetime import date as date_cls

from openai import OpenAI

import config
from content_batch import ContentItem, DailyBatch

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


def generate_daily_content(date_str: str | None = None) -> DailyBatch:
    date_str = date_str or date_cls.today().isoformat()
    fatos = _load_knowledge_base()

    if not config.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY não configurada no .env. Crie uma chave grátis em "
            "https://console.groq.com/keys (não pede cartão)."
        )

    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

    prompt = USER_PROMPT_TEMPLATE.format(fatos=fatos, data=date_str, n_shorts=config.SHORTS_PER_DAY)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    data = _extract_json(response.choices[0].message.content)

    items = [
        ContentItem(
            item_id=f"long-{date_str}",
            kind="long",
            titulo=data["long"]["titulo"],
            roteiro=data["long"]["roteiro"],
        )
    ]
    for i, short in enumerate(data["shorts"], start=1):
        items.append(
            ContentItem(
                item_id=f"short-{date_str}-{i:02d}",
                kind="short",
                titulo=short["titulo"],
                roteiro=short["roteiro"],
            )
        )

    return DailyBatch(date=date_str, status="PENDENTE", items=items)
