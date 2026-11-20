# The arrow keys of the operator — the cursor that hangs

**Status:** implemented, covered by tests and by a probe that fail without it.
**Reported by:** the operator, on 2026-11-20 — *"by holding arrow key to move forward and back the cursor hangs until I release the key, and then it moves to the correct position"*.

**Probe:** [`probe_arrow_key_repeat.py`](probe_arrow_key_repeat.py) — read-only.  It drives the real reader
from a pseudo-terminal, with the bytes a terminal sends, and measures how long the reader takes for
them and how long the drain of the keyboard lasts.  It writes nothing and talks to no service.

---

## 1. The report

The operator holds an arrow key to walk the cursor through the text he wrote.  The cursor stands still
while the key is held, and it jumps to the place it belongs to when the key is released.

Two things were wrong, and they had to be told apart before anything was changed.

## 2. What the reader was doing

`components/tui/input_reader.py` — `_poll_escape()` read a control sequence in two steps: it asked the
terminal whether anything was there, and then it read the sequence out of its own buffer.  The first
step was **unconditional**: the reader waited fifty milliseconds for the terminal before it looked at
the buffer it already had.

A terminal that repeats a key sends the sequences faster than the screen is drawn.  The reader was
therefore always half a second behind the operator:

| the keys | before | after |
| :--- | ---: | ---: |
| twenty arrow keys, written in one piece | **1.005 s** | 0.000 s |
| one arrow key, on its own | 0.051 s | 0.001 s |

Fifty milliseconds for every key is not a slow cursor — it is a cursor that cannot keep up with a key
that repeats, and a backlog that grows the whole time the key is held.

## 3. What the app was doing with the keys

`components/tui/tui_app.py` — `_process_keyboard_input()` asked the reader for **one key after the
other, until the terminal went quiet**:

```python
while self.input_reader.is_available():
    key = self.input_reader.poll_key()
    if not key:
        break
    self._handle_key(key)
```

A terminal that repeats a key that is held **never goes quiet**.  The drain of the keyboard therefore
lasted as long as the key was held, and the screen is drawn *after* the drain:

```
the drain of the keyboard, tick by tick, while the key is held:
    [0.0, 0.946, 0.0, 0.0, 0.0, ...]
   the longest drain: 0.946 s   (the screen is drawn after the drain)
   -> the screen was frozen for 0.946 s
```

That is the report of the operator, in numbers: the screen was frozen for as long as the key was
held, and the cursor landed on the right place at the end of it.

## 4. What was changed

### 4.1 The reader waits for the rest of a sequence only when it does not have it

`_poll_escape()` looks at the buffer first and asks the terminal only when the buffer runs out
mid-sequence.  A key that repeats is read at the speed it arrives.

The reader keeps the old behaviour where it matters: a sequence that the terminal is still writing is
waited for, as long as it takes — a terminal that is slow writes the rest of the sequence late, and
the sequence is one key.

### 4.2 The reader hands over the keys that are waiting, in one piece

`poll_keys()` is the new way of reading: the terminal is read **once**, and the keys that are in the
buffer are parsed out of it.  A key that arrives while they are parsed is left for the next call.

The reason is the report of the operator: a reader that waits for the quiet never gives the screen
back while a key is held.  The keys that arrive during a tick are read by the next tick — the cursor
is one frame behind the key, which is a frame the operator cannot see.

### 4.3 The app draws the screen between the keys

`_process_keyboard_input()` reads the keys the app is given in one piece and handles them.  The drain
of the keyboard is now as long as the keys that are waiting, and the screen is drawn right after it.

### 4.4 The escape that is alone

A lone ESC is still an escape.  The reader leaves it in the buffer and reports it when nothing comes
after it — after fifty milliseconds, as before.  A sequence the terminal is in the middle of writing
is waited for and is one key.

## 5. How it is verified

`tests/test_tui_input_reader.py` — 5 new tests, in a file that held 6 more, in two groups:

| group | what it holds |
| :--- | :--- |
| the repeated key | twenty arrow keys are twenty keys and they come at once; the drain of the keyboard ends while the key is held |
| the keys | a paste arrives in one piece, a lone escape is an escape, a sequence in two pieces is one key |

The tests measure the **behaviour**, not the shape of the reader: the child uses the way of reading
the keys that the reader has, so the old reader is measured by the same ruler as the new one.  Two of
them fail against the old code:

```
the twenty keys took 1.004 s to be read -- the reader waits for the rest of a
sequence it already has
the drain of the keyboard lasted 0.647 s -- the screen is drawn after the drain,
and the cursor of the operator stands still while the key is held
```

`probe_arrow_key_repeat.py` measures the same three things and fails against the old code with the
numbers of §2 and §3.
