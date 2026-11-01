"""Утилиты для работы с CSV."""

import csv
from typing import List, Dict


def read_csv(file_path: str) -> List[Dict[str, str]]:
    """Читает CSV файл и возвращает список словарей."""
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(file_path: str, data: List[Dict[str, str]]):
    """Записывает список словарей в CSV файл."""
    if not data:
        return

    fieldnames = data[0].keys()
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def filter_csv(data: List[Dict], column: str, value: str) -> List[Dict]:
    """Фильтрует данные по значению в указанной колонке."""
    return [row for row in data if row.get(column) == value]
