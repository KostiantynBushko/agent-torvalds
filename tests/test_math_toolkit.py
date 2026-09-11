"""
Unit tests for agent_math_toolkit.

Tests all mathematical operations including:
- Basic arithmetic (add, subtract, multiply, divide)
- Advanced operations (power, modulo, sqrt)
- Trigonometric functions (sin, cos, tan)
- Logarithmic functions (log, log10)
- Factorial
- Reverse Polish Notation evaluator
"""

import unittest
import math
import sys
import os

# Add the parent directory to the path so we can import agent_math_toolkit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_math_toolkit import (
    add, subtract, multiply, divide,
    power, modulo, sqrt,
    sin, cos, tan,
    log, log10, factorial,
    evaluate_rpn
)


class TestBasicArithmetic(unittest.TestCase):
    """Tests for basic arithmetic operations."""
    
    def test_add(self):
        """Test addition of two numbers."""
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)
        self.assertEqual(add(0, 0), 0)
        self.assertAlmostEqual(add(0.1, 0.2), 0.3, places=10)
    
    def test_subtract(self):
        """Test subtraction of two numbers."""
        self.assertEqual(subtract(5, 3), 2)
        self.assertEqual(subtract(1, 1), 0)
        self.assertEqual(subtract(0, 5), -5)
        self.assertEqual(subtract(-1, -1), 0)
    
    def test_multiply(self):
        """Test multiplication of two numbers."""
        self.assertEqual(multiply(2, 3), 6)
        self.assertEqual(multiply(-2, 3), -6)
        self.assertEqual(multiply(0, 100), 0)
        self.assertEqual(multiply(-2, -3), 6)
    
    def test_divide(self):
        """Test division of two numbers."""
        self.assertEqual(divide(6, 2), 3)
        self.assertEqual(divide(-6, 2), -3)
        self.assertEqual(divide(0, 5), 0)
        self.assertAlmostEqual(divide(1, 3), 0.3333333333, places=9)
    
    def test_divide_by_zero(self):
        """Test division by zero raises ZeroDivisionError."""
        with self.assertRaises(ZeroDivisionError):
            divide(1, 0)


class TestAdvancedOperations(unittest.TestCase):
    """Tests for advanced mathematical operations."""
    
    def test_power(self):
        """Test power operation."""
        self.assertEqual(power(2, 3), 8)
        self.assertEqual(power(5, 0), 1)
        self.assertEqual(power(2, -1), 0.5)
        self.assertAlmostEqual(power(2, 0.5), math.sqrt(2), places=10)
    
    def test_modulo(self):
        """Test modulo operation."""
        self.assertEqual(modulo(10, 3), 1)
        self.assertEqual(modulo(10, 2), 0)
        self.assertEqual(modulo(7, 7), 0)
    
    def test_sqrt(self):
        """Test square root operation."""
        self.assertAlmostEqual(sqrt(4), 2)
        self.assertAlmostEqual(sqrt(9), 3)
        self.assertAlmostEqual(sqrt(2), math.sqrt(2), places=10)
        self.assertAlmostEqual(sqrt(0), 0)
    
    def test_sqrt_negative(self):
        """Test square root of negative number raises ValueError."""
        with self.assertRaises(ValueError):
            sqrt(-1)


class TestTrigonometricFunctions(unittest.TestCase):
    """Tests for trigonometric functions."""
    
    def test_sin(self):
        """Test sine function."""
        self.assertAlmostEqual(sin(0), 0, places=10)
        self.assertAlmostEqual(sin(math.pi / 2), 1, places=10)
        self.assertAlmostEqual(sin(math.pi), 0, places=10)
        self.assertAlmostEqual(sin(3 * math.pi / 2), -1, places=10)
    
    def test_cos(self):
        """Test cosine function."""
        self.assertAlmostEqual(cos(0), 1, places=10)
        self.assertAlmostEqual(cos(math.pi / 2), 0, places=10)
        self.assertAlmostEqual(cos(math.pi), -1, places=10)
        self.assertAlmostEqual(cos(2 * math.pi), 1, places=10)
    
    def test_tan(self):
        """Test tangent function."""
        self.assertAlmostEqual(tan(0), 0, places=10)
        self.assertAlmostEqual(tan(math.pi / 4), 1, places=10)
        self.assertAlmostEqual(tan(math.pi), 0, places=10)


