import math

def multiply(a: float, b: float) -> float:
    """
    Useful for multiplying two numbers.
    """
    print("Agent call multiply:")
    return a * b

def divide(dividend: float, divisor: float) -> float:
    """
    Useful to divide two numbers.
    """
    print("Agent call divide:")
    return dividend / divisor

def add(a: float, b: float) -> float:
    """Useful for addition two numbers."""
    print("Agent call sum:")
    return a + b

def subtract(a: float, b: float) -> float:
    """Useful for subtracting two numbers."""
    print("Agent call subtract:")
    return a - b

def power(base: float, exponent: float) -> float:
    """Useful for raising a number to a power."""
    print("Agent call power:")
    return base ** exponent

def modulo(a: float, b: float) -> float:
    """Useful for calculating the remainder."""
    print("Agent call modulo:")
    return a % b

def sqrt(a: float) -> float:
    """Useful for calculating the square root."""
    print("Agent call sqrt:")
    return math.sqrt(a)

def sin(a: float) -> float:
    """Useful for calculating the sine (radians)."""
    print("Agent call sin:")
    return math.sin(a)

def cos(a: float) -> float:
    """Useful for calculating the cosine (radians)."""
    print("Agent call cos:")
    return math.cos(a)

def tan(a: float) -> float:
    """Useful for calculating the tangent (radians)."""
    print("Agent call tan:")
    return math.tan(a)

def log(a: float) -> float:
    """Useful for calculating the natural logarithm."""
    print("Agent call log:")
    return math.log(a)

def log10(a: float) -> float:
    """Useful for calculating the base-10 logarithm."""
    print("Agent call log10:")
    return math.log10(a)

def factorial(a: float) -> float:
    """Useful for calculating the factorial (input treated as integer)."""
    print("Agent call factorial:")
    return math.factorial(int(a))

def evaluate_rpn(expression: str) -> float:
    """
    Evaluates a Reverse Polish Notation (RPN) expression.
    
    This function reuses the existing math operations defined in this file.
    
    Supported Binary Operators: +, -, *, /, ^, %, pow
    Supported Unary Operators: sqrt, sin, cos, tan, log, log10, fact, factorial
    
    Example:
        "3 4 +" -> 7
        "3 4 + 2 *" -> 14
        "5 sqrt" -> 2.236...
    """
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
                raise ValueError(f"Not enough operands for operator {token}")
            b = stack.pop()
            a = stack.pop()
            result = binary_ops[token](a, b)
            stack.append(result)
        elif token in unary_ops:
            # Pop one operand for unary operations
            if len(stack) < 1:
                raise ValueError(f"Not enough operands for operator {token}")
            a = stack.pop()
            result = unary_ops[token](a)
            stack.append(result)
        else:
            # Try to parse as number
            try:
                stack.append(float(token))
            except ValueError:
                raise ValueError(f"Unknown token: {token}")
                
    if len(stack) != 1:
        raise ValueError("Invalid RPN expression (leftover operands on stack)")
        
    return stack[0]