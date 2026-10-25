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
import string
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
        options: The choices, when the question is a list.  The question
            text never repeats them — the consumer renders the menu.
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
    # An imperative ask: "Please enter the API key ...", "Provide the
    # passphrase ...".  The verb has to start the sentence, otherwise
    # ordinary prose that happens to contain "enter" or "provide" would
    # look like a request.  Without this rule a password question is not
    # even recognised as a question.
    re.compile(
        r"(?:^|[.!?]\s*)\s*"
        r"(?:please\s+)?"
        r"\b(enter|provide|supply|give\s+me|tell\s+me|type\s+(?:in|the|a|your))\b",
        re.IGNORECASE,
    ),
    # Explicit HITL markers (the agent can be instructed to emit these).
    # The type may be given: "[HITL:text]", "[HITL:password]".
    re.compile(
        r"\[HITL(?::[a-z]+)?\]|\[QUESTION\]|\[NEEDS_INPUT\]", re.IGNORECASE,
    ),
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
#: ``1) item``.  The bullet characters ``•`` and ``‣`` are included
#: because a model that writes a report very often uses them.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+•‣]|\d+[.)])\s+(\S.*?)\s*$")

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


#: The kind of every line of a block: a list item, the continuation of a
#: list item, an ordinary line, or blank.
_ITEM = "item"
_CONTINUATION = "continuation"
_OTHER = "other"
_BLANK = "blank"


def _classify_lines(lines: Sequence[str]) -> List[str]:
    """Classify every line of a block.

    A line that is indented and follows a list item (or another
    continuation) belongs to that item — "1. **There is nothing to
    delete** — the path is already\\n   absent, so a delete would be a
    no-op." is one item, not two lines.
    """
    kinds: List[str] = []
    last_content = ""
    for line in lines:
        if not line.strip():
            kinds.append(_BLANK)
            continue
        if _LIST_ITEM.match(line):
            kinds.append(_ITEM)
            last_content = _ITEM
        elif line[:1] in (" ", "\t") and last_content in (_ITEM, _CONTINUATION):
            kinds.append(_CONTINUATION)
            last_content = _CONTINUATION
        else:
            kinds.append(_OTHER)
            last_content = _OTHER
    return kinds


def _item_text(lines: Sequence[str], kinds: Sequence[str], index: int) -> str:
    """Return the text of the list item that starts at *index*."""
    match = _LIST_ITEM.match(lines[index])
    parts = [match.group(1).strip()]  # type: ignore[union-attr]
    cursor = index + 1
    while cursor < len(lines) and kinds[cursor] == _CONTINUATION:
        parts.append(lines[cursor].strip())
        cursor += 1
    return " ".join(part for part in parts if part)


def _list_lead_in(
    lines: Sequence[str], kinds: Sequence[str]
) -> Tuple[Optional[int], Tuple[str, ...]]:
    """Return ``(lead_in_index, items)`` for a block written as a list.

    ``lead_in_index`` is the index of the line that introduces the list
    ("Also, would you like me to:").  It is ``None`` when the block is
    *only* a list of items — such a block carries no question of its own.
    """
    item_indexes = [i for i, kind in enumerate(kinds) if kind == _ITEM]
    if not item_indexes:
        return None, ()

    others = [i for i, kind in enumerate(kinds) if kind == _OTHER]
    if len(others) > 1:
        return None, ()
    if not others:
        return None, tuple(
            _item_text(lines, kinds, i) for i in item_indexes
        )

    lead_in = others[0]
    # The lead-in must come before the items and end with a colon.
    if lead_in > item_indexes[0] or not lines[lead_in].rstrip().endswith(":"):
        return None, ()

    return lead_in, tuple(_item_text(lines, kinds, i) for i in item_indexes)


