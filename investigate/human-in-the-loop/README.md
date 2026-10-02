# Human-in-the-Loop (HITL) Solution

## Overview

The **Human-in-the-Loop (HITL)** solution enables the Torvalds AI Agent to pause execution, ask clarifying questions to the user, handle timeouts with fallback answers, and resume execution after receiving user input. This feature transforms the agent from a purely autonomous system into an interactive assistant that can seek human guidance when needed.

This implementation builds upon the existing event streaming infrastructure and leverages LlamaIndex's workflow system to provide seamless human interaction capabilities.

---

## Table of Contents

- [Solution Description](#solution-description)
- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Implementation Steps](#implementation-steps)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [File Reference](#file-reference)
- [Related Investigations](#related-investigations)
- [External Resources](#external-resources)

---

## Solution Description

The HITL solution addresses a critical gap in autonomous AI agents: the inability to seek human guidance when needed. Many tasks require human judgment, confirmation, or additional context that the AI agent doesn't possess. This solution enables:

1. **Interactive Questioning**: The agent can pause execution and ask the user clarifying questions when it encounters ambiguity or needs confirmation
2. **Multiple Input Methods**: Support for both console-based text input and whiptail dialog-based input for different terminal environments
3. **Timeout Handling**: Automatic fallback answers if the user doesn't respond within a configurable timeout period, preventing the agent from hanging indefinitely
4. **Runtime Toggle**: Ability to enable/disable HITL during execution without restarting the agent
5. **Spinner Integration**: Seamless pause/resume of the console spinner during HITL prompts to maintain a clean UI

The solution integrates with the existing `EventConsumer`, `SpinnerController`, and `CallbackManager` infrastructure, extending them with HITL-specific capabilities without breaking existing functionality.

---

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Interactive Questioning** | Agent can pause and ask the user questions when clarification is needed |
| **Multiple Input Methods** | Support for both console-based and whiptail dialog-based input |
| **Timeout Handling** | Automatic fallback answers if the user doesn't respond within a specified time |
| **Runtime Toggle** | Ability to enable/disable HITL during execution without restarting |
| **Configuration Options** | Extensive CLI arguments and environment variables for customization |
| **Spinner Integration** | Seamless pause/resume of the console spinner during HITL prompts |
| **Question Detection** | Pattern matching to detect when the agent needs human input |
| **History Tracking** | Logs all questions, answers, and timeouts for review |

---

## Architecture

The HITL solution is built on top of the existing event streaming infrastructure and leverages LlamaIndex's workflow system. Key components include:

### Core Components

1. **Custom HITL Events** (`components/hitl_events.py`)
   - `AgentQuestionEvent`: Signals when the agent needs human input
   - `AgentAnswerEvent`: Carries the human's response back to the agent

2. **Input Modules**
   - `ConsoleInputModule` (`components/console_input_module.py`): Text-based terminal input with timeout support
   - `WhiptailInputModule` (`components/whiptail_input_module.py`): Dialog-based input using whiptail

3. **HumanLoopHandler** (`components/human_loop_handler.py`)
   - Callback handler that intercepts agent events
   - Detects when human input is needed
   - Manages the HITL flow (prompt → input → response → resume)

4. **EventConsumer Integration** (`components/event_consumer.py`)
   - Enhanced to handle HITL-specific events
   - Routes `InputRequiredEvent` and `AgentQuestionEvent` to appropriate handlers

5. **Timeout Manager** (`components/timeout_manager.py`)
   - Centralized timeout handling with fallback logic
   - Tracks timed-out questions for review

6. **Runtime Toggle** (`components/hitl_runtime_toggle.py`)
   - Dynamic enable/disable of HITL during execution
   - Thread-safe state management

7. **Agent Integration** (`agent-torvalds.py`)
   - Full wiring into the agent workflow
   - CLI arguments and environment variable configuration

---

## Implementation Steps

The solution was implemented in 9 steps, each documented in detail in the `implementation-plan/` subfolder:

| Step | Component | Description | Documentation |
|------|-----------|-------------|---------------|
| 1 | Custom HITL Events | Define `AgentQuestionEvent` and `AgentAnswerEvent` classes | [step-01-custom-hitl-events.md](implementation-plan/step-01-custom-hitl-events.md) |
| 2 | Console Input Module | Implement `ConsoleInputModule` with `prompt()`, `confirm()`, `menu()`, `password()` | [step-02-console-input-module.md](implementation-plan/step-02-console-input-module.md) |
| 3 | Whiptail Input Module | Implement `WhiptailInputModule` with dialog-based input | [step-03-whiptail-input-module.md](implementation-plan/step-03-whiptail-input-module.md) |
| 4 | HumanLoopHandler Callback | Create callback handler that intercepts HITL events | [step-04-human-loop-handler-callback.md](implementation-plan/step-04-human-loop-handler-callback.md) |
| 5 | EventConsumer Integration | Integrate HITL handling into existing EventConsumer | [step-05-eventconsumer-integration.md](implementation-plan/step-05-eventconsumer-integration.md) |
| 6 | Timeout Manager | Centralized timeout management for HITL prompts | [step-06-timeout-manager.md](implementation-plan/step-06-timeout-manager.md) |
| 7 | Runtime Toggle | Allow dynamic enable/disable of HITL during execution | [step-07-runtime-toggle.md](implementation-plan/step-07-runtime-toggle.md) |
| 8 | Agent Integration | Wire all HITL components into the agent workflow | [step-08-agent-integration.md](implementation-plan/step-08-agent-integration.md) |
| 9 | Configuration & CLI | Add CLI flags and environment variable support | [step-09-configuration-cli.md](implementation-plan/step-09-configuration-cli.md) |

---

## Configuration

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--no-hitl` | Disable Human-in-the-Loop interactions (HITL is enabled by default) | - |
| `--hitl-method` | Input method for HITL prompts (`console` or `whiptail`) | `console` |
| `--hitl-timeout` | Timeout in seconds for HITL prompts | `30` |
| `--hitl-default-answer` | Default fallback answer on timeout | `""` (empty) |
| `--hitl-no-runtime-toggle` | Disable runtime toggle commands | - |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TORVALDS_HITL_ENABLED` | Enable/disable HITL | `true` |
| `TORVALDS_HITL_METHOD` | Input method (`console` or `whiptail`) | `console` |
| `TORVALDS_HITL_TIMEOUT` | Default timeout in seconds | `30` |
| `TORVALDS_HITL_DEFAULT_ANSWER` | Default fallback answer | `""` (empty) |
| `TORVALDS_HITL_RUNTIME_TOGGLE` | Enable/disable runtime toggle | `true` |

### Runtime Commands

When HITL is enabled, you can use the following commands during agent execution:

| Command | Description |
|---------|-------------|
| `\hitl-status` | Show current HITL status |
| `\toggle-hitl` | Toggle HITL on/off |
| `\hitl-on` | Enable HITL |
| `\hitl-off` | Disable HITL |

---

## Usage Examples

### Start agent with HITL enabled (default)
```bash
python agent-torvalds.py --hitl-method console --hitl-timeout 60
```

### Start agent with HITL disabled
```bash
python agent-torvalds.py --no-hitl
```

### Start agent with whiptail input method
```bash
python agent-torvalds.py --hitl-method whiptail
```

### Start agent with custom default answer
```bash
python agent-torvalds.py --hitl-default-answer "yes"
```

### Using environment variables
```bash
export TORVALDS_HITL_ENABLED=true
export TORVALDS_HITL_METHOD=console
export TORVALDS_HITL_TIMEOUT=60
python agent-torvalds.py
```

---

## File Reference

### Investigation Documents

| File | Description |
|------|-------------|
| [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) | Comprehensive gap analysis and architecture proposal |
| [PROPOSAL_step_by_step.md](PROPOSAL_step_by_step.md) | Detailed step-by-step implementation plan |
| [llama-human-in-loop-task.md](llama-human-in-loop-task.md) | Original task requirements |

### Implementation Plan Documents

| File | Description |
|------|-------------|
| [implementation-plan/step-01-custom-hitl-events.md](implementation-plan/step-01-custom-hitl-events.md) | Step 1: Foundation - Custom HITL Events |
| [implementation-plan/step-02-console-input-module.md](implementation-plan/step-02-console-input-module.md) | Step 2: Console Input Module |
| [implementation-plan/step-03-whiptail-input-module.md](implementation-plan/step-03-whiptail-input-module.md) | Step 3: Whiptail Input Module |
| [implementation-plan/step-04-human-loop-handler-callback.md](implementation-plan/step-04-human-loop-handler-callback.md) | Step 4: HumanLoopHandler Callback |
| [implementation-plan/step-05-eventconsumer-integration.md](implementation-plan/step-05-eventconsumer-integration.md) | Step 5: EventConsumer Integration |
| [implementation-plan/step-06-timeout-manager.md](implementation-plan/step-06-timeout-manager.md) | Step 6: Timeout Manager |
| [implementation-plan/step-07-runtime-toggle.md](implementation-plan/step-07-runtime-toggle.md) | Step 7: Runtime Toggle |
| [implementation-plan/step-08-agent-integration.md](implementation-plan/step-08-agent-integration.md) | Step 8: Agent Integration |
| [implementation-plan/step-09-configuration-cli.md](implementation-plan/step-09-configuration-cli.md) | Step 9: Configuration & CLI |

---

## Related Investigations

- [LlamaIndex Workflow Investigation](../llama-index-workflow/INVESTIGATION_REPORT.md) - Workflow architecture and event system
- [Whiptail Investigation](../whiptail/INVESTIGATION_REPORT.md) - Whiptail bash vs Python package analysis

---

## External Resources

- [LlamaIndex HITL Documentation](https://developers.llamaindex.ai/python/framework/understanding/agent/human_in_the_loop/)
- [LlamaIndex Workflows](https://developers.llamaindex.ai/python/llamaagents/workflows/)
- [Full HITL Example](https://github.com/run-llama/python-agents-tutorial/blob/main/5_human_in_the_loop.py)

---

## Status

✅ **Implemented** - All 9 steps completed and merged into `feature/human-in-the-loop` branch.

---

*Generated by Torvalds AI Agent*  
*Branch: feature/human-in-the-loop*  
*Date: 2025-01-15*
