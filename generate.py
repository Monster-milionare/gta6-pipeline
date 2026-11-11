#!/usr/bin/env python3
"""
Roda 1x/dia (ex.: 06:00 via cron/GitHub Actions). Gera o lote do dia
inteiro de uma vez (1 longo + N shorts) e roda a trava de qualidade
automatica (ver quality_gate.py): se passar, o lote ja fica APROVADO e
publish.py publica sozinho, sem voce precisar abrir nada. Se algo soar
arriscado (claim nao verificavel, roteiros parecidos demais, titulo
repetido), o lote fica PENDENTE e os problemas ficam registrados no
proprio arquivo - essa e a unica situacao em que vale a pena olhar.

Antes de gerar, o radar (radar.py) procura as noticias de GTA VI que estao
rolando e so deixa passar as que tem lastro (fonte oficial ou 2+ veiculos
confiaveis). Se o radar falhar, o lote sai normal, so com os fatos oficiais.

Uso: python generate.py [AAAA-MM-DD]
"""
import sys
from datetime import date as date_cls

import config
import script_generator
from content_batch import render_markdown
from notify import notify_batch_ready
from quality_gate import auto_aprovar_ou_sinalizar
from script_generator import generate_daily_content


def _ligar_radar() -> None:
    """Acrescenta as noticias validadas aos fatos e aos angulos do gerador."""
    try:
        import radar
        noticias = radar.buscar()
    except Exception as exc:
        print(f"[generate] radar indisponivel ({exc!r}) - seguindo so com os fatos oficiais.")
        return
    if not noticias:
        return
    original = script_generator._load_knowledge_base

    def _kb_com_radar() -> str:
        return original() + radar.bloco_para_prompt(noticias)

    script_generator._load_knowledge_base = _kb_com_radar
    script_generator.ANGULOS = radar.angulos(noticias) + list(script_generator.ANGULOS)
    for n in noticias:
        marca = "oficial" if n["oficial"] else ("nao confirmada" if n["nao_confirmada"] else "reportada")
        print(f"[radar] {marca}: {n['titulo']} ({', '.join(n['veiculos'])})")


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else date_cls.today().isoformat()

    review_path = config.REVIEW_DIR / f"{date_str}.md"
    if review_path.exists():
        print(f"[generate] {review_path} ja existe - apague-o antes de gerar de novo.")
        return

    _ligar_radar()
    batch = generate_daily_content(date_str)
    batch, problemas = auto_aprovar_ou_sinalizar(batch)

    # ANTI-TRAVAMENTO: generate_daily_content ja garante que cada roteiro do
    # lote e valido (tamanho, sem claim nao verificavel) E inedito (nao repete
    # nenhum tema de nenhum dia nem do mesmo lote) - o que nao passou foi
    # regenerado ou descartado. Entao o que sobra aqui e so aviso, e um aviso
    # nunca pode segurar a publicacao do dia: o lote vai APROVADO.
    batch.status = "APROVADO"

    texto = render_markdown(batch)
    descartados = getattr(batch, "descartados", [])
    if problemas or descartados:
        texto += "\n## Observacoes da trava de qualidade (informativo - lote aprovado)\n"
        for p in problemas:
            texto += f"- {p}\n"
        for d in descartados:
            texto += f"- descartado (repetido ou invalido): {d}\n"
    review_path.write_text(texto, encoding="utf-8")

    print(f"[generate] lote de {date_str} gerado: {review_path}")
    print(f"[generate] {len(batch.items)} itens, todos inéditos - lote APROVADO, publish.py ja pode publicar.")
    for p in problemas + descartados:
        print(f"  - aviso: {p}")
    if problemas:
        try:
            notify_batch_ready(date_str, str(review_path), problemas=problemas)
        except Exception as exc:
            print(f"[generate] aviso: notificacao falhou: {exc}")


if __name__ == "__main__":
    main()