def _plain_list_items(text: str) -> Tuple[str, ...]:
    """Return the items of a block that is *nothing but* a list of choices.

    An empty tuple when the block is not a plain list.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ()
    if not all(_LIST_ITEM.match(line) for line in lines):
        return ()
    kinds = _classify_lines(lines)
    return tuple(
        _item_text(lines, kinds, i)
        for i, kind in enumerate(kinds)
        if kind == _ITEM
    )


#: An inline option marker: "(a)", "(b)", "(c)".  A model that offers a
#: choice inside a single sentence uses these.
_INLINE_OPTION = re.compile(r"\(\s*([a-z])\s*\)", re.IGNORECASE)

#: The punctuation that surrounds an inline option.
_OPTION_TRIM = " \t,;:-—…"


def _inline_choice(text: str) -> Optional[Tuple[Tuple[str, ...], str]]:
    """Return ``(options, question)`` for an inline ``(a) … (b) …`` choice.

    ``None`` when *text* does not carry such a choice.  The markers have to
    be consecutive letters starting at "a", otherwise a stray "(a)" in a
    sentence would look like a menu.  The question is what is left in front
    of the first marker — the options are removed from it, because the
    consumer renders them as the menu.
    """
    matches = list(_INLINE_OPTION.finditer(text))
    if len(matches) < 2:
        return None

    letters = [match.group(1).lower() for match in matches]
    if letters != list(string.ascii_lowercase[: len(letters)]):
        return None

    options: List[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        option = text[start:end].strip()
        # The marker is often wrapped in Markdown emphasis: "**(a)**".
        option = option.strip("*_`").strip()
        # "… file, or **(c)** cancel" — the "or" belongs to the previous
        # option.
        option = re.sub(r"\s*,?\s*\bor\b\s*$", "", option, flags=re.IGNORECASE)
        option = option.strip(_OPTION_TRIM).strip()
        option = option.rstrip(".").strip()
        if not option:
            return None
        options.append(option)

    question = text[: matches[0].start()].strip()
    question = question.strip("*_`").strip()
    return tuple(options), question


#: The plan for one block: where the question is, what it says and what
#: the choices are.
@dataclass(frozen=True)
class _Plan:
    """Where the question of a block is, and what it offers."""

    start: int
    end: int
    text: str
    options: Tuple[str, ...]
    #: The region of the source that holds the options.  It is cut out of
    #: the context — the consumer renders the menu instead.
    option_span: Optional[Tuple[int, int]] = None


def _question_in_block(
    source: str,
    start: int,
    end: int,
) -> Optional[_Plan]:
    """Find the question inside one paragraph.

    Returns ``None`` when the paragraph carries no question.
    """
    block = source[start:end]
    lines = block.split("\n")
    offsets = _line_offsets(block)
    kinds = _classify_lines(lines)

    # A question written as a list: the lead-in is the question and the
    # list items are the choices.
    lead_in, items = _list_lead_in(lines, kinds)
    if lead_in is not None:
        if not any(_carries_interrogative(line) for line in lines):
            return None
        lead = len(lines[lead_in]) - len(lines[lead_in].lstrip())
        question_start = start + offsets[lead_in] + lead
        question = lines[lead_in].strip()
        item_indexes = [i for i, kind in enumerate(kinds) if kind == _ITEM]
        option_start = start + offsets[item_indexes[0]]
        option_end = start + offsets[item_indexes[-1]] + len(
            lines[item_indexes[-1]]
        )
        return _Plan(
            start=question_start,
            end=question_start + len(question),
            text=question,
            options=items,
            option_span=(option_start, option_end),
        )

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
            # — the whole line is the question.  A lead-in that ends with a
            # colon keeps its last sentence only: "The commit touches 4
            # files. Also, would you like me to:" becomes "Also, would you
            # like me to:".
            stripped = line.rstrip()
            if stripped.endswith(":"):
                offset = 0
                for match in _SENTENCE_BOUNDARY.finditer(line):
                    offset = match.end()
                question = line[offset:].strip()
            else:
                question = line.strip()
            lead = len(line) - len(line.lstrip())
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

        # An inline choice — "(a) …, (b) …, or (c) …" — is the menu.
        inline = _inline_choice(question)
        if inline is not None:
            options, head = inline
            return _Plan(
                start=question_start,
                end=question_start + len(head),
                text=head,
                options=options,
                option_span=(question_start + len(head), question_end),
            )

        return _Plan(
            start=question_start,
            end=question_end,
            text=question,
            options=(),
        )

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

    * a paragraph written as a list becomes a question with a *menu*: the
      lead-in is the question, the list items are the choices;
    * a list of choices that *follows* the question is the menu as well;
    * an inline choice — "(a) …, (b) …, or (c) …" — is the menu;
    * otherwise the last interrogative sentence of the last interrogative
      line becomes the question, extended backwards over a lead-in line
      that ends with a colon.

    The choices are never repeated inside the question: the consumer
    renders them as the menu.

    Returns ``None`` when the message is not a question at all.
    """
    if not text or not text.strip():
        return None

    source = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    blocks = list(_iter_blocks(source))
    if not blocks:
        return None

    # Walk the paragraphs from the last one backwards: the question the
    # operator has to answer is the one the agent asked *last*.
    chosen: Optional[Tuple[int, _Plan]] = None
    for index in range(len(blocks) - 1, -1, -1):
        start, end, _ = blocks[index]
        plan = _question_in_block(source, start, end)
        if plan is not None:
            chosen = (index, plan)
            break
    if chosen is None:
        return None

    q_index, plan = chosen
    options = plan.options
    option_span = plan.option_span

    # A list of choices that *follows* the question is the menu.
    if not options and q_index + 1 < len(blocks):
        nxt_start, nxt_end, _ = blocks[q_index + 1]
        items = _plain_list_items(source[nxt_start:nxt_end])
        if len(items) >= 2:
            options = items
            option_span = (nxt_start, nxt_end)

    prefix = source[: plan.start].strip()
    suffix = source[plan.end:].strip()
    if option_span is not None:
        # The choices are rendered as the menu, not as context.
        option_start, option_end = option_span
        head = source[plan.end : option_start].strip() if option_start >= plan.end else ""
        tail = source[option_end:].strip()
        suffix = "\n\n".join(part for part in (head, tail) if part)

    context = "\n\n".join(part for part in (prefix, suffix) if part)
    return Question(
        question=_cap(plan.text.strip()),
        context=context,
        options=options,
    )


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

