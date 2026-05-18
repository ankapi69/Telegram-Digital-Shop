from __future__ import annotations

import csv
import io


def parse_stock_csv(blob: bytes, max_items: int = 5000, max_length: int = 1024) -> list[str]:
    """Parse a CSV/TSV/plain-text file of stock units into a list of strings.

    Accepts: one item per row (first column used) or one item per newline.
    Empty lines are skipped. Raises ``ValueError`` on overflow or oversized
    rows.
    """
    text = blob.decode("utf-8-sig", errors="replace")
    items: list[str] = []
    reader = csv.reader(io.StringIO(text), delimiter=",")
    for row in reader:
        if not row:
            continue
        value = (row[0] if len(row) == 1 else ",".join(row)).strip()
        if not value:
            continue
        if len(value) > max_length:
            raise ValueError(f"Слишком длинная строка (>{max_length}).")
        items.append(value)
        if len(items) > max_items:
            raise ValueError(f"Слишком много позиций (>{max_items}).")
    return items
