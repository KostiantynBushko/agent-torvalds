"""
Math Toolkit - Mathematical operations and calculations.

This module provides essential mathematical functions for numerical computations,
trigonometry, logarithms, and advanced expression evaluation.

Category: Mathematics
Retriever Keywords: calculation, math, arithmetic, trigonometry, logarithm, statistics
"""
import math
import logging
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


def add(a: float, b: float) -> float:
    """
    Add two numbers together.
    
    Use this tool for basic addition operations and summing values.
    
    Args:
        a (float): First number to add
        b (float): Second number to add
        
    Returns:
        float: The sum of a and b
        
    Example:
        >>> add(5, 3)
        8
        >>> add(-2, 7)
        5
        
    Keywords: sum, plus, total, addition, arithmetic
    """
    logger.info(f"add called with a={a}, b={b}")
    try:
        return a + b
    except Exception as e:
        return f"Error adding numbers: {str(e)}"


def subtract(a: float, b: float) -> float:
    """
    Subtract the second number from the first number.
    
    Use this tool for subtraction operations and finding differences between values.
    
    Args:
        a (float): Number to subtract from
        b (float): Number to subtract
        
    Returns:
        float: The difference (a - b)
        
    Example:
        >>> subtract(10, 4)
        6
        >>> subtract(5, 8)
        -3
        
    Keywords: minus, difference, subtract, arithmetic
    """
    logger.info(f"subtract called with a={a}, b={b}")
    try:
        return a - b
    except Exception as e:
        return f"Error subtracting numbers: {str(e)}"


def multiply(a: float, b: float) -> float:
    """
    Multiply two numbers together.
    
    Use this tool for multiplication operations, scaling values, or calculating areas/volumes.
    
    Args:
        a (float): First number to multiply
        b (float): Second number to multiply
        
    Returns:
        float: The product of a and b
        
    Example:
        >>> multiply(4, 5)
        20
        >>> multiply(2.5, 3)
        7.5
        
    Keywords: times, product, scale, area, volume, arithmetic
    """
    logger.info(f"multiply called with a={a}, b={b}")
    try:
        return a * b
    except Exception as e:
        return f"Error multiplying numbers: {str(e)}"


def divide(dividend: float, divisor: float) -> float:
    """
    Divide the first number by the second number.
    
    Use this tool for division operations, calculating ratios, averages, or percentages.
    
    Args:
        dividend (float): Number to be divided
        divisor (float): Number to divide by (must not be zero)
        
    Returns:
        float: The quotient (dividend / divisor)
        
    Example:
        >>> divide(10, 2)
        5.0
        >>> divide(7, 3)
        2.333...
        
    Keywords: quotient, ratio, average, percentage, split, arithmetic
    """
    logger.info(f"divide called with dividend={dividend}, divisor={divisor}")
    try:
        if divisor == 0:
            return "Error: Division by zero"
        return dividend / divisor
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error dividing numbers: {str(e)}"


def power(base: float, exponent: float) -> float:
    """
    Raise a base number to the power of an exponent.
    
    Use this tool for exponential calculations, squaring, cubing, or compound interest.
    
    Args:
        base (float): The base number
        exponent (float): The power to raise the base to
        
    Returns:
        float: base raised to the power of exponent
        
    Example:
        >>> power(2, 3)
        8
        >>> power(5, 2)
        25
        >>> power(9, 0.5)
        3
        
    Keywords: exponent, square, cube, exponential, compound, raise
    """
    logger.info(f"power called with base={base}, exponent={exponent}")
    try:
        return base ** exponent
    except Exception as e:
        return f"Error calculating power: {str(e)}"


def modulo(a: float, b: float) -> float:
    """
    Calculate the remainder of dividing the first number by the second.
    
    Use this tool for finding remainders, checking divisibility, or cyclic operations.
    
    Args:
        a (float): Dividend
        b (float): Divisor (must not be zero)
        
    Returns:
        float: The remainder when a is divided by b
        
    Example:
        >>> modulo(10, 3)
        1
        >>> modulo(15, 4)
        3
        
    Keywords: remainder, mod, divisibility, cyclic, cycle
    """
    logger.info(f"modulo called with a={a}, b={b}")
    try:
        if b == 0:
            return "Error: Modulo by zero"
        return a % b
    except ZeroDivisionError:
        return "Error: Modulo by zero"
    except Exception as e:
        return f"Error calculating modulo: {str(e)}"


