#!/usr/bin/env python3
"""
Side-by-Side Comparison: Bash whiptail vs Python whiptail package
================================================================
This script demonstrates equivalent operations in both approaches.
Run with: python3 comparison_example.py
"""

import subprocess
import os
import sys
from whiptail import Whiptail

# ============================================================================
# Configuration
# ============================================================================
TITLE = "Whiptail Comparison"
BACKTITLE = "Bash vs Python"
HEIGHT = 12
WIDTH = 50

# Python whiptail instance
wt = Whiptail(
    title=TITLE,
    backtitle=BACKTITLE,
    height=HEIGHT,
    width=WIDTH,
    auto_exit=False
)

print("=" * 60)
print("  Whiptail: Bash vs Python Package Comparison")
print("=" * 60)
print()

# ============================================================================
# Example 1: Message Box
# ============================================================================
print("[Example 1] Message Box")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("  whiptail --title 'Title' --msgbox 'Message' 10 50")
print("  # Exit code 0 = OK, 1 = Cancel")

# PYTHON APPROACH
print("\n  PYTHON:")
print("  wt.alert('Message')")
print("  # auto_exit=False, no return value")

# ============================================================================
# Example 2: Yes/No Confirmation
# ============================================================================
print("\n[Example 2] Yes/No Confirmation")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  if whiptail --yesno "Continue?" 10 50; then
      echo "User said YES"
  else
      echo "User said NO"
  fi""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  if wt.confirm("Continue?"):
      print("User said YES")
  else:
      print("User said NO")
  # Returns: True/False boolean""")

# ============================================================================
# Example 3: Input Box
# ============================================================================
print("\n[Example 3] Input Box")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  INPUT=$(whiptail --inputbox "Name:" 10 50 "Default" 2>&1)
  EXIT_CODE=$?
  echo "Input: $INPUT"
  # Value comes from stderr (2>&1)""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  input_value = wt.prompt("Name:", default="Default")
  print(f"Input: {input_value}")
  # Returns: string directly""")

# ============================================================================
# Example 4: Password Box
# ============================================================================
print("\n[Example 4] Password Box")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  PASS=$(whiptail --passwordbox "Password:" 10 50 2>&1)
  # Same as inputbox but masked""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  password = wt.prompt("Password:", password=True)
  # Same method, different parameter""")

# ============================================================================
# Example 5: Menu Selection
# ============================================================================
print("\n[Example 5] Menu Selection")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  CHOICE=$(whiptail --menu "Choose:" 15 50 10 \\
      "1" "Option One" \\
      "2" "Option Two" \\
      "3" "Option Three" \\
      2>&1)
  # Tag and description as alternating args""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  choice = wt.menu(
      "Choose:",
      items=[
          ("1", "Option One"),
          ("2", "Option Two"),
          ("3", "Option Three"),
      ]
  )
  # List of (tag, description) tuples""")

# ============================================================================
# Example 6: Checklist
# ============================================================================
print("\n[Example 6] Checklist (Multi-Select)")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  SELECTED=$(whiptail --checklist "Select:" 15 50 10 \\
      "A" "Item A" ON \\
      "B" "Item B" OFF \\
      "C" "Item C" ON \\
      2>&1)
  # Tag, description, status as alternating args""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  selected = wt.checklist(
      "Select:",
      items=[
          ("A", "Item A", "ON"),
          ("B", "Item B", "OFF"),
          ("C", "Item C", "ON"),
      ]
  )
  # Returns: list of selected tags""")

# ============================================================================
# Example 7: Environment Variables
# ============================================================================
print("\n[Example 7] Environment Variables")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  MY_VAR="Hello"
  whiptail --msgbox "VAR=$MY_VAR" 10 50
  # Direct access to shell variables""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  import os
  my_var = os.environ.get('MY_VAR', 'default')
  wt.alert(f"VAR={my_var}")
  # Access via os.environ""")

# ============================================================================
# Example 8: Custom Parameters
# ============================================================================
print("\n[Example 8] Custom Parameters")
print("-" * 40)

# BASH APPROACH
print("\n  BASH:")
print("""  whiptail --yesno "Continue?" \\
      --defaultno \\
      --yes-button "Go" \\
      --no-button "Stop" \\
      10 50""")

# PYTHON APPROACH
print("\n  PYTHON:")
print("""  wt.run(
      control='yesno',
      msg='Continue?',
      extra=[
          '--defaultno',
          '--yes-button', 'Go',
          '--no-button', 'Stop',
      ]
  )
  # Use run() with extra=[] for custom flags""")

# ============================================================================
# Summary Table
# ============================================================================
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
print("""
┌─────────────┬────────────────────┬─────────────────────┐
│ Feature     │ Bash whiptail      │ Python Package      │
├─────────────┼────────────────────┼─────────────────────┤
│ msgbox      │ ✓ exit code        │ wt.alert()          │
│ yesno       │ ✓ exit code        │ wt.confirm() bool   │
│ inputbox    │ ✓ stderr parse     │ wt.prompt() str     │
│ passwordbox │ ✓ stderr parse     │ wt.prompt(pw=True)  │
│ menu        │ ✓ stderr parse     │ wt.menu() str       │
│ checklist   │ ✓ stderr parse     │ wt.checklist() list │
│ radiolist   │ ✓ stderr parse     │ wt.radiolist() list │
│ textbox     │ ✓                  │ wt.view_file()      │
│ gauge       │ ✓                  │ ✗ NOT SUPPORTED     │
│ infobox     │ ✓                  │ ✗ NOT SUPPORTED     │
│             │                    │                     │
│ Env Vars    │ Direct $VAR        │ os.environ['VAR']   │
│ Custom      │ Direct flags       │ run(extra=[...])    │
│ Error       │ Check $?           │ try/except          │
│ Type Safe   │ No (all strings)   │ Yes (bool, list)    │
└─────────────┴────────────────────┴─────────────────────┘

KEY INSIGHTS:
1. Python package is a WRAPPER - still needs /usr/bin/whiptail
2. Python package is cleaner for basic dialogs
3. Bash still needed for gauge, infobox, advanced features
4. Python package v0.2 is from 2013 - limited maintenance
5. Consider modern alternatives: questionary, rich, prompt_toolkit
""")

print("=" * 60)
print("  Investigation Complete!")
print("=" * 60)
