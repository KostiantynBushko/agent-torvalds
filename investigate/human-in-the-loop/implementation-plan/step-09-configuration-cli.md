# Step 9: Configuration & CLI

**Step:** 9 of 9  
**Goal:** Add CLI flags and configuration for HITL settings  
**Estimated Effort:** 3-4 days  
**Dependencies:** Step 8 (Agent Integration)

---

## Overview

This final step adds CLI arguments and configuration options for HITL settings. It allows users to configure HITL behavior through command-line flags, environment variables, and configuration files.

## Files to Modify

- `agent-torvalds.py` (CLI argument parser)
- `README.md` (documentation)

## Implementation Details

### CLI Arguments

```python
# Add CLI arguments
parser.add_argument(
    "--hitl-enabled",
    action="store_true",
    default=True,
    help="Enable Human-in-the-Loop interactions (default: True)",
)

parser.add_argument(
    "--hitl-disabled",
    action="store_true",
    help="Disable Human-in-the-Loop interactions at startup",
)

parser.add_argument(
    "--hitl-method",
    choices=["console", "whiptail"],
    default="console",
    help="Input method for HITL prompts (default: console)",
)

parser.add_argument(
    "--hitl-timeout",
    type=int,
    default=30,
    help="Timeout in seconds for HITL prompts (default: 30)",
)

parser.add_argument(
    "--hitl-default-answer",
    type=str,
    default="",
    help="Default fallback answer on timeout (default: empty)",
)

parser.add_argument(
    "--hitl-no-runtime-toggle",
    action="store_true",
    help="Disable runtime toggle commands (toggle-hitl, hitl-status, etc.)",
)
```

### Environment Variable Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TORVALDS_HITL_ENABLED` | Enable/disable HITL | `true` |
| `TORVALDS_HITL_METHOD` | Input method (console/whiptail) | `console` |
| `TORVALDS_HITL_TIMEOUT` | Timeout in seconds | `30` |
| `TORVALDS_HITL_DEFAULT_ANSWER` | Default answer on timeout | `""` |
| `TORVALDS_HITL_RUNTIME_TOGGLE` | Enable runtime toggle | `true` |

### Usage Examples

```bash
# Enable HITL with console input (default)
./agent-torvalds.py "Your query here"

# Enable HITL with whiptail input
./agent-torvalds.py --hitl-method whiptail "Your query here"

# Disable HITL at startup
./agent-torvalds.py --hitl-disabled "Your query here"

# Custom timeout
./agent-torvalds.py --hitl-timeout 60 "Your query here"

# Custom default answer
./agent-torvalds.py --hitl-default-answer "yes" "Your query here"
```

## Deliverables

- [ ] Add CLI arguments for HITL configuration
- [ ] Add `--hitl-disabled` flag for initial disable
- [ ] Add `--hitl-no-runtime-toggle` to disable inline commands
- [ ] Add environment variable overrides
- [ ] Update help text
- [ ] Update README with HITL usage and runtime toggle commands
- [ ] Add configuration examples

## Success Criteria

- [ ] All CLI arguments work correctly
- [ ] Environment variables override CLI defaults
- [ ] Help text is clear and comprehensive
- [ ] README includes HITL documentation
- [ ] Configuration examples are provided
- [ ] Integration tests pass

## Final Deliverables

After completing this step, the full HITL system will be ready with:

- [ ] Custom HITL events
- [ ] Console input module
- [ ] Whiptail input module
- [ ] HumanLoopHandler callback
- [ ] EventConsumer integration
- [ ] Timeout manager
- [ ] Runtime toggle
- [ ] Agent integration
- [ ] CLI configuration
- [ ] Documentation
- [ ] Unit tests
- [ ] Integration tests

## Next Steps

After completing all steps:

1. **Testing** - Run comprehensive tests
2. **Documentation** - Update README and user guide
3. **Release** - Prepare for release
4. **Monitoring** - Track usage and performance
