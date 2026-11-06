#!/usr/bin/env python3
"""
Aprova o lote do dia de uma vez so, depois que voce (opcionalmente) editou
o arquivo review/<data>.md a mao.

Uso: python approve.py AAAA-MM-DD
"""
import sys

import config
from content_batch import load_batch, save_batch


def main():
    if len(sys.argv) < 2:
        print("Uso: python approve.py AAAA-MM-DD")
        sys.exit(1)

    date_str = sys.argv[1]
    review_path = config.REVIEW_DIR / f"{date_str}.md"
    if not review_path.exists():
        print(f"[approve] {review_path} nao existe. Rode generate.py primeiro.")
        sys.exit(1)

    batch = load_batch(review_path, date_str)
    batch.status = "APROVADO"
    save_batch(review_path, batch)

    print(f"[approve] lote de {date_str} aprovado ({len(batch.items)} itens).")
    print("[approve] publish.py agora pode processar esses itens.")


if __name__ == "__main__":
    main()
