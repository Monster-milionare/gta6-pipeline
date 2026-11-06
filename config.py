"""Configuracao central do pipeline. Le variaveis do .env. Versao R$0."""
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

# --- Volume diario ---
# ATENCAO: a cota GRATIS da YouTube Data API e 10.000 unidades/dia e cada
# upload custa 1.600 unidades -> so da pra automatizar ~6 uploads/dia ate
# voce pedir aumento de cota (gratis, mas precisa aprovacao do Google).
# Comece aqui e suba pra 8 shorts so depois que a cota for aumentada, ou
# publique os shorts excedentes manualmente (upload manual nao gasta cota).
SHORTS_PER_DAY = 5
LONG_VIDEOS_PER_DAY = 1
LONG_VIDEO_MIN_DURATION_SEC = 8 * 60
LONG_VIDEO_MAX_DURATION_SEC = 12 * 60

# --- Roteiro (LLM) - Groq tem tier gratis sem cartao (14.400 req/dia) ---
# (Gemini tambem tem tier gratis, mas exige vincular faturamento em
# projetos novos do Google Cloud - testamos e bateu nessa trava; Groq nao
# pede cartao em nenhuma etapa.)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# --- Voz (TTS) - edge-tts e gratis, sem chave de API ---
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "pt-BR-AntonioNeural")

# --- YouTube (OAuth - gratis, ver upload.py) ---
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "token.json")

# --- Notificacao por e-mail (opcional, Gmail com senha de app e gratis) ---
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFY_TO_EMAIL = os.getenv("NOTIFY_TO_EMAIL")
