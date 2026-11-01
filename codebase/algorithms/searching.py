"""Алгоритмы поиска."""


def binary_search(arr, target):
    """Бинарный поиск в отсортированном массиве. O(log n)."""
    left, right = 0, len(arr) - 1

    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1


def linear_search(arr, target):
    """Линейный поиск. O(n)."""
    for i, item in enumerate(arr):
        if item == target:
            return i
    return -1
