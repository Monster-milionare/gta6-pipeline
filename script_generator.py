"""
Gera o lote diário de roteiros (1 longo + N shorts) usando a API grátis da
Groq (console.groq.com — sem cartão de crédito, API compatível com
OpenAI), restrito ao que está em knowledge_base.json — o modelo é
proibido de inventar fatos novos sobre o jogo (evita alucinar "leak"
falso).
"""
import json
import time
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

def _load_knowledge_base() -> str:
    if not config.KNOWLEDGE_BASE_FILE.exists():
        raise FileNotFoundError(
            "knowledge_base.json não encontrado. Copie knowledge_base.example.json "
            "e preencha com fatos oficiais confirmados antes de gerar conteúdo."
        )
    return config.KNOWLEDGE_BASE_FILE.read_text(encoding="utf-8")


# Modelos de reserva: se o principal falhar em gerar JSON valido (erro 400
# "Failed to generate JSON", que ja derrubou a geracao do lote), tenta o proximo.
MODELOS = [config.GROQ_MODEL, "llama-3.3-70b-versatile", "openai/gpt-oss-20b"]

# Um formato/angulo diferente por vaga do dia (rotaciona com a data), pra o
# lote nascer variado em vez de depender so do modelo "lembrar" de variar.
ANGULOS = [
    "pergunta provocativa que o torcedor de GTA faria",
    "comparacao entre dois trailers ou dois jogos da franquia",
    "contagem regressiva para o lancamento (19/11/2026) e o que fazer ate la",
    "curiosidade sobre um personagem confirmado",
    "um lugar/cenario do mapa mostrado nos trailers",
    "plataformas, pre-carga e preparacao tecnica",
    "historia da franquia GTA e como chegou ate aqui",
    "reacao a um detalhe especifico de um trailer",
    "numeros e recordes do marketing (so os confirmados)",
    "perguntas e respostas rapidas sobre o que ja foi confirmado",
    "o que a Rockstar ja disse oficialmente e o que ainda nao disse",
    "tour pelas cenas do trailer, uma a uma",
]


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    ini, fim = text.find("{"), text.rfind("}")
    if ini == -1 or fim == -1:
        raise ValueError("resposta sem JSON")
    return json.loads(text[ini:fim + 1], strict=False)


def _chat(client, prompt: str, temperatura: float = 0.9) -> dict:
    """Chama o modelo ate conseguir um JSON valido: alterna com/sem modo JSON
    estrito, baixa a temperatura e troca de modelo a cada falha."""
    ultimo = None
    for tentativa in range(6):
        modelo = MODELOS[min(tentativa // 2, len(MODELOS) - 1)]
        kwargs = dict(
            model=modelo,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=max(0.5, temperatura - 0.1 * tentativa),
            max_tokens=7000,
        )
        if tentativa % 2 == 0:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(**kwargs)
            return _extract_json(resp.choices[0].message.content)
        except Exception as exc:
            ultimo = exc
            print(f"[generate] chamada ao modelo {modelo} falhou ({str(exc)[:160]}) - tentativa {tentativa + 1}/6", flush=True)
            time.sleep(4 + 4 * tentativa)
    raise ultimo


def _problema_individual(kind: str, titulo: str, roteiro: str):
    """Motivo pelo qual o item nao pode ir ao ar (None = ok)."""
    n = len(roteiro.split())
    if kind == "long" and not (MIN_LONG_WORDS <= n <= MAX_LONG_WORDS):
        return f"roteiro longo com {n} palavras (precisa de {MIN_LONG_WORDS}-{MAX_LONG_WORDS})"
    if kind == "short" and not (MIN_SHORT_WORDS <= n <= MAX_SHORT_WORDS):
        return f"short com {n} palavras (precisa de {MIN_SHORT_WORDS}-{MAX_SHORT_WORDS})"
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


def _gerar_um(client, kind: str, fatos: str, proibidos: list, angulo: str, motivo: str | None):
    """Pede UM roteiro (cada item em sua propria chamada: respostas curtas
    quase nunca quebram o JSON, e cada uma ja nasce sabendo o que e proibido)."""
    alvo = ("1 roteiro de video longo (1300-1900 palavras)" if kind == "long"
            else "1 roteiro de short (80-150 palavras)")
    lista = "\n".join(f"- {t}" for t in proibidos[-80:]) or "(nenhum ainda)"
    aviso = f"\nA tentativa anterior foi recusada: {motivo}. Corrija isso.\n" if motivo else ""
    prompt = (
        f"<fatos_confirmados>\n{fatos}\n</fatos_confirmados>\n\n"
        f"<temas_ja_usados>\n{lista}\n</temas_ja_usados>\n"
        f"REGRA ABSOLUTA: o assunto/titulo novo nao pode repetir nem parafrasear nada "
        f"da lista acima.\n{aviso}\n"
        f"Gere {alvo}. Formato/angulo sugerido: {angulo}. Responda so com JSON: "
        f'{{"titulo": "...", "roteiro": "..."}}'
    )
    data = _chat(client, prompt)
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

    vagas = [("long", f"long-{date_str}")] + [
        ("short", f"short-{date_str}-{i:02d}") for i in range(1, config.SHORTS_PER_DAY + 1)]
    deslocamento = date_cls.fromisoformat(date_str).toordinal()

    itens, aceitos, descartados = [], [], []
    for n, (kind, item_id) in enumerate(vagas):
        angulo = ANGULOS[(deslocamento + n * 5) % len(ANGULOS)]
        motivo, recusados, ok = None, [], False
        for tentativa in range(1, 6):
            proibidos = titulos_hist + [a[1] for a in aceitos] + recusados
            try:
                titulo, roteiro = _gerar_um(client, kind, fatos, proibidos, angulo, motivo)
            except Exception as exc:
                print(f"[generate] {item_id}: falha ao gerar ({str(exc)[:160]}) - tentativa {tentativa}/5", flush=True)
                motivo = f"erro de geracao: {str(exc)[:80]}"
                continue
            recusa = _validar(kind, titulo, roteiro, historico, aceitos)
            if not recusa:
                aceitos.append((item_id, titulo, roteiro))
                itens.append(ContentItem(item_id=item_id, kind=kind, titulo=titulo, roteiro=roteiro))
                print(f"[generate] {item_id} ok: {titulo}", flush=True)
                ok = True
                break
            print(f"[generate] {item_id} recusado ({recusa}) - tentativa {tentativa}/5", flush=True)
            recusados.append(titulo)
            motivo = recusa
        if not ok:
            print(f"[generate] {item_id} DESCARTADO: {motivo}", flush=True)
            descartados.append(f"{item_id}: {motivo}")

    if not itens:
        raise RuntimeError("Nenhum roteiro valido e inedito foi gerado: " + "; ".join(descartados))
    batch = DailyBatch(date=date_str, status="PENDENTE", items=itens)
    batch.descartados = descartados  # so informativo (generate.py anota no arquivo)
    return batch
