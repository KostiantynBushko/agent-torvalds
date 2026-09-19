"""
Linux Toolkit - Shell command execution and system inspection.

This module provides functionality to execute shell commands on Linux systems,
parse outputs, check file permissions, and gather system information.

Category: System
Retriever Keywords: shell, command, linux, execute, system, permissions, environment

Prerequisites:
    - Linux/Unix-like operating system
    - Appropriate shell access and permissions
"""
import subprocess
import os
import logging
from typing import Dict, List, Optional, Any
from llama_index.core.tools import FunctionTool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def execute_shell_command(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    shell: bool = True,
) -> Dict[str, Any]:
    """
    Execute a shell command and return structured response with stdout, stderr, and return code.
    
    Use this tool for running any shell command, scripting, or system operations.
    Supports timeouts, custom working directories, and non-shell execution.
    
    Args:
        command (str): The shell command to execute
        timeout (int): Timeout in seconds for the command execution (default: 30)
        cwd (str, optional): Working directory for the command
        shell (bool): Whether to use shell (default: True)
        
    Returns:
        Dict containing 'stdout', 'stderr', 'returncode', and 'success' keys
        
    Example:
        >>> execute_shell_command("ls -la")
        {'stdout': 'total 48\\n...', 'stderr': '', 'returncode': 0, 'success': True}
        
        >>> execute_shell_command("ls /nonexistent")
        {'stdout': '', 'stderr': 'ls: cannot access...', 'returncode': 2, 'success': False}
        
    Keywords: execute, run, shell, command, terminal, bash, stdout, stderr
    """
    try:
        logger.info(f"Executing command: {command}")
        
        result = subprocess.run(
            command,
            shell=shell,
            cwd=cwd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        response = {
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
        
        if response["success"]:
            logger.info(f"Command executed successfully. Return code: {response['returncode']}")
        else:
            logger.warning(f"Command failed with return code: {response['returncode']}")
            if response["stderr"]:
                logger.warning(f"Error output: {response['stderr']}")
        
        return response
        
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds: {command}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
        }
    except Exception as e:
        error_msg = f"Error executing command '{command}': {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
        }


def execute_multiple_commands(commands: List[str], timeout: int = 30) -> List[Dict[str, Any]]:
    """
    Execute multiple shell commands sequentially and return results for each.
    
    Use this tool for running a series of commands, batch operations, or pipelines.
    Commands are executed one after another, not in parallel.
    
    Args:
        commands (List[str]): List of shell commands to execute
        timeout (int): Timeout in seconds for each command execution
        
    Returns:
        List of response dictionaries for each command
        
    Example:
        >>> execute_multiple_commands(["whoami", "pwd", "date"])
        [{'stdout': 'user', ...}, {'stdout': '/home/user', ...}, ...]
        
    Keywords: multiple, batch, sequential, pipeline, series, commands
    """
    results = []
    for i, command in enumerate(commands):
        logger.info(f"Executing command {i+1}/{len(commands)}: {command}")
        result = execute_shell_command(command, timeout)
        results.append(result)
    return results


def parse_command_output(output: str) -> Dict[str, Any]:
    """
    Parse command output into structured format.
    
    Use this tool to split command output into lines and extract metadata.
    
    Args:
        output (str): Raw output string from command
        
    Returns:
        Dictionary with parsed content:
            - 'lines': List of lines
            - 'count': Number of lines
            - 'first_line': First line (if any)
            - 'last_line': Last line (if any)
            
    Example:
        >>> parse_command_output("line1\\nline2\\nline3")
        {'lines': ['line1', 'line2', 'line3'], 'count': 3, 'first_line': 'line1', 'last_line': 'line3'}
        
    Keywords: parse, split, lines, format, structured, output
    """
    if not output:
        return {"lines": [], "count": 0, "first_line": "", "last_line": ""}
    
    lines = output.strip().split("\n")
    return {
        "lines": lines,
        "count": len(lines),
        "first_line": lines[0] if lines else "",
        "last_line": lines[-1] if lines else "",
    }


