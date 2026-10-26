# Math Toolkit

A small, dependency-free mathematics toolkit for the Torvalds agent.

It offers the fourteen operations the agent needs for everyday numerical
work - arithmetic, roots, trigonometry, logarithms, factorials and a
Reverse Polish Notation evaluator - in two halves:

| Module | Role | Depends on LlamaIndex |
|---|---|---|
| `operations.py` | the **library half** - the mathematics itself | no |
| `agent_math_toolkit.py` | the **adapter** - wraps the operations as `FunctionTool`s | yes |

The split is the point.  The mathematics stays usable as a plain Python
library, independently testable, and importing it never drags the agent
framework into the process.  The adapter is the single module that knows
about LlamaIndex, and it is imported on demand.

## Quick start

### As a plain library

```python
from toolkits.math_toolkit import add, multiply, evaluate_rpn

add(2, 3)                  # 5
multiply(4, 5)             # 20
evaluate_rpn("3 4 + 2 *")  # 14
```

### As LlamaIndex tools

```python
from toolkits.math_toolkit.agent_math_toolkit import get_all_tools

tools = get_all_tools()    # 14 FunctionTool objects
```

## The operations

| Operation | Signature | Purpose |
|---|---|---|
| `add` | `(a, b)` | sum of two numbers |
| `subtract` | `(a, b)` | difference of two numbers |
| `multiply` | `(a, b)` | product of two numbers |
| `divide` | `(dividend, divisor)` | quotient; guards a division by zero |
| `power` | `(base, exponent)` | `base ** exponent` |
| `modulo` | `(a, b)` | remainder; guards a modulo by zero |
| `sqrt` | `(a)` | square root; guards a negative argument |
| `sin` / `cos` / `tan` | `(a)` | trigonometry, in **radians** |
| `log` | `(a)` | natural logarithm (base *e*) |
| `log10` | `(a)` | base-10 logarithm |
| `factorial` | `(a)` | `a!` for a non-negative integer |
| `evaluate_rpn` | `(expression)` | Reverse Polish Notation evaluator |

### The RPN evaluator

RPN places the operator *after* its operands, so no parentheses and no
operator-precedence rules are needed:

```
evaluate_rpn("3 4 +")      # 7
evaluate_rpn("3 4 + 2 *")  # 14
evaluate_rpn("10 2 ^ 3 +") # 13
evaluate_rpn("9 sqrt")     # 3.0
```

Binary operators: `+`, `-`, `*`, `/`, `^`, `%`, `pow`.
Unary operators: `sqrt`, `sin`, `cos`, `tan`, `log`, `log10`, `fact`,
`factorial`.

## The error contract

Every operation is **total**.  An invalid input is reported as a
human-readable error *string* instead of being raised:

```python
divide(1, 0)      # "Error: Division by zero"
sqrt(-1)          # "Error: Cannot calculate square root of negative number"
log(0)            # "Error: Logarithm undefined for non-positive numbers"
evaluate_rpn("3 4")  # "Error: Invalid RPN expression (leftover operands on stack)"
```

The agent can hand that message straight back to the model, instead of the
tool call dying with a traceback.

## Layout

```
toolkits/
|-- __init__.py                 # package root + import alias shim
`-- math-toolkit/               # <-- this directory
    |-- __init__.py             # public API surface
    |-- operations.py           # the mathematics - the library half
    |-- agent_math_toolkit.py   # the LlamaIndex adapter
    |-- py.typed                # PEP 561 marker
    `-- tests/                  # module-local tests (no __init__.py!)
```

The directory name contains a hyphen, which is not a valid Python
identifier, so the package is reached through the alias that
`toolkits/__init__.py` registers:

```python
from toolkits.math_toolkit import add            # the library half
from toolkits.math_toolkit.agent_math_toolkit import get_all_tools   # the adapter
```

Installed as a standalone distribution it keeps the plain ``math_toolkit``
name:

```python
from math_toolkit import add
```

## Running the tests

The tests live inside the package, and they use **relative** imports:

```bash
pytest toolkits/math-toolkit/tests
```

The module-local ``tests/`` directory must **not** contain ``__init__.py``,
and the suite must run with ``--import-mode=importlib`` (set in the
repository's ``pytest.ini`` through ``addopts``).
