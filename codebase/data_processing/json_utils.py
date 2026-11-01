"""Утилиты для работы с JSON."""

import json
from typing import Any, Dict, List


def read_json(file_path: str) -> Any:
    """Читает JSON файл."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(file_path: str, data: Any, indent: int = 2):
    """Записывает данные в JSON файл."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def flatten_dict(d: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """Преобразует вложенный словарь в плоский."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
