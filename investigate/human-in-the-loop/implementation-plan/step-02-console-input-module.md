# Step 2: Console Input Module

**Step:** 2 of 9  
**Goal:** Provide text-based terminal input with timeout support  
**Estimated Effort:** 3-4 days  
**Dependencies:** Step 1 (Custom HITL Events)

---

## Overview

This step implements the console-based input module for HITL interactions. It provides async input methods with timeout support, allowing the agent to prompt users for various types of input (text, yes/no confirmation, menu selection, password) through the terminal.

## Files to Create

- `components/console_input_module.py`
- `tests/test_console_input_module.py`

## Implementation Details

### ConsoleInputModule Class

The module provides four main input methods:

1. **`prompt()`** - General text input with timeout
2. **`confirm()`** - Yes/no confirmation with default value
3. **`menu()`** - Menu selection from a list of options
4. **`password()`** - Hidden password input

All methods use `asyncio.wait_for()` for timeout handling and return default values when timeout occurs.

## Implementation

```python
# components/console_input_module.py

import asyncio
from typing import List, Optional
from rich.console import Console


class ConsoleInputModule:
    """Console-based input module for HITL interactions.
    
    Provides async input methods with timeout support.
    All methods return default values on timeout.
    """
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
    
    @staticmethod
    async def prompt(
        message: str,
        default: str = "",
        timeout: int = 30,
    ) -> str:
        """
        Prompt user for text input via console with timeout.
        
        Args:
            message: Question to ask
            default: Default answer if timeout or empty response
            timeout: Seconds to wait for input
            
        Returns:
            User's response or default on timeout/empty
        """
        loop = asyncio.get_event_loop()
        
        def ask():
            try:
                return input(message)
            except (EOFError, KeyboardInterrupt):
                return default
        
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response if response.strip() else default
        except asyncio.TimeoutError:
            return default
    
    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
    ) -> bool:
        """
        Ask for yes/no confirmation via console.
        
        Args:
            message: Question to ask
            default_yes: Default answer if timeout
            timeout: Seconds to wait
            
        Returns:
            True if yes, False otherwise
        """
        suffix = " [Y/n]" if default_yes else " [y/N]"
        full_message = f"{message}{suffix}"
        response = await ConsoleInputModule.prompt(full_message, timeout=timeout)
        
        if not response:
            return default_yes
        
        return response.lower() in ("y", "yes")
    
    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = 30,
    ) -> str:
        """
        Display a menu and get user selection.
        
        Args:
            message: Menu title
            options: List of option strings
            timeout: Seconds to wait
            
        Returns:
            Selected option or first option on timeout
        """
        self.console.print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            self.console.print(f"  [bold]{i}[/bold]. {opt}")
        
        default = "1"
        response = await ConsoleInputModule.prompt(
            "Select option [1]: ", default=default, timeout=timeout
        )
        
        try:
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        
        return options[0]  # Default to first option
    
    async def password(
        self,
        message: str = "Enter password: ",
        timeout: int = 60,
    ) -> str:
        """
        Prompt for password input (hidden).
        
        Args:
            message: Prompt message
            timeout: Seconds to wait
            
        Returns:
            Entered password or empty string on timeout
        """
        import getpass
        
        loop = asyncio.get_event_loop()
        
        def ask():
            try:
                return getpass.getpass(message)
            except (EOFError, KeyboardInterrupt):
                return ""
        
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            return ""
```

## Deliverables

- [ ] Create `ConsoleInputModule` class
- [ ] Implement `prompt()` method with timeout support
- [ ] Implement `confirm()` method with yes/no handling
- [ ] Implement `menu()` method with option selection
- [ ] Implement `password()` method with hidden input
- [ ] Add timeout handling with `asyncio.wait_for()`
- [ ] Add unit tests with mocked input
- [ ] Test all input types (text, yesno, menu, password)

## Success Criteria

- [ ] All input methods work correctly
- [ ] Timeout handling works as expected
- [ ] Default values are returned on timeout
- [ ] Menu displays options correctly
- [ ] Password input is hidden
- [ ] Unit tests pass

## Next Step

Step 3: Whiptail Input Module
