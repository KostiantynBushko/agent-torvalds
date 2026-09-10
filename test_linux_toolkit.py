"""
Test script for the Linux toolkit functionality.
"""

import sys
import os

# Add the current directory to Python path to import our module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_linux_toolkit import (
    execute_shell_command,
    execute_multiple_commands,
    get_system_info,
    check_file_permissions
)

def test_basic_command():
    """Test basic command execution."""
    print("Testing basic command execution...")
    
    # Test a simple command
    result = execute_shell_command('echo "Hello, Linux Toolkit!"')
    
    print(f"Command: echo \"Hello, Linux Toolkit!\"")
    print(f"Success: {result['success']}")
    print(f"Output: {result['stdout']}")
    print(f"Error: {result['stderr']}")
    print()

def test_command_with_error():
    """Test command that should fail."""
    print("Testing command with expected error...")
    
    # Test a command that should fail
    result = execute_shell_command('ls /nonexistent/directory')
    
    print(f"Command: ls /nonexistent/directory")
    print(f"Success: {result['success']}")
    print(f"Output: {result['stdout']}")
    print(f"Error: {result['stderr']}")
    print()

def test_multiple_commands():
    """Test execution of multiple commands."""
    print("Testing multiple command execution...")
    
    commands = ['whoami', 'pwd', 'date']
    results = execute_multiple_commands(commands)
    
    for i, (command, result) in enumerate(zip(commands, results)):
        print(f"Command {i+1}: {command}")
        print(f"  Success: {result['success']}")
        print(f"  Output: {result['stdout'][:50]}...")
        print()

def test_system_info():
    """Test system information gathering."""
    print("Testing system info gathering...")
    
    sys_info = get_system_info()
    
    for key, value in sys_info.items():
        print(f"{key}: {value[:100] if value else 'N/A'}")
    print()

def test_file_permissions():
    """Test file permission checking."""
    print("Testing file permission checking...")
    
    # Test with current directory
    result = check_file_permissions('.')
    print(f"Current directory permissions: {result}")
    print()

if __name__ == "__main__":
    print("Running Linux Toolkit Tests\n")
    
    try:
        test_basic_command()
        test_command_with_error()
        test_multiple_commands()
        test_system_info()
        test_file_permissions()
        
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()