#: An open (wh-) question at the head of the question.  "Which of these
#: should I investigate first?" and "What is the name of the branch you
#: want me to create?" ask for a *value* or a *choice* — they cannot be
#: answered with "yes" or "no", so they must never be prompted as
#: ``[y/N]``.
_WH_HEAD = re.compile(
    r"^[\s,.;:]*(?:(?:and|also|so|now|then|ok|okay|alright|well)\b[\s,]*|"
    r"(?:in|on|at|for|by|from|with|about)\s+)*"
    r"(which|what|who|whom|whose|where|when|why|how)\b",
    re.IGNORECASE,
)

#: "the branch *you* want me to create" — a relative clause inside a noun
#: phrase.  The operator is asked for a value, not for a confirmation.
#: The look-behinds skip the genuine offers — "Do you want me to …?",
#: "Would you like me to …?".
_RELATIVE_OFFER = re.compile(
    r"(?<!do )(?<!would )(?<!could )(?<!will )(?<!should )(?<!shall )"
    r"(?<!can )(?<!may )"
    r"\b(you|it|them|us)\s+(want|need|like)\s+me\s+to\b",
    re.IGNORECASE,
)

#: "want me to" / "need me to" — a request for a confirmation.
_WANT_ME_TO = re.compile(r"\b(want|need)\s+me\s+to\b", re.IGNORECASE)

#: Phrases that offer a binary choice.
_YESNO: Tuple[re.Pattern, ...] = (
    re.compile(r"\bshall\s+i\b", re.IGNORECASE),
    re.compile(r"\bshould\s+i\b", re.IGNORECASE),
    re.compile(r"\bcan\s+i\b", re.IGNORECASE),
    re.compile(r"\bmay\s+i\b", re.IGNORECASE),
    re.compile(
        r"\b(do|would|could|will)\s+you\s+(want|like|prefer|need)\b",
        re.IGNORECASE,
    ),
    _WANT_ME_TO,
    re.compile(
        r"\bis\s+it\s+(ok|okay|fine|alright|acceptable|safe)\b", re.IGNORECASE,
    ),
    re.compile(r"\b(confirm|proceed|go\s+ahead|continue)\b", re.IGNORECASE),
)

#: An explicit marker wins over every heuristic.
_MARKER = re.compile(r"\[HITL:(text|yesno|menu|password)\]", re.IGNORECASE)

#: Any explicit marker, with or without a type.
_MARKER_ANY = re.compile(r"\[HITL(?::[a-z]+)?\]", re.IGNORECASE)


def strip_marker(question: str) -> str:
    """Return *question* without its explicit ``[HITL:...]`` marker.

    The marker is an instruction to the *detector*, not something the
    operator has to read.
    """
    if not question:
        return ""
    return _MARKER_ANY.sub("", question).strip()


def _is_yes_no(question: str) -> bool:
    """Return ``True`` when *question* offers a binary choice.

    Two rules, in order:

    1. an **open** question — a wh-question at its head — is never a
       binary offer.  "Which of these should I investigate first?" wants a
       choice, not a "yes";
    2. otherwise the question has to *offer* something: "shall I …?",
       "do you want …?", "is it ok …?", "confirm …".  A request that
       merely mentions the offer — "the branch you want me to create" — is
       not an offer.
    """
    if _WH_HEAD.search(question):
        return False

    relative = _RELATIVE_OFFER.search(question)
    for pattern in _YESNO:
        if not pattern.search(question):
            continue
        if relative is not None and pattern is _WANT_ME_TO:
            continue
        return True
    return False


def detect_input_type(question: str, options: Sequence[str] = ()) -> str:
    """Return the input type the *question* asks for.

    The question — never the answer, never the report around it — decides:

    ``password``
        the question asks for a secret: it names one **and** asks for it.
        Mentioning a secret is not enough.
    ``menu``
        the question offers a list of choices — two or more options.
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

    # A question written as a list of choices wants a choice, not a yes or
    # a no.  "Would you like me to: 1. ... 2. ..." cannot be answered with
    # "yes" — the operator has to pick one.
    if len(options) >= 2:
        return "menu"

    if _is_yes_no(question):
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