def sqrt(a: float) -> float:
    """
    Calculate the square root of a number.
    
    Use this tool for finding square roots in geometry, statistics, or physics calculations.
    
    Args:
        a (float): Number to find square root of (must be non-negative)
        
    Returns:
        float: The square root of a
        
    Example:
        >>> sqrt(16)
        4
        >>> sqrt(2)
        1.414...
        
    Keywords: square root, geometry, distance, standard deviation
    """
    logger.info(f"sqrt called with a={a}")
    try:
        if a < 0:
            return "Error: Cannot calculate square root of negative number"
        return math.sqrt(a)
    except ValueError as e:
        return f"Error calculating square root: {str(e)}"
    except Exception as e:
        return f"Error calculating square root: {str(e)}"


def sin(a: float) -> float:
    """
    Calculate the sine of an angle in radians.
    
    Use this tool for trigonometric calculations, wave functions, or periodic phenomena.
    
    Args:
        a (float): Angle in radians
        
    Returns:
        float: The sine of the angle
        
    Example:
        >>> sin(0)
        0
        >>> sin(3.14159/2)  # π/2
        1
        
    Keywords: sine, trigonometry, wave, periodic, radians, angle
    """
    logger.info(f"sin called with a={a}")
    try:
        return math.sin(a)
    except Exception as e:
        return f"Error calculating sine: {str(e)}"


def cos(a: float) -> float:
    """
    Calculate the cosine of an angle in radians.
    
    Use this tool for trigonometric calculations, projections, or wave functions.
    
    Args:
        a (float): Angle in radians
        
    Returns:
        float: The cosine of the angle
        
    Example:
        >>> cos(0)
        1
        >>> cos(3.14159)  # π
        -1
        
    Keywords: cosine, trigonometry, projection, wave, radians, angle
    """
    logger.info(f"cos called with a={a}")
    try:
        return math.cos(a)
    except Exception as e:
        return f"Error calculating cosine: {str(e)}"


def tan(a: float) -> float:
    """
    Calculate the tangent of an angle in radians.
    
    Use this tool for trigonometric calculations, slopes, or angle relationships.
    
    Args:
        a (float): Angle in radians
        
    Returns:
        float: The tangent of the angle
        
    Example:
        >>> tan(0)
        0
        >>> tan(3.14159/4)  # π/4
        1
        
    Keywords: tangent, trigonometry, slope, angle, radians
    """
    logger.info(f"tan called with a={a}")
    try:
        return math.tan(a)
    except Exception as e:
        return f"Error calculating tangent: {str(e)}"


def log(a: float) -> float:
    """
    Calculate the natural logarithm (base e) of a number.
    
    Use this tool for exponential growth calculations, entropy, or scientific computations.
    
    Args:
        a (float): Number to find logarithm of (must be positive)
        
    Returns:
        float: The natural logarithm of a
        
    Example:
        >>> log(2.71828)  # e
        1
        >>> log(1)
        0
        
    Keywords: natural log, ln, exponential, entropy, scientific
    """
    logger.info(f"log called with a={a}")
    try:
        if a <= 0:
            return "Error: Logarithm undefined for non-positive numbers"
        return math.log(a)
    except ValueError as e:
        return f"Error calculating logarithm: {str(e)}"
    except Exception as e:
        return f"Error calculating logarithm: {str(e)}"


def log10(a: float) -> float:
    """
    Calculate the base-10 logarithm of a number.
    
    Use this tool for pH calculations, decibels, or order-of-magnitude comparisons.
    
    Args:
        a (float): Number to find logarithm of (must be positive)
        
    Returns:
        float: The base-10 logarithm of a
        
    Example:
        >>> log10(100)
        2
        >>> log10(1000)
        3
        
    Keywords: log10, base-10, pH, decibel, magnitude, scale
    """
    logger.info(f"log10 called with a={a}")
    try:
        if a <= 0:
            return "Error: Logarithm undefined for non-positive numbers"
        return math.log10(a)
    except ValueError as e:
        return f"Error calculating base-10 logarithm: {str(e)}"
    except Exception as e:
        return f"Error calculating base-10 logarithm: {str(e)}"


