"""Утилиты для форматирования вывода."""


def format_list_as_table(items, columns=3):
    """Форматирует список в виде таблицы с указанным количеством колонок."""
    if not items:
        return ""

    rows = []
    for i in range(0, len(items), columns):
        row = items[i : i + columns]
        rows.append(" | ".join(f"{item:>10}" for item in row))

    return "\n".join(rows)


def format_progress_bar(current, total, width=50):
    """Создает текстовый прогресс-бар."""
    if total == 0:
        return "[" + " " * width + "] 0%"

    percent = current / total
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:.1%}"
