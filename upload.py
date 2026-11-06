"""
Upload agendado pro YouTube via YouTube Data API v3.

Setup (uma vez so, manual):
1. Crie um projeto no Google Cloud Console e ative a "YouTube Data API v3".
2. Crie credenciais OAuth (tipo "Desktop app") e baixe o client_secret.json
   pra pasta do projeto.
3. Na primeira execucao, um link de autorizacao vai abrir/ser impresso;
   autorize com a conta dona do canal. Isso salva token.json e nao pede
   de novo (o token e renovado sozinho).
"""
import os
from pathlib import Path

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials() -> Credentials:
    token_path = Path(config.YOUTUBE_TOKEN_FILE)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        elif os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            # Rodando no GitHub Actions: nao tem navegador pra autorizar do
            # zero aqui. token.json (com refresh_token valido) precisa ter
            # sido gerado 1x localmente e restaurado a partir do secret
            # YOUTUBE_TOKEN_JSON antes de chamar isto - ver README.
            raise RuntimeError(
                "token.json ausente/invalido em ambiente sem navegador. Gere-o "
                "1x na sua maquina (rode publish.py localmente uma vez) e "
                "salve o conteudo no secret YOUTUBE_TOKEN_JSON do repositorio."
            )
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    publish_at_iso: str | None = None,
    is_short: bool = False,
) -> str:
    """publish_at_iso: ex. '2026-11-10T14:00:00Z' para agendar; None publica direto."""
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    status = {"selfDeclaredMadeForKids": False}
    if publish_at_iso:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at_iso
    else:
        status["privacyStatus"] = "public"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "20",  # Gaming
        },
        "status": status,
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return response["id"]
