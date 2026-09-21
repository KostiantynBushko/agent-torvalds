#!/bin/bash
# ============================================================================
# Test Script: Bash Whiptail (native)
# ============================================================================
# This script demonstrates native whiptail usage from bash.
# Run with: bash test_bash_whiptail.sh
# ============================================================================

set -euo pipefail

WHIPTAIL_BIN="whiptail"
TITLE="Bash Whiptail Demo"
BACKTITLE="Native whiptail from bash"
HEIGHT=12
WIDTH=50

echo "=== Bash Whiptail Tests ==="
echo ""

# --- Test 1: msgbox (info dialog) ---
echo "[Test 1] msgbox: Displaying info message..."
$WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --msgbox "This is a message box from bash whiptail.\n\nEnvironment variables and bash features work directly." \
    $HEIGHT $WIDTH 2>/dev/null
echo "  Result: Exit code $?"
echo ""

# --- Test 2: yesno (confirmation) ---
echo "[Test 2] yesno: Asking for confirmation..."
if $WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --yesno "Do you want to continue?" \
    $HEIGHT $WIDTH; then
    echo "  Result: User said YES"
else
    echo "  Result: User said NO (or cancelled)"
fi
echo ""

# --- Test 3: inputbox (text input) ---
echo "[Test 3] inputbox: Asking for user input..."
INPUT=$($WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --inputbox "Enter your name:" \
    $HEIGHT $WIDTH "Default Name" 2>&1)
exit_code=$?
echo "  Exit code: $exit_code"
echo "  Input value: '$INPUT'"
echo ""

# --- Test 4: passwordbox (masked input) ---
echo "[Test 4] passwordbox: Asking for password..."
PASSWORD=$($WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --passwordbox "Enter your password:" \
    $HEIGHT $WIDTH "" 2>&1)
exit_code=$?
echo "  Exit code: $exit_code"
echo "  Password length: ${#PASSWORD} chars"
echo ""

# --- Test 5: menu (selection) ---
echo "[Test 5] menu: Selection dialog..."
CHOICE=$($WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --menu "Choose an option:" \
    $HEIGHT $WIDTH 6 \
    "1" "Option One" \
    "2" "Option Two" \
    "3" "Option Three" \
    2>&1)
exit_code=$?
echo "  Exit code: $exit_code"
echo "  Selected: '$CHOICE'"
echo ""

# --- Test 6: checklist (multi-select) ---
echo "[Test 6] checklist: Multi-select dialog..."
SELECTED=$($WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --checklist "Select items:" \
    $HEIGHT $WIDTH 6 \
    "A" "Item A" ON \
    "B" "Item B" OFF \
    "C" "Item C" ON \
    2>&1)
exit_code=$?
echo "  Exit code: $exit_code"
echo "  Selected: '$SELECTED'"
echo ""

# --- Test 7: radiolist (single select) ---
echo "[Test 7] radiolist: Single-select dialog..."
SELECTED=$($WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --radiolist "Choose one:" \
    $HEIGHT $WIDTH 6 \
    "X" "Choice X" ON \
    "Y" "Choice Y" OFF \
    "Z" "Choice Z" OFF \
    2>&1)
exit_code=$?
echo "  Exit code: $exit_code"
echo "  Selected: '$SELECTED'"
echo ""

# --- Test 8: Environment variable access ---
echo "[Test 8] Environment variable demonstration..."
MY_VAR="Hello from bash"
export MY_VAR
$WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --msgbox "Environment variable MY_VAR='$MY_VAR'\nPATH contains $(echo $PATH | wc -w) entries\nUser: $(whoami)\nHost: $(hostname)" \
    $HEIGHT $WIDTH 2>/dev/null
echo "  Result: Env vars accessible directly in bash"
echo ""

# --- Test 9: gauge (progress bar) ---
echo "[Test 9] gauge: Progress bar..."
(
    for i in $(seq 1 100); do
        echo "Updating to $i%"
        echo $i
        sleep 0.02
    done
) | $WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --gauge "Processing..." $HEIGHT $WIDTH 0
echo "  Result: Gauge completed"
echo ""

# --- Test 10: textbox (file viewer) ---
echo "[Test 10] textbox: File viewer..."
echo "This is a test file content." > /tmp/whiptail_test.txt
echo "Line 2 of the file." >> /tmp/whiptail_test.txt
echo "Line 3 of the file." >> /tmp/whiptail_test.txt
$WHIPTAIL_BIN --title "$TITLE" --backtitle "$BACKTITLE" \
    --textbox /tmp/whiptail_test.txt $HEIGHT $WIDTH 2>/dev/null
echo "  Result: Textbox displayed"
rm -f /tmp/whiptail_test.txt
echo ""

echo "=== All Bash Whiptail Tests Complete ==="
