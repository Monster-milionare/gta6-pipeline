"""
Representacao do 'lote do dia' (1 video longo + N shorts) como um arquivo
Markdown unico, legivel e editavel a mao - e esse arquivo que voce abre,
edita e aprova uma vez por dia. publish.py rele esse mesmo arquivo, entao
qualquer edicao sua e sempre respeitada.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContentItem:
    item_id: str
    kind: str          # "long" ou "short"
    titulo: str
    roteiro: str
    publicado: bool = False
    estilo: str = ""   # estilo de edicao (estilos.py) - vazio = padrao
    pegada: str = ""   # jeito de contar o roteiro (estilos.py)


@dataclass
class DailyBatch:
    date: str
    status: str        # "PENDENTE" ou "APROVADO"
    items: list = field(default_factory=list)


def render_markdown(batch: DailyBatch) -> str:
    lines = [f"# Lote do dia - {batch.date}", f"Status: {batch.status}", ""]
    for item in batch.items:
        label = "LONGO" if item.kind == "long" else "SHORT"
        lines.append(f"## {label} - {item.item_id}")
        lines.append(f"Titulo: {item.titulo}")
        lines.append(f"Publicado: {'sim' if item.publicado else 'nao'}")
        if item.estilo:
            lines.append(f"Estilo: {item.estilo}")
        if item.pegada:
            lines.append(f"Pegada: {item.pegada}")
        lines.append("Roteiro:")
        lines.append("```")
        lines.append(item.roteiro.strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


_HEADER_RE = re.compile(r"^Status:\s*(\w+)", re.MULTILINE)
_ITEM_RE = re.compile(
    r"^##\s*(LONGO|SHORT[^-]*)\s*-\s*(?P<id>\S+)\s*\n"
    r"Titulo:\s*(?P<titulo>[^\n]*)\n"
    r"Publicado:\s*(?P<publicado>sim|nao)\s*\n"
    r"(?:Estilo:\s*(?P<estilo>[^\n]*)\n)?"
    r"(?:Pegada:\s*(?P<pegada>[^\n]*)\n)?"
    r"Roteiro:\s*\n```\n(?P<roteiro>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def parse_markdown(text: str, date: str) -> DailyBatch:
    header_match = _HEADER_RE.search(text)
    status = header_match.group(1) if header_match else "PENDENTE"

    items = []
    for m in _ITEM_RE.finditer(text):
        raw_kind = m.group(1).strip()
        kind = "long" if raw_kind.upper().startswith("LONGO") else "short"
        items.append(
            ContentItem(
                item_id=m.group("id"),
                kind=kind,
                titulo=m.group("titulo").strip(),
                roteiro=m.group("roteiro").strip(),
                publicado=(m.group("publicado") == "sim"),
                estilo=(m.group("estilo") or "").strip(),
                pegada=(m.group("pegada") or "").strip(),
            )
        )
    return DailyBatch(date=date, status=status, items=items)


def load_batch(path: Path, date: str) -> DailyBatch:
    return parse_markdown(path.read_text(encoding="utf-8"), date)


def save_batch(path: Path, batch: DailyBatch) -> None:
    path.write_text(render_markdown(batch), encoding="utf-8")


def mark_item_published(path: Path, date: str, item_id: str) -> None:
    batch = load_batch(path, date)
    for item in batch.items:
        if item.item_id == item_id:
            item.publicado = True
    save_batch(path, batch)


def next_unpublished(batch: DailyBatch):
    """Retorna o proximo item aprovado ainda nao publicado, ou None."""
    if batch.status != "APROVADO":
        return None
    for item in batch.items:
        if not item.publicado:
            return item
    return None