def factorial(a: float) -> float:
    """
    Calculate the factorial of a non-negative integer.
    
    Use this tool for permutations, combinations, probability calculations, or combinatorics.
    
    Args:
        a (float): Non-negative integer (will be converted to int)
        
    Returns:
        float: The factorial of a (a!)
        
    Example:
        >>> factorial(5)
        120
        >>> factorial(0)
        1
        
    Keywords: factorial, permutation, combination, probability, combinatorics
    """
    logger.info(f"factorial called with a={a}")
    try:
        a_int = int(a)
        if a_int < 0:
            return "Error: Factorial undefined for negative numbers"
        if a_int != a and a < 0:
            return "Error: Factorial requires a non-negative integer"
        return math.factorial(a_int)
    except ValueError as e:
        return f"Error calculating factorial: {str(e)}"
    except OverflowError:
        return "Error: Factorial result too large"
    except Exception as e:
        return f"Error calculating factorial: {str(e)}"


def evaluate_rpn(expression: str) -> float:
    """
    Evaluate a Reverse Polish Notation (RPN) expression.
    
    Use this tool for complex mathematical expressions without parentheses.
    RPN places operators after operands, eliminating the need for operator precedence rules.
    
    Supported Binary Operators: +, -, *, /, ^, %, pow
    Supported Unary Operators: sqrt, sin, cos, tan, log, log10, fact, factorial
    
    Args:
        expression (str): RPN expression with space-separated tokens
        
    Returns:
        float: Result of the evaluated expression
        
    Example:
        >>> evaluate_rpn("3 4 +")
        7
        >>> evaluate_rpn("3 4 + 2 *")
        14
        >>> evaluate_rpn("5 sqrt")
        2.236...
        >>> evaluate_rpn("10 2 ^ 3 +")
        13
        
    Keywords: RPN, reverse polish, expression, calculator, postfix
    """
    logger.info(f"evaluate_rpn called with expression: {expression}")
    try:
        stack = []
        tokens = expression.split()
        
        # Map operators to the functions defined above
        binary_ops = {
            '+': add,
            '-': subtract,
            '*': multiply,
            '/': divide,
            '^': power,
            '%': modulo,
            'pow': power,
        }
        
        unary_ops = {
            'sqrt': sqrt,
            'sin': sin,
            'cos': cos,
            'tan': tan,
            'log': log,
            'log10': log10,
            'fact': factorial,
            'factorial': factorial,
        }
        
        for token in tokens:
            if token in binary_ops:
                # Pop two operands for binary operations
                if len(stack) < 2:
                    return f"Error: Not enough operands for operator {token}"
                b = stack.pop()
                a = stack.pop()
                result = binary_ops[token](a, b)
                stack.append(result)
            elif token in unary_ops:
                # Pop one operand for unary operations
                if len(stack) < 1:
                    return f"Error: Not enough operands for operator {token}"
                a = stack.pop()
                result = unary_ops[token](a)
                stack.append(result)
            else:
                # Try to parse as number
                try:
                    stack.append(float(token))
                except ValueError:
                    return f"Error: Unknown token: {token}"
                    
        if len(stack) != 1:
            return "Error: Invalid RPN expression (leftover operands on stack)"
            
        return stack[0]
    except Exception as e:
        return f"Error evaluating RPN expression: {str(e)}"


def get_all_tools() -> list[FunctionTool]:
    """
    Return all math tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of math FunctionTool objects
    """
    logger.info("get_all_tools called for math toolkit")
    return [
        FunctionTool.from_defaults(
            fn=add,
            description="Add two numbers together. Use for basic addition and summing values. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=subtract,
            description="Subtract one number from another. Use for finding differences. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=multiply,
            description="Multiply two numbers. Use for scaling, areas, volumes. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=divide,
            description="Divide one number by another. Use for ratios, averages, percentages. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=power,
            description="Raise a number to a power. Use for exponential calculations, squaring, cubing. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=modulo,
            description="Calculate remainder of division. Use for checking divisibility. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=sqrt,
            description="Calculate square root. Use for geometry, statistics, physics. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=sin,
            description="Calculate sine of an angle in radians. Use for trigonometry and wave functions. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=cos,
            description="Calculate cosine of an angle in radians. Use for trigonometry and projections. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=tan,
            description="Calculate tangent of an angle in radians. Use for trigonometry and slopes. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=log,
            description="Calculate natural logarithm (base e). Use for exponential growth and entropy. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=log10,
            description="Calculate base-10 logarithm. Use for pH, decibels, magnitude comparisons. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=factorial,
            description="Calculate factorial. Use for permutations, combinations, probability. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=evaluate_rpn,
            description="Evaluate Reverse Polish Notation expressions. Use for complex math without parentheses. Category: Mathematics",
        ),
    ]