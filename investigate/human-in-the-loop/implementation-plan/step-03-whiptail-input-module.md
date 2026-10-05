# Step 3: Whiptail Input Module

**Step:** 3 of 9  
**Goal:** Extend existing Whiptail functionality for general HITL input  
**Estimated Effort:** 3-4 days  
**Dependencies:** Step 1 (Custom HITL Events), Step 2 (Console Input Module)

---

## Overview

This step extends the existing Whiptail password module for general HITL input. It provides dialog-based interaction with timeout support, reusing patterns from the existing `WhiptailPasswordPrompter`. This module will be used when users prefer dialog-based input over console input.

## Files to Create

- `components/whiptail_input_module.py`
- `tests/test_whiptail_input_module.py`

## Implementation Details

### WhiptailInputModule Class

The module provides three main input methods (password is handled by existing module):

1. **`prompt()`** - Text input via whiptail dialog
2. **`confirm()`** - Yes/no confirmation via whiptail dialog
3. **`menu()`** - Menu selection via whiptail dialog

All methods include availability checking and fallback to default values.

## Implementation

```python
# components/whiptail_input_module.py

import asyncio
from typing import List, Optional
from components.whiptail_password import WhiptailPasswordPrompter


class WhiptailInputModule:
    """Whiptail-based input module for HITL interactions.
    
    Extends the existing WhiptailPasswordPrompter for general input.
    Provides dialog-based interaction with timeout support.
    
    See: investigate/whiptail/INVESTIGATION_REPORT.md for details
    """
    
    def __init__(self):
        self._prompter = WhiptailPasswordPrompter()
    
    @staticmethod
    def is_available() -> bool:
        """Check if whiptail is available on the system."""
        info = WhiptailPasswordPrompter.is_available()
        return info.get("available", False)
    
    async def prompt(
        self,
        message: str,
        default: str = "",
        timeout: int = 30,
        title: str = "Agent Question",
    ) -> str:
        """
        Prompt user for input via whiptail dialog with timeout.
        
        Args:
            message: Question to ask
            default: Default answer if timeout
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            User's response or default on timeout
        """
        if not self.is_available():
            return default
        
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=10,
                width=60,
                auto_exit=False,
            )
            
            def ask():
                return wt.prompt(msg=message, default=default, password=False)
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response if response.strip() else default
            
        except asyncio.TimeoutError:
            return default
        except Exception as e:
            print(f"Whiptail prompt error: {e}")
            return default
    
    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
        title: str = "Confirmation",
    ) -> bool:
        """
        Ask for yes/no confirmation via whiptail dialog.
        
        Args:
            message: Question to ask
            default_yes: Default if timeout
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            True if yes, False otherwise
        """
        if not self.is_available():
            return default_yes
        
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=10,
                width=60,
                auto_exit=False,
            )
            
            def ask():
                extra = ['--defaultno'] if not default_yes else []
                return wt.run(
                    control='yesno',
                    msg=message,
                    extra=extra,
                    exit_on=(1, 255)
                )
            
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return result.returncode == 0
            
        except asyncio.TimeoutError:
            return default_yes
        except Exception as e:
            print(f"Whiptail confirm error: {e}")
            return default_yes
    
    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = 30,
        title: str = "Select Option",
    ) -> str:
        """
        Display a menu via whiptail dialog.
        
        Args:
            message: Menu title
            options: List of option descriptions
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            Selected option or first option on timeout
        """
        if not self.is_available():
            return options[0] if options else ""
        
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=15,
                width=60,
                auto_exit=False,
            )
            
            # Format items as (tag, description) tuples
            items = [(str(i), opt) for i, opt in enumerate(options, 1)]
            
            def ask():
                return wt.menu(msg=message, items=items)
            
            loop = asyncio.get_event_loop()
            tag = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            
            try:
                idx = int(tag) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except ValueError:
                pass
            
            return options[0]  # Default
            
        except asyncio.TimeoutError:
            return options[0]
        except Exception as e:
            print(f"Whiptail menu error: {e}")
            return options[0]
```

## Deliverables

- [ ] Create `WhiptailInputModule` class
- [ ] Implement `prompt()` method with dialog support
- [ ] Implement `confirm()` method with yesno dialog
- [ ] Implement `menu()` method with menu dialog
- [ ] Add availability checking for whiptail
- [ ] Reuse existing `WhiptailPasswordPrompter` patterns
- [ ] Add unit tests with mocked whiptail
- [ ] Test fallback when whiptail is unavailable

## Success Criteria

- [ ] All whiptail methods work correctly when available
- [ ] Fallback to default values when whiptail unavailable
- [ ] Timeout handling works as expected
- [ ] Dialogs display correctly with proper titles
- [ ] Unit tests pass
- [ ] Integration with existing whiptail module works

## Next Step

Step 4: HumanLoopHandler Callback
