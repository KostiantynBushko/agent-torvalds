#!/usr/bin/env python3
"""
Test Script: Python whiptail Package
====================================
This script demonstrates usage of the 'whiptail' Python package.
Package: whiptail 0.2 by Marwan Alsabbagh
Source: https://github.com/marwano/whiptail

Run with: python3 test_python_whiptail.py
"""

import os
import sys
import subprocess

# Import the whiptail package
try:
    from whiptail import Whiptail
    print("✓ Successfully imported whiptail package")
except ImportError as e:
    print(f"✗ Failed to import whiptail: {e}")
    sys.exit(1)

print(f"\n=== Python Whiptail Tests ===\n")

# --- Setup ---
wt = Whiptail(
    title="Python Whiptail Demo",
    backtitle="Using whiptail Python package",
    height=12,
    width=50,
    auto_exit=False  # Don't auto-exit on cancel
)

# --- Test 1: alert (msgbox) ---
print("[Test 1] alert: Display info message...")
try:
    wt.alert("This is a message box from Python whiptail.\n\nThe Python package wraps bash whiptail.")
    print("  Result: alert() completed")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 2: confirm (yesno) ---
print("[Test 2] confirm: Ask for confirmation...")
try:
    result = wt.confirm("Do you want to continue?")
    print(f"  Result: User said {'YES' if result else 'NO'}")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 3: prompt (inputbox) ---
print("[Test 3] prompt: Ask for user input...")
try:
    input_value = wt.prompt("Enter your name:", default="Python User")
    print(f"  Input value: '{input_value}'")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 4: prompt with password ---
print("[Test 4] prompt: Ask for password (masked)...")
try:
    password = wt.prompt("Enter your password:", default="", password=True)
    print(f"  Password length: {len(password)} chars")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 5: menu ---
print("[Test 5] menu: Selection dialog...")
try:
    # Items can be strings or (key, value) tuples
    choice = wt.menu(
        msg="Choose an option:",
        items=[
            ("1", "Option One"),
            ("2", "Option Two"),
            ("3", "Option Three"),
        ]
    )
    print(f"  Selected: '{choice}'")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 6: checklist ---
print("[Test 6] checklist: Multi-select dialog...")
try:
    # Items: (tag, description, status) where status is 'ON' or 'OFF'
    selected = wt.checklist(
        msg="Select items:",
        items=[
            ("A", "Item A", "ON"),
            ("B", "Item B", "OFF"),
            ("C", "Item C", "ON"),
        ]
    )
    print(f"  Selected: {selected}")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 7: radiolist ---
print("[Test 7] radiolist: Single-select dialog...")
try:
    selected = wt.radiolist(
        msg="Choose one:",
        items=[
            ("X", "Choice X", "ON"),
            ("Y", "Choice Y", "OFF"),
            ("Z", "Choice Z", "OFF"),
        ]
    )
    print(f"  Selected: {selected}")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 8: Environment variables access ---
print("[Test 8] Environment variable demonstration...")
try:
    # Access env vars from Python
    user = os.environ.get("USER", "unknown")
    home = os.environ.get("HOME", "unknown")
    hostname = subprocess.check_output(["hostname"], text=True).strip()
    
    wt.alert(
        f"Environment info from Python:\n"
        f"USER={user}\n"
        f"HOME={home}\n"
        f"HOSTNAME={hostname}\n"
        f"Python version: {sys.version.split()[0]}"
    )
    print("  Result: Env vars accessible via os.environ")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 9: view_file (textbox) ---
print("[Test 9] view_file: File viewer...")
try:
    # Create a temp file
    test_file = "/tmp/whiptail_python_test.txt"
    with open(test_file, "w") as f:
        f.write("Line 1: This is test content.\n")
        f.write("Line 2: Created by Python.\n")
        f.write("Line 3: Viewed via whiptail.\n")
    
    wt.view_file(test_file)
    print("  Result: view_file() completed")
    os.remove(test_file)
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 10: Direct run() method ---
print("[Test 10] Direct run() method: Custom whiptail call...")
try:
    # The run() method gives more control
    response = wt.run(
        control="yesno",
        msg="Custom yesno dialog",
        extra=["--defaultno"],  # Extra parameters
        exit_on=(1, 255)
    )
    print(f"  Response: returncode={response.returncode}, value='{response.value}'")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 11: Check Response namedtuple ---
print("[Test 11] Response object inspection...")
try:
    from whiptail import Response
    print(f"  Response fields: {Response._fields}")
    print(f"  Response is a namedtuple: {isinstance(Response, type)}")
except Exception as e:
    print(f"  Error: {e}")
print()

# --- Test 12: Package version ---
print("[Test 12] Package info...")
try:
    import whiptail
    print(f"  whiptail version: {whiptail.__version__}")
    print(f"  whiptail file: {whiptail.__file__}")
except Exception as e:
    print(f"  Error: {e}")
print()

print("=== All Python Whiptail Tests Complete ===")
