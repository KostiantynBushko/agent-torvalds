# The content of a session, printed or written to a file

A proposal for a `\chat-export` command in the **Chat** section.

Date: 2026-11-08
Status: implemented on `feature/chat-export`

---

## The request

> a command under the "chat" section to be able to print current session
> content into stdout or file

## What the session holds

Two things are called "the session", and they are not the same size:

| | what it is | who asks for it |
|---|---|---|
| the **stored** messages | everything the session keeps — it grows with every turn and is never trimmed | the operator, who wants to keep a copy |
| the **buffered** messages | the tail of the history that survives the chat-token limit — what the model is actually sent | the model |

`\chat-info` already reports both numbers.  The export takes the **stored**
messages: an export that silently drops the older half of a conversation
would be a trap, and the operator can see the difference between the two
sizes in the header of the export itself.

## The shape

```
\chat-export                      the stored history, on stdout
\chat-export <path>               the stored history, in a file
\chat-export --buffer             the buffered tail, on stdout
\chat-export --buffer <path>      the buffered tail, in a file
\chat-export --store              the stored history, said out loud
\chat-export --json               the JSON of the session, on stdout
\chat-export --json <path>        the JSON of the session, in a file
\chat-export --json --buffer      the JSON of the buffer
```

One command, one optional argument, one optional source, one optional
format.  The text is the text — the same rendering the log uses
(`components/chat_message.to_string`) — and the JSON is the same export
with the parts of a message turned into fields.

### The source

The export can carry either half of the session:

| | what it carries | why it is worth having |
|---|---|---|
| `--store` (the default) | every message the session keeps | the whole conversation, nothing dropped |
| `--buffer` | the tail that survives the chat-token limit | what the model was actually shown |

The stored history is the default, because an export that silently dropped
the older half of a conversation would be a trap.  The buffer is the other
half — it is what a report about a runaway context needs to quote.

The options come first and the path is what is left, kept verbatim, so a
path with a space in it survives.  An unknown option, the same option
twice and two sources at once are reported with the usage line.

### The format

| | what it carries | who reads it |
|---|---|---|
| `--text` (the default) | the rendering of the log — one message per line | a person |
| `--json` | the same messages, with the role, the content, the thinking and the tool calls as fields | a program |

The JSON is not the text with brackets around it.  A consumer that has to
read a session does not have to parse a line to learn what a message is:

```json
{
  "session": {"id": "sess-1", "name": "General Chat", "type": "general",
              "created_at": "2026-11-08T14:00:00",
              "updated_at": "2026-11-08T14:42:12"},
  "source": "stored",
  "message_count": 2,
  "size_bytes": 27,
  "tokens": 4,
  "tokens_estimated": false,
  "messages": [
    {"role": "user", "content": "hello", "thinking": null,
     "tool_calls": [], "metadata": {}}
  ]
}
```

The document says the same things the text says: the session, the source,
the count, the size and the tokens — the size and the tokens of the
**exported** messages, and `tokens_estimated` says whether the tokenizer
was there to count them.

The source and the format are independent groups of options: `--buffer`
chooses which half of the session, `--json` chooses how it is written.
Each group takes one option.

### The text

```
Session: General Chat (sess-1)
Type: general
Source: stored | Messages: 12 | Size: 4.2 KB | Tokens: ≈1,234

user: I want to improve the debug message
assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
```

The header says which session it is, **which part of it** was exported, and
how big that part is — an export that does not say where it came from is a
mystery file, and one that does not say whether it carries the whole
session or only what the model sees is half a mystery file.  The size and
the tokens are the ones of the *exported* messages, not of the session
behind them.

The messages themselves are rendered by `components.chat_message.to_string`,
the renderer the log already uses, so the text of a session reads the same
everywhere.

### The file

* The path is the operator's: `~` is expanded, a relative path is taken
  from the working directory of the agent.
* The file is written as UTF-8 and **overwritten** — an export is a copy
  of the session, not a log to append to.
* A directory that does not exist is **not** created: the command says
  which directory is missing, and the operator decides.
* On success the command reports the path, the number of messages and the
  size of what was written.

## The trap that was found while designing this

The classic console prints the result of a chat command with Rich markup::

    console.print(f"[cyan]{chat_response}[/cyan]")

The content of a session is **arbitrary text** — it is what the operator
typed and what the model answered.  Rich reads square brackets as markup,
and the result is not a cosmetic problem:

```
'user: hello [1] world'      ->  'user: hello [1] world'   (fine)
'assistant: [dim]text[/dim]' ->  'assistant: text'          (the text is eaten)
'user: a [b] c'              ->  'user: a  c'               (the text is eaten)
'user: [/nope] broken'       ->  MarkupError                (the REPL dies)
```

So the export would have printed something *different* from what the
session holds, or crashed the REPL on a closing tag.  The print of the
chat commands therefore stops interpreting markup — the content of a
session is printed **verbatim**, and the colour of the output is kept.

## The files that change

| file | what it does |
|---|---|
| `chat_manager/export.py` | **new** — renders the header and the transcript, and names the source |
| `chat_manager/manager.py` | `get_stored_messages()` — the stored messages, the way `get_history_stats()` reads them |
| `chat_manager/stats.py` | `message_text()` — the helper that reads the text of a message becomes public, so the export measures the messages the same way |
| `chat_manager/commands/cli.py` | `cmd_chat_export()` — the command |
| `chat_manager/commands/handler.py` | the dispatch of `\chat-export` |
| `components/command_registry.py` | the entry, so `\help` shows it |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | the chat commands are printed verbatim |

## What is **not** in this change

* **No format but two.**  Not text, not markdown, not JSON — the text the
  log uses, and the JSON a program reads.  A third format would be a
  format nobody asked for.
* **No export of the buffer of *another* session.**  The command works on
  the active session; `--buffer` chooses which part of it is exported.
* **No export of another session.**  The command exports the *active*
  session; `\chat-select` first is how another session is exported.
* **No new setting.**  The path is given per call, and it is not remembered.
* **The history is not trimmed, and the export is not a backup.**  The
  files of the agent are not touched by this command.