def get_system_info() -> Dict[str, str]:
    """
    Get basic system information using shell commands.
    
    Use this tool to inspect OS details, CPU info, memory usage, and disk space.
    Useful for diagnostics, monitoring, and system inspection.
    
    Returns:
        Dictionary with system information keys:
            - 'os_info': OS and kernel details
            - 'cpu_info': CPU architecture and model
            - 'memory_info': Memory usage summary
            - 'disk_usage': Filesystem disk space usage
            
    Example:
        >>> get_system_info()
        {'os_info': 'Linux hostname 5.15...', 'cpu_info': 'Architecture: x86_64...', ...}
        
    Keywords: system, info, os, cpu, memory, disk, diagnostics, monitor
    """
    info = {}
    
    # Get OS information
    result = execute_shell_command("uname -a")
    if result["success"]:
        info["os_info"] = result["stdout"]
    
    # Get CPU info
    result = execute_shell_command("lscpu | head -n 10")
    if result["success"]:
        info["cpu_info"] = result["stdout"]
    
    # Get memory info
    result = execute_shell_command("free -h")
    if result["success"]:
        info["memory_info"] = result["stdout"]
    
    # Get disk usage
    result = execute_shell_command("df -h")
    if result["success"]:
        info["disk_usage"] = result["stdout"]
    
    return info


def check_file_permissions(filepath: str) -> Dict[str, Any]:
    """
    Check file permissions using shell commands.
    
    Use this tool to inspect file ownership, permissions, and access rights.
    
    Args:
        filepath (str): Path to the file
        
    Returns:
        Dictionary with permission information:
            - 'permissions': Permission string (e.g., '-rw-r--r--')
            - 'owner': File owner username
            - 'group': File group name
            - 'success': Whether the check was successful
            
    Example:
        >>> check_file_permissions("/etc/passwd")
        {'permissions': '-rw-r--r--', 'owner': 'root', 'group': 'root', 'success': True}
        
    Keywords: permissions, owner, group, access, rights, chmod, ls
    """
    result = execute_shell_command(f'ls -l "{filepath}"')
    
    if result["success"]:
        output_lines = result["stdout"].split("\n")
        if output_lines:
            parts = output_lines[0].split()
            permissions = parts[0] if len(parts) > 0 else ""
            owner = parts[2] if len(parts) > 2 else ""
            group = parts[3] if len(parts) > 3 else ""
            
            return {
                "permissions": permissions,
                "owner": owner,
                "group": group,
                "success": True,
            }
    
    return {
        "permissions": "",
        "owner": "",
        "group": "",
        "success": False,
        "error": result.get("stderr", "Unknown error"),
    }


def run_command_with_env(command: str, env_vars: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute a shell command with custom environment variables.
    
    Use this tool for running commands with specific environment configurations,
    testing environment-dependent behavior, or setting up isolated execution contexts.
    
    Args:
        command (str): The shell command to execute
        env_vars (Dict[str, str]): Dictionary of environment variables
        
    Returns:
        Dictionary with command execution results
        
    Example:
        >>> run_command_with_env("echo $MY_VAR", {"MY_VAR": "hello"})
        {'stdout': 'hello', 'stderr': '', 'returncode': 0, 'success': True}
        
    Keywords: environment, env, variables, custom, isolated, context
    """
    try:
        env = os.environ.copy()
        env.update(env_vars)
        
        logger.info(f"Executing command with custom env: {command}")
        
        result = subprocess.run(
            command,
            shell=True,
            env=env,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        response = {
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
        
        return response
        
    except Exception as e:
        error_msg = f"Error executing command with custom env: {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
        }


def get_all_tools() -> list[FunctionTool]:
    """
    Return all Linux tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Linux FunctionTool objects
    """
    return [
        FunctionTool.from_defaults(
            fn=execute_shell_command,
            description="Execute a shell command. Use for running any terminal command with timeout and working directory support. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=execute_multiple_commands,
            description="Execute multiple shell commands sequentially. Use for batch operations and command pipelines. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=parse_command_output,
            description="Parse command output into structured format. Use for splitting output into lines and extracting metadata. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=get_system_info,
            description="Get system information including OS, CPU, memory, and disk. Use for diagnostics and monitoring. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=check_file_permissions,
            description="Check file permissions, owner, and group. Use for inspecting file access rights. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=run_command_with_env,
            description="Execute command with custom environment variables. Use for isolated execution contexts. Category: System",
        ),
    ]