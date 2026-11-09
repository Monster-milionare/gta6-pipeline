"""Configuração central do pipeline. Lê variáveis do .env. Versão R$0."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
REVIEW_DIR = BASE_DIR / "review"
STATE_DIR = BASE_DIR / "state"
ASSETS_DIR = BASE_DIR / "assets"  # broll oficial (screenshots de trailer), etc.

REVIEW_DIR.mkdir(exist_ok=True)
STATE_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

KNOWLEDGE_BASE_FILE = BASE_DIR / "knowledge_base.json"

# --- Volume diário ---
# ATENÇÃO: a cota GRÁTIS da YouTube Data API é 10.000 unidades/dia e cada
# upload custa 1.600 unidades → só dá pra automatizar ~6 uploads/dia até
# você pedir aumento de cota (grátis, mas precisa aprovação do Google).
# Comece aqui e suba pra 8 shorts só depois que a cota for aumentada, ou
# publique os shorts excedentes manualmente (upload manual não gasta cota).
SHORTS_PER_DAY = 5
LONG_VIDEOS_PER_DAY = 1
LONG_VIDEO_MIN_DURATION_SEC = 8 * 60
LONG_VIDEO_MAX_DURATION_SEC = 12 * 60

# --- Roteiro (LLM) — Groq tem tier grátis sem cartão (14.400 req/dia) ---
# (Gemini também tem tier grátis, mas exige vincular faturamento em
# projetos novos do Google Cloud — testamos e bateu nessa trava; Groq não
# pede cartão em nenhuma etapa.)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# --- Voz (TTS) — edge-tts é grátis, sem chave de API ---
# pt-BR-MacerioMultilingualNeural é a geração mais nova de voz neural
# multilíngue da Microsoft pra PT-BR (mais natural/expressiva que as vozes
# "clássicas" como a AntonioNeural antiga). tts.py já tem fallback
# automático pra AntonioNeural se essa não existir no catálogo do
# edge-tts algum dia - então o default aqui pode mirar na melhor voz sem
# risco de travar o pipeline.
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "pt-BR-MacerioMultilingualNeural")

# --- YouTube (OAuth — grátis, ver upload.py) ---
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "token.json")

# --- Notificação por e-mail (opcional, Gmail com senha de app é grátis) ---
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFY_TO_EMAIL = os.getenv("NOTIFY_TO_EMAIL")
