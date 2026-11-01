"""Примеры реализации факториала."""

import math


def factorial_recursive(n: int) -> int:
    """Рекурсивная реализация."""
    if n <= 1:
        return 1
    return n * factorial_recursive(n - 1)


def factorial_iterative(n: int) -> int:
    """Итеративная реализация."""
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def factorial_math(n: int) -> int:
    """Использование встроенной функции math.factorial."""
    return math.factorial(n)


# Пример использования
if __name__ == "__main__":
    n = 10
    print(f"{n}! = {factorial_iterative(n)}")
