"""Aviso simples por e-mail de que o lote do dia esta pronto pra revisao."""
import smtplib
from email.mime.text import MIMEText

import config


def notify_batch_ready(date_str: str, review_path: str) -> None:
    if not (config.SMTP_HOST and config.SMTP_USER and config.NOTIFY_TO_EMAIL):
        print(f"[notify] SMTP nao configurado - lote salvo em {review_path}")
        return

    body = (
        f"Lote de conteudo de {date_str} esta pronto para revisao.\n\n"
        f"Arquivo: {review_path}\n\n"
        f"Abra, edite o que quiser, e rode:\n"
        f"    python approve.py {date_str}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"[GTA VI pipeline] Lote de {date_str} pronto para aprovar"
    msg["From"] = config.SMTP_USER
    msg["To"] = config.NOTIFY_TO_EMAIL

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
    print(f"[notify] e-mail enviado para {config.NOTIFY_TO_EMAIL}")
