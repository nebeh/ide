"""Утилиты для валидации данных."""


def validate_positive_integer(value, name="value"):
    """Проверяет, что значение является положительным целым числом."""
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value)}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return True


def validate_non_negative_integer(value, name="value"):
    """Проверяет, что значение является неотрицательным целым числом."""
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value)}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return True


def validate_string_not_empty(value, name="value"):
    """Проверяет, что строка не пустая."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value)}")
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")
    return True