class TestLogarithmicFunctions(unittest.TestCase):
    """Tests for logarithmic functions."""
    
    def test_log(self):
        """Test natural logarithm."""
        self.assertAlmostEqual(log(1), 0, places=10)
        self.assertAlmostEqual(log(math.e), 1, places=10)
        self.assertAlmostEqual(log(math.e ** 2), 2, places=10)
    
    def test_log_zero(self):
        """Test log of zero raises ValueError."""
        with self.assertRaises(ValueError):
            log(0)
    
    def test_log_negative(self):
        """Test log of negative number raises ValueError."""
        with self.assertRaises(ValueError):
            log(-1)
    
    def test_log10(self):
        """Test base-10 logarithm."""
        self.assertAlmostEqual(log10(1), 0, places=10)
        self.assertAlmostEqual(log10(10), 1, places=10)
        self.assertAlmostEqual(log10(100), 2, places=10)
        self.assertAlmostEqual(log10(1000), 3, places=10)


class TestFactorial(unittest.TestCase):
    """Tests for factorial function."""
    
    def test_factorial(self):
        """Test factorial of positive integers."""
        self.assertEqual(factorial(0), 1)
        self.assertEqual(factorial(1), 1)
        self.assertEqual(factorial(5), 120)
        self.assertEqual(factorial(10), 3628800)
    
    def test_factorial_float(self):
        """Test factorial with float input (should be converted to int)."""
        self.assertEqual(factorial(5.9), 120)  # int(5.9) = 5


class TestRPNEvaluator(unittest.TestCase):
    """Tests for the Reverse Polish Notation evaluator."""
    
    def test_rpn_basic_addition(self):
        """Test basic addition in RPN."""
        self.assertEqual(evaluate_rpn("3 4 +"), 7)
    
    def test_rpn_basic_subtraction(self):
        """Test basic subtraction in RPN."""
        self.assertEqual(evaluate_rpn("10 3 -"), 7)
    
    def test_rpn_basic_multiplication(self):
        """Test basic multiplication in RPN."""
        self.assertEqual(evaluate_rpn("5 6 *"), 30)
    
    def test_rpn_basic_division(self):
        """Test basic division in RPN."""
        self.assertEqual(evaluate_rpn("15 3 /"), 5)
    
    def test_rpn_complex_expression(self):
        """Test complex RPN expression: (3 + 4) * 2 = 14"""
        self.assertEqual(evaluate_rpn("3 4 + 2 *"), 14)
    
    def test_rpn_power(self):
        """Test power operation in RPN."""
        self.assertEqual(evaluate_rpn("2 3 ^"), 8)
        self.assertEqual(evaluate_rpn("2 3 pow"), 8)
    
    def test_rpn_modulo(self):
        """Test modulo operation in RPN."""
        self.assertEqual(evaluate_rpn("10 3 %"), 1)
    
    def test_rpn_sqrt(self):
        """Test square root in RPN."""
        self.assertAlmostEqual(evaluate_rpn("9 sqrt"), 3, places=10)
    
    def test_rpn_trigonometric(self):
        """Test trigonometric functions in RPN."""
        self.assertAlmostEqual(evaluate_rpn("0 sin"), 0, places=10)
        self.assertAlmostEqual(evaluate_rpn("0 cos"), 1, places=10)
    
    def test_rpn_logarithmic(self):
        """Test logarithmic functions in RPN."""
        self.assertAlmostEqual(evaluate_rpn("1 log"), 0, places=10)
        self.assertAlmostEqual(evaluate_rpn("10 log10"), 1, places=10)
    
    def test_rpn_factorial(self):
        """Test factorial in RPN."""
        self.assertEqual(evaluate_rpn("5 fact"), 120)
        self.assertEqual(evaluate_rpn("5 factorial"), 120)
    
    def test_rpn_invalid_token(self):
        """Test RPN with invalid token raises ValueError."""
        with self.assertRaises(ValueError):
            evaluate_rpn("3 invalid +")
    
    def test_rpn_not_enough_operands(self):
        """Test RPN with not enough operands raises ValueError."""
        with self.assertRaises(ValueError):
            evaluate_rpn("3 +")
    
    def test_rpn_leftover_operands(self):
        """Test RPN with leftover operands raises ValueError."""
        with self.assertRaises(ValueError):
            evaluate_rpn("3 4")


class TestMathPrecision(unittest.TestCase):
    """Tests for mathematical precision with floating point numbers."""
    
    def test_add_precision(self):
        """Test addition precision."""
        self.assertAlmostEqual(add(0.1, 0.2), 0.3, places=10)
    
    def test_multiply_precision(self):
        """Test multiplication precision."""
        self.assertAlmostEqual(multiply(0.1, 0.2), 0.02, places=10)
    
    def test_divide_precision(self):
        """Test division precision."""
        self.assertAlmostEqual(divide(1, 3), 1/3, places=10)


if __name__ == "__main__":
    unittest.main()
