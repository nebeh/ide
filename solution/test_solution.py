import unittest
from solution import fibonacci_recursive

class TestSolution(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(fibonacci_recursive(-1), -1)

    def test_zero(self):
        self.assertEqual(fibonacci_recursive(0), 0)

    def test_one(self):
        self.assertEqual(fibonacci_recursive(1), 1)

    def test_five(self):
        self.assertEqual(fibonacci_recursive(5), 5)

if __name__ == '__main__':
    unittest.main()
