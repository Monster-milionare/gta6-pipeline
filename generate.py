#!/usr/bin/env python3
"""
Roda 1x/dia (ex.: 06:00 via cron/GitHub Actions). Gera o lote do dia
inteiro de uma vez (1 longo + N shorts) e roda a trava de qualidade
automatica (ver quality_gate.py): se passar, o lote ja fica APROVADO e
publish.py publica sozinho, sem voce precisar abrir nada. Se algo soar
arriscado (claim nao verificavel, roteiros parecidos demais, titulo
repetido), o lote fica PENDENTE e os problemas ficam registrados no
proprio arquivo - essa e a unica situacao em que vale a pena olhar.

Uso: python generate.py [AAAA-MM-DD]
"""
import sys
from datetime import date as date_cls

import config
from content_batch import render_markdown
from notify import notify_batch_ready
from quality_gate import auto_aprovar_ou_sinalizar
from script_generator import generate_daily_content

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else date_cls.today().isoformat()

    review_path = config.REVIEW_DIR / f"{date_str}.md"
    if review_path.exists():
        print(f"[generate] {review_path} ja existe - apague-o antes de gerar de novo.")
        return

    batch = generate_daily_content(date_str)
    batch, problemas = auto_aprovar_ou_sinalizar(batch)

    texto = render_markdown(batch)
    if problemas:
        texto += "\n## Observacoes da trava de qualidade (revisao manual necessaria)\n"
        for p in problemas:
            texto += f"- {p}\n"
    review_path.write_text(texto, encoding="utf-8")

    print(f"[generate] lote de {date_str} gerado: {review_path}")
    print(f"[generate] {len(batch.items)} itens (1 longo + {len(batch.items)-1} shorts)")

    if problemas:
        print(f"[generate] trava de qualidade encontrou {len(problemas)} problema(s) - lote ficou PENDENTE:")
        for p in problemas:
            print(f"  - {p}")
        notify_batch_ready(date_str, str(review_path), problemas=problemas)
        print(f"[generate] revise e rode: python approve.py {date_str}")
    else:
        print(f"[generate] trava de qualidade OK - lote APROVADO automaticamente, publish.py ja pode publicar.")

if __name__ == "__main__":
    main()
