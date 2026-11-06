#!/usr/bin/env python3
"""
Roda 1x/dia (ex.: 06:00 via cron/GitHub Actions). Gera o lote do dia
inteiro de uma vez (1 longo + N shorts) e salva em review/<data>.md para
voce aprovar em um unico momento - nao video por video.

Uso: python generate.py [AAAA-MM-DD]
"""
import sys
from datetime import date as date_cls

import config
from content_batch import render_markdown
from notify import notify_batch_ready
from script_generator import generate_daily_content


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else date_cls.today().isoformat()

    review_path = config.REVIEW_DIR / f"{date_str}.md"
    if review_path.exists():
        print(f"[generate] {review_path} ja existe - apague-o antes de gerar de novo.")
        return

    batch = generate_daily_content(date_str)
    review_path.write_text(render_markdown(batch), encoding="utf-8")

    print(f"[generate] lote de {date_str} gerado: {review_path}")
    print(f"[generate] {len(batch.items)} itens (1 longo + {len(batch.items)-1} shorts)")
    notify_batch_ready(date_str, str(review_path))
    print(f"[generate] revise e rode: python approve.py {date_str}")


if __name__ == "__main__":
    main()
