"""
HITL question extraction — the single source of truth for *what the question
is* and *what kind of answer it wants*.

Why this module exists
----------------------
The Human-in-the-Loop used to treat the **whole assistant message** as the
question.  A 3 180-character investigation report became a 3 180-character
question, and the input type was guessed from that report with a substring
match — so a report that merely mentioned *"secret redaction"* turned the
question into a masked ``Enter password:`` prompt.  The operator reported
both symptoms (see ``investigate/hitl-questions-issue/``).

The fix is to separate three things that used to be conflated:

1. the **question** — what the human is actually asked;
2. the **context** — the report around the question, which the human needs
   in order to answer but which is not part of the question;
3. the **input type** — derived from the question alone, never from the
   answer.

Everything here is a pure function of its input: no workflow, no LLM, no
console.  That makes the whole thing unit-testable and gives the agent, the
consumer and the callback handler exactly one implementation to agree on.

Usage:
    from components.hitl_question import (
        split_question, detect_input_type, normalise_question, is_question,
    )

    split = split_question(answer)
    if split is None:
        ...  # the message is not a question
    event = AgentQuestionEvent(
        question=split.question,
        context=split.context,
        input_type=detect_input_type(split.question, split.options),
    )

Category: HITL / Questions
Retriever Keywords: hitl, question, split, extract, input type, normalise
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

#: The longest question the agent puts in front of the operator.  Anything
#: longer is truncated on a word boundary — a question that needs a scroll
#: to read is a report, not a question.
MAX_QUESTION_CHARS = 400


@dataclass(frozen=True)
class Question:
    """A question split out of an assistant message.

    Attributes:
        question: What the operator is asked.  Never the whole message.
        context: The report around the question.  Empty when the message
            *is* the question.
        options: The choices, when the question is a list.
    """

    question: str
    context: str = ""
    options: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

#: A question mark at the end of a sentence.  The character before the mark
#: may be a word character, a closing code span, a quote or a bracket — a
#: question that ends with a code span ("Shall I use `feature/x`?") is still
#: a question.  Trailing Markdown emphasis after the mark is allowed too.
_QUESTION_MARK = re.compile(r"[\w`\"'\)\]]*\s*\?[\*_`\"']*$", re.MULTILINE)

#: Requests that need an answer even without a question mark.
_REQUESTS: Tuple[re.Pattern, ...] = (
    # Direct requests for confirmation / approval
    re.compile(r"\b(confirm|approve|proceed|continue|go ahead)\b", re.IGNORECASE),
    # Destructive operations phrased as an implicit request.  The verb must
    # start a sentence (optionally after a politeness word) so that ordinary
    # prose which merely *mentions* the operation — "Understood, I will not
    # delete it." — is not mistaken for a question.  Without that anchor the
    # agent would keep asking the human the same thing forever.
    re.compile(
        r"(?:^|[.!?]\s*)\s*"
        r"(?:please\s+|could you\s+|can you\s+|would you\s+|do you\s+)?"
        r"\b(delete|drop|remove|overwrite|destroy|format|uninstall)\b",
        re.IGNORECASE,
    ),
    # "Do you want to ..." / "Would you like to ..."
    re.compile(
        r"\b(do you|would you|could you|can you)\b.*\b(want|like|prefer|need)\b",
        re.IGNORECASE,
    ),
    # Explicit HITL markers (the agent can be instructed to emit these)
    re.compile(r"\[HITL\]|\[QUESTION\]|\[NEEDS_INPUT\]", re.IGNORECASE),
)

#: The loose "yes/no" pattern.  Kept for backwards compatibility with the
#: original detection, but *not* used to decide whether a paragraph is the
#: question — it is far too loose for that ("no" appears in "notification").
_LOOSE_YES_NO = re.compile(r"\b(yes|no|y|n)\b.*\b(yes|no|y|n)\b", re.IGNORECASE)

#: The shared detection patterns.  ``components.hitl_agent`` and
#: ``components.human_loop_handler`` both use this list, so there is exactly
#: one definition of "this looks like a question".
QUESTION_PATTERNS: List[re.Pattern] = [
    _QUESTION_MARK,
    *_REQUESTS,
    _LOOSE_YES_NO,
]

#: A Markdown list item: ``- item``, ``* item``, ``+ item``, ``1. item``,
#: ``1) item``.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(\S.*?)\s*$")

#: A sentence boundary: a terminator, optional closing punctuation, then
#: whitespace.
_SENTENCE_BOUNDARY = re.compile(r"[.!?][\"'\)\]]*\s+")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_question(text: str) -> bool:
    """Return ``True`` if *text* appears to contain a question.

    This is the *detection* half of the module: it answers "does this
    message ask the human something?".  It is deliberately loose, because a
    false positive costs a round-trip while a false negative silently
    swallows the question.
    """
    if not text:
        return False
    return any(pattern.search(text) for pattern in QUESTION_PATTERNS)


def _carries_interrogative(text: str) -> bool:
    """Return ``True`` if *text* asks for an answer.

    Stricter than :func:`is_question`: the loose "yes/no" pattern is left
    out, because it would classify ordinary prose as a question and make the
    splitter pick the wrong paragraph.
    """
    if not text or not text.strip():
        return False
    if _QUESTION_MARK.search(text):
        return True
    return any(pattern.search(text) for pattern in _REQUESTS)


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def _iter_blocks(text: str) -> Iterator[Tuple[int, int, str]]:
    """Yield ``(start, end, block)`` for every non-empty paragraph.

    The offsets are into *text*, so the caller can cut the original message
    without re-joining anything.
    """
    length = len(text)
    index = 0
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            return
        start = index
        end = index
        cursor = index
        while cursor < length:
            line_end = text.find("\n", cursor)
            if line_end == -1:
                line_end = length
            if not text[cursor:line_end].strip():
                break
            end = line_end
            cursor = line_end + 1
        yield start, end, text[start:end]
        index = cursor


def _line_offsets(block: str) -> List[int]:
    """Return the offset of every line of *block* within *block*."""
    offsets: List[int] = []
    position = 0
    for line in block.split("\n"):
        offsets.append(position)
        position += len(line) + 1
    return offsets


def _interrogative_span(line: str) -> Optional[Tuple[int, int]]:
    """Return the ``(start, end)`` of the last interrogative sentence.

    ``None`` when the line carries no question mark.  The end of the span
    includes trailing Markdown emphasis, so "…multilingual)?**" keeps its
    closing markers.
    """
    mark = line.rfind("?")
    if mark == -1:
        return None
    end = mark + 1
    while end < len(line) and line[end] in "*_`\"'":
        end += 1
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(line, 0, mark):
        start = match.end()
    return start, end


def _list_question(
    lines: Sequence[str],
) -> Optional[Tuple[str, ...]]:
    """Return the options of *lines* when it is a question written as a list.

    A list block is a set of list items, optionally introduced by a single
    lead-in line that ends with a colon ("Also, would you like me to:").  The
    options are the list items without their markers.
    """
    item_indexes = [
        index for index, line in enumerate(lines) if _LIST_ITEM.match(line)
    ]
    if not item_indexes:
        return None

    others = [
        index
        for index, line in enumerate(lines)
        if index not in item_indexes and line.strip()
    ]
    if len(others) > 1:
        return None
    if others:
        lead_in = others[0]
        # The lead-in must come before the items and end with a colon.
        if lead_in > item_indexes[0] or not lines[lead_in].rstrip().endswith(":"):
            return None

    if not any(_carries_interrogative(line) for line in lines):
        return None

    return tuple(
        _LIST_ITEM.match(lines[index]).group(1).strip()  # type: ignore[union-attr]
        for index in item_indexes
    )


def _question_in_block(
    source: str,
    start: int,
    end: int,
) -> Optional[Tuple[int, int, str, Tuple[str, ...]]]:
    """Find the question inside one paragraph.

    Returns ``(start, end, question, options)`` with the offsets into
    *source*, or ``None`` when the paragraph carries no question.
    """
    block = source[start:end]
    lines = block.split("\n")
    offsets = _line_offsets(block)

    # A question written as a list: the whole paragraph is the question and
    # the items are the options.
    options = _list_question(lines)
    if options is not None:
        return start, end, block, options

    # Otherwise: the last line that carries an interrogative.
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if not line.strip():
            continue
        if not _carries_interrogative(line):
            continue

        span = _interrogative_span(line)
        if span is None:
            # A request without a question mark ("Please delete the branch")
            # — the whole line is the question.
            lead = len(line) - len(line.lstrip())
            question = line.strip()
            question_start = start + offsets[index] + lead
            question_end = question_start + len(question)
        else:
            local_start, local_end = span
            question_start = start + offsets[index] + local_start
            question_end = start + offsets[index] + local_end
            question = source[question_start:question_end]

        # A lead-in line that ends with a colon belongs to the question:
        # "Also, would you like me to:" on its own says nothing.
        if index > 0:
            previous = lines[index - 1]
            if previous.strip() and previous.rstrip().endswith(":"):
                lead = len(previous) - len(previous.lstrip())
                question_start = start + offsets[index - 1] + lead
                question = source[question_start:question_end]

        return question_start, question_end, question, ()

    return None


def _cap(question: str) -> str:
    """Shorten *question* to :data:`MAX_QUESTION_CHARS` on a word boundary."""
    if len(question) <= MAX_QUESTION_CHARS:
        return question
    clipped = question[: MAX_QUESTION_CHARS - 1]
    space = clipped.rfind(" ")
    if space > MAX_QUESTION_CHARS // 2:
        clipped = clipped[:space]
    return clipped.rstrip() + "…"


def split_question(text: str) -> Optional[Question]:
    """Split an assistant message into the question and its context.

    The algorithm walks the message from the last paragraph backwards and
    takes the first paragraph that carries a question:

    * a paragraph written as a list becomes the question, and the list items
      become the options;
    * otherwise the last interrogative sentence of the last interrogative
      line becomes the question, extended backwards over a lead-in line that
      ends with a colon;
    * everything before the question is the context, everything after it is
      appended to the context as well.

    Returns ``None`` when the message is not a question at all.
    """
    if not text or not text.strip():
        return None

    source = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Walk the paragraphs from the last one backwards: the question the
    # operator has to answer is the one the agent asked *last*.
    for start, end, _block in reversed(list(_iter_blocks(source))):
        found = _question_in_block(source, start, end)
        if found is None:
            continue
        question_start, question_end, question, options = found
        prefix = source[:question_start].strip()
        suffix = source[question_end:].strip()
        context = "\n\n".join(part for part in (prefix, suffix) if part)
        return Question(
            question=_cap(question.strip()),
            context=context,
            options=options,
        )

    return None


# ---------------------------------------------------------------------------
# Input type
# ---------------------------------------------------------------------------

#: Words that name a secret.  Mentioning one is *not* enough to ask for a
#: password — the question must also ask for it.
_SECRET_NOUN = re.compile(
    r"\b(password|passphrase|passcode|pin|secret|credential|credentials"
    r"|api[\s-]?key|access[\s-]?token|auth[\s-]?token|private[\s-]?key)\b",
    re.IGNORECASE,
)

#: Phrases that ask for something.
_ASK = re.compile(
    r"\b(what\s+is|what's|what\s+are|enter|provide|give\s+me|supply"
    r"|tell\s+me|type)\b",
    re.IGNORECASE,
)

#: Phrases that offer a binary choice.
_YESNO = (
    re.compile(r"\bshall\s+i\b", re.IGNORECASE),
    re.compile(r"\bshould\s+i\b", re.IGNORECASE),
    re.compile(r"\bcan\s+i\b", re.IGNORECASE),
    re.compile(r"\bmay\s+i\b", re.IGNORECASE),
    re.compile(
        r"\b(do|would|could|will)\s+you\s+(want|like|prefer|need)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(want|need)\s+me\s+to\b", re.IGNORECASE),
    re.compile(
        r"\bis\s+it\s+(ok|okay|fine|alright|acceptable|safe)\b", re.IGNORECASE,
    ),
    re.compile(r"\b(confirm|proceed|go\s+ahead|continue)\b", re.IGNORECASE),
)

#: An explicit marker wins over every heuristic.
_MARKER = re.compile(r"\[HITL:(text|yesno|menu|password)\]", re.IGNORECASE)


def detect_input_type(question: str, options: Sequence[str] = ()) -> str:
    """Return the input type the *question* asks for.

    The question — never the answer, never the report around it — decides:

    ``password``
        the question asks for a secret: it names one **and** asks for it.
        Mentioning a secret is not enough.
    ``menu``
        the question carries an explicit ``[HITL:menu]`` marker.
    ``yesno``
        the question offers a binary choice.
    ``text``
        everything else.

    Args:
        question: The extracted question.
        options: The options of the question, when it is a list.
    """
    if not question or not question.strip():
        return "text"

    marker = _MARKER.search(question)
    if marker:
        return marker.group(1).lower()

    if _SECRET_NOUN.search(question) and _ASK.search(question):
        return "password"

    for pattern in _YESNO:
        if pattern.search(question):
            return "yesno"

    return "text"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

#: The interrogative frame at the head of a question.  "Shall I create the
#: branch X?" and "Should I create the branch X?" are the same request, so
#: the frame is dropped before the two are compared.
_LEADING_FRAME = re.compile(
    r"^(?:"
    r"please\s+|kindly\s+"
    r"|(?:do|would|could|will)\s+you\s+(?:want|like|prefer|need)\s+(?:me\s+to\s+)?"
    r"|(?:shall|should|can|may|could|would)\s+(?:i|we)\s+"
    r"|(?:want|need)\s+me\s+to\s+"
    r"|is\s+it\s+(?:ok|okay|fine|alright|acceptable)\s+"
    r")+",
    re.IGNORECASE,
)


def normalise_question(question: str) -> str:
    """Return the comparison key of *question*.

    The key ignores the things that make the *same* question look different
    — case, Markdown, punctuation, whitespace and the interrogative frame —
    so that "Shall I create the branch X?" and "Should I create the branch
    X?" collapse into one key.  The re-ask guard uses it to stop the agent
    from asking the human the same thing again after the answer was "no".
    """
    if not question:
        return ""
    text = question.strip().lower()
    text = re.sub(r"[`*_~]", "", text)
    text = _LEADING_FRAME.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())
