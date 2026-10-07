import unittest

from arithmetic import add


class ArithmeticTests(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative_input(self):
        self.assertEqual(add(-2, 3), 1)
