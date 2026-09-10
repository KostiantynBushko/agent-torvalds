"""
Linux Toolkit for executing shell commands and parsing responses.

This module provides functionality to execute shell commands on Linux systems
and properly parse both stdout and stderr outputs.
"""

import subprocess
import logging
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def execute_shell_command(command: str, 
                         timeout: int = 30,
                         cwd: Optional[str] = None,
                         shell: bool = True) -> Dict[str, any]:
    """
    Execute a shell command and return structured response with stdout, stderr, and return code.
    
    Args:
        command (str): The shell command to execute
        timeout (int): Timeout in seconds for the command execution (default: 30)
        cwd (str, optional): Working directory for the command
        shell (bool): Whether to use shell (default: True)
        
    Returns:
        Dict containing 'stdout', 'stderr', 'returncode', and 'success' keys
    """
    try:
        logger.info(f"Executing command: {command}")
        
        # Execute the command
        result = subprocess.run(
            command,
            shell=shell,
            cwd=cwd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Parse the output
        response = {
            'stdout': result.stdout.strip() if result.stdout else '',
            'stderr': result.stderr.strip() if result.stderr else '',
            'returncode': result.returncode,
            'success': result.returncode == 0
        }
        
        # Log the results
        if response['success']:
            logger.info(f"Command executed successfully. Return code: {response['returncode']}")
        else:
            logger.warning(f"Command failed with return code: {response['returncode']}")
            if response['stderr']:
                logger.warning(f"Error output: {response['stderr']}")
        
        return response
        
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds: {command}"
        logger.error(error_msg)
        return {
            'stdout': '',
            'stderr': error_msg,
            'returncode': -1,
            'success': False
        }
    except Exception as e:
        error_msg = f"Error executing command '{command}': {str(e)}"
        logger.error(error_msg)
        return {
            'stdout': '',
            'stderr': error_msg,
            'returncode': -1,
            'success': False
        }


def execute_multiple_commands(commands: List[str], 
                            timeout: int = 30) -> List[Dict[str, any]]:
    """
    Execute multiple shell commands sequentially and return results for each.
    
    Args:
        commands (List[str]): List of shell commands to execute
        timeout (int): Timeout in seconds for each command execution
        
    Returns:
        List of response dictionaries for each command
    """
    results = []
    for i, command in enumerate(commands):
        logger.info(f"Executing command {i+1}/{len(commands)}: {command}")
        result = execute_shell_command(command, timeout)
        results.append(result)
    return results


def parse_command_output(output: str) -> Dict[str, any]:
    """
    Parse command output into structured format.
    
    Args:
        output (str): Raw output string from command
        
    Returns:
        Dictionary with parsed content
    """
    if not output:
        return {'lines': [], 'count': 0}
    
    lines = output.strip().split('\n')
    return {
        'lines': lines,
        'count': len(lines),
        'first_line': lines[0] if lines else '',
        'last_line': lines[-1] if lines else ''
    }


def get_system_info() -> Dict[str, str]:
    """
    Get basic system information using shell commands.
    
    Returns:
        Dictionary with system information
    """
    info = {}
    
    # Get OS information
    result = execute_shell_command('uname -a')
    if result['success']:
        info['os_info'] = result['stdout']
    
    # Get CPU info
    result = execute_shell_command('lscpu | head -n 10')
    if result['success']:
        info['cpu_info'] = result['stdout']
    
    # Get memory info
    result = execute_shell_command('free -h')
    if result['success']:
        info['memory_info'] = result['stdout']
    
    # Get disk usage
    result = execute_shell_command('df -h')
    if result['success']:
        info['disk_usage'] = result['stdout']
    
    return info


def check_file_permissions(filepath: str) -> Dict[str, any]:
    """
    Check file permissions using shell commands.
    
    Args:
        filepath (str): Path to the file
        
    Returns:
        Dictionary with permission information
    """
    result = execute_shell_command(f'ls -l {filepath}')
    
    if result['success']:
        # Parse the ls output
        output_lines = result['stdout'].split('\n')
        if output_lines:
            permissions = output_lines[0].split()[0] if len(output_lines[0].split()) > 0 else ''
            owner = output_lines[0].split()[2] if len(output_lines[0].split()) > 2 else ''
            group = output_lines[0].split()[3] if len(output_lines[0].split()) > 3 else ''
            
            return {
                'permissions': permissions,
                'owner': owner,
                'group': group,
                'success': True
            }
    
    return {
        'permissions': '',
        'owner': '',
        'group': '',
        'success': False,
        'error': result['stderr'] if 'stderr' in result else 'Unknown error'
    }


def run_command_with_env(command: str, env_vars: Dict[str, str]) -> Dict[str, any]:
    """
    Execute a shell command with custom environment variables.
    
    Args:
        command (str): The shell command to execute
        env_vars (Dict[str, str]): Dictionary of environment variables
        
    Returns:
        Dictionary with command execution results
    """
    try:
        # Create a copy of the current environment
        env = subprocess.os.environ.copy()
        
        # Update with custom environment variables
        env.update(env_vars)
        
        logger.info(f"Executing command with custom env: {command}")
        
        result = subprocess.run(
            command,
            shell=True,
            env=env,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        response = {
            'stdout': result.stdout.strip() if result.stdout else '',
            'stderr': result.stderr.strip() if result.stderr else '',
            'returncode': result.returncode,
            'success': result.returncode == 0
        }
        
        return response
        
    except Exception as e:
        error_msg = f"Error executing command with custom env: {str(e)}"
        logger.error(error_msg)
        return {
            'stdout': '',
            'stderr': error_msg,
            'returncode': -1,
            'success': False
        }


# Example usage function
def example_usage():
    """Example of how to use the Linux toolkit functions."""
    
    print("=== Linux Toolkit Examples ===\n")
    
    # Example 1: Simple command execution
    print("1. Simple command execution:")
    result = execute_shell_command('echo "Hello, World!"')
    print(f"Success: {result['success']}")
    print(f"Output: {result['stdout']}")
    print()
    
    # Example 2: Command with error handling
    print("2. Command with error handling:")
    result = execute_shell_command('ls /nonexistent/directory')
    print(f"Success: {result['success']}")
    print(f"Error output: {result['stderr']}")
    print()
    
    # Example 3: Multiple commands
    print("3. Multiple commands execution:")
    commands = ['whoami', 'pwd', 'date']
    results = execute_multiple_commands(commands)
    for i, res in enumerate(results):
        print(f"Command {i+1}: {commands[i]}")
        print(f"  Success: {res['success']}")
        print(f"  Output: {res['stdout'][:50]}...")
        print()
    
    # Example 4: System info
    print("4. System information:")
    sys_info = get_system_info()
    for key, value in sys_info.items():
        print(f"{key}: {value[:100]}...")


if __name__ == "__main__":
    example_usage()