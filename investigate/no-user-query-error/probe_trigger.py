"""
Probe: what exactly makes the Ollama Jinja template raise
"No user query found in messages."?

The model template (richardyoung/qwen3.6-27b-abliterated:Q4_K_M) contains:

    {%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
    {%- for message in messages[::-1] %}
        {%- if ns.multi_step_tool and message.role == "user" %}
            {%- set content = render_content(message.content, false)|trim %}
            {%- if not(content.startswith('<tool_response>') and content.endswith('</tool_response>')) %}
                {%- set ns.multi_step_tool = false %}
                ...
    {%- if ns.multi_step_tool %}
        {{- raise_exception('No user query found in messages.') }}
    {%- endif %}

So the error fires iff *no* message has role == "user" with content that is
not a <tool_response>...</tool_response> wrapper.

This probe sends real requests to the local Ollama server and reports which
shapes fail.  It uses `stream=False` and a tiny `num_predict` so it is fast
and does not generate long answers.
"""

import json
import urllib.request
import urllib.error

OLLAMA = "http://localhost:11434"
MODEL = "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"


def chat(messages, model=MODEL, num_predict=1):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": num_predict},
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return "OK", resp.read().decode()[:200]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"HTTP {e.code}", body[:400]
    except Exception as e:  # noqa: BLE001
        return "EXC", repr(e)[:300]


CASES = [
    (
        "A: plain user message",
        [{"role": "user", "content": "merge the excel files"}],
    ),
    (
        "B: user query + assistant tool_call + tool result",
        [
            {"role": "user", "content": "merge the excel files"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_xlsx",
                            "arguments": {"path": "a.xlsx"},
                        }
                    }
                ],
            },
            {"role": "tool", "content": "row1\nrow2"},
        ],
    ),
    (
        "C: ONLY tool results (no user query) -- role=tool",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "read_xlsx", "arguments": {}}}
                ],
            },
            {"role": "tool", "content": "row1\nrow2"},
        ],
    ),
    (
        "D: ONLY tool results expressed as role=user + <tool_response>",
        [
            {"role": "user", "content": "<tool_response>\nrow1\nrow2\n</tool_response>"},
        ],
    ),
    (
        "E: user query only AFTER a tool response (reverse-scan should find it)",
        [
            {"role": "user", "content": "<tool_response>\nrow1\n</tool_response>"},
            {"role": "user", "content": "merge the excel files"},
        ],
    ),
    (
        "F: assistant-only, no user at all",
        [{"role": "assistant", "content": "I will merge them."}],
    ),
    (
        "G: user query present but empty string",
        [{"role": "user", "content": ""}],
    ),
]


def main():
    print("=" * 78)
    print("PROBE: which message shapes trigger 'No user query found in messages.'")
    print(f"model: {MODEL}")
    print("=" * 78)

    for label, messages in CASES:
        status, body = chat(messages)
        is_target = "No user query found" in body
        flag = "  <== TARGET ERROR" if is_target else ""
        print(f"\n[{status}]{flag} {label}")
        print("   messages: " + json.dumps(messages)[:220])
        if status != "OK":
            print("   body: " + body.replace("\n", " ")[:300])

    print("\n" + "=" * 78)
    print("DONE")
    print("=" * 78)


if __name__ == "__main__":
    main()
