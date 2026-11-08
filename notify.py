"""Aviso simples por e-mail de que o lote do dia esta pronto (ou precisa
de revisao porque a trava de qualidade automatica achou algo suspeito -
ver quality_gate.py)."""
import smtplib
from email.mime.text import MIMEText

import config

def notify_batch_ready(date_str: str, review_path: str, problemas: list[str] | None = None) -> None:
    if not (config.SMTP_HOST and config.SMTP_USER and config.NOTIFY_TO_EMAIL):
        if problemas:
            print(f"[notify] SMTP nao configurado - lote de {date_str} ficou PENDENTE em {review_path} (revisao manual necessaria).")
        else:
            print(f"[notify] SMTP nao configurado - lote salvo em {review_path}")
        return

    if problemas:
        assunto = f"[GTA VI pipeline] Lote de {date_str} precisa de revisao"
        lista = "\n".join(f"- {p}" for p in problemas)
        body = (
            f"A trava de qualidade automatica achou algo suspeito no lote de {date_str} "
            f"e NAO aprovou sozinho (fica pendente ate alguem revisar):\n\n"
            f"{lista}\n\n"
            f"Arquivo: {review_path}\n\n"
            f"Edite o que precisar e rode:\n"
            f"    python approve.py {date_str}\n"
        )
    else:
        assunto = f"[GTA VI pipeline] Lote de {date_str} aprovado automaticamente"
        body = (
            f"Lote de conteudo de {date_str} passou na trava de qualidade e ja foi "
            f"aprovado sozinho - publish.py vai publicar sem precisar de nada seu.\n\n"
            f"Arquivo: {review_path}\n"
        )

    msg = MIMEText(body)
    msg["Subject"] = assunto
    msg["From"] = config.SMTP_USER
    msg["To"] = config.NOTIFY_TO_EMAIL

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
    print(f"[notify] e-mail enviado para {config.NOTIFY_TO_EMAIL}")
