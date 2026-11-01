# solution.py

Функция из задачи пользователя.

```python
def fibonacci_recursive(n: int) -> int:
    """Рекурсивная реализация. O(2^n) - неэффективно для больших n."""
    if n <= 1:
        return n
    return fibonacci_recursive(n - 1) + fibonacci_recursive(n - 2)


def fibonacci_iterative(n: int) -> int:
    """Итеративная реализация. O(n) - эффективно."""
    if n <= 1:
        return n

    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def fibonacci_generator(n: int):
    """Генератор чисел Фибоначчи. Память: O(1)."""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b


def fibonacci_sequence(n: int) -> list:
    """Возвращает последовательность из n чисел Фибоначчи."""
    return list(fibonacci_generator(n))


# Пример использования
if __name__ == "__main__":
    print("Первые 10 чисел Фибоначчи:")
    print(fibonacci_sequence(10))

    print("\n10-е число Фибоначчи:")
    print(fibonacci_iterative(10))
```
