"""
Linux Toolkit - the library half.

This module holds the **shell-execution and system-inspection
operations** of the Linux toolkit.  It is the reusable half of the
feature: it carries **no LlamaIndex import**, so it stays usable - and
testable - as a plain Python library by any application that has no
agent framework installed.

The LlamaIndex adapter is a submodule of the package
(:mod:`agent_linux_toolkit`); it is the one module of the toolkit that
knows about the agent framework, and it is imported on demand.

The operations are the ones that used to live in the single module
``agent_linux_toolkit.py`` at the project root.  They moved here
**verbatim**: same names, same signatures, same docstrings, same error
contract - a failure is reported as a message string, never raised.

Category: System
Retriever Keywords: shell, command, linux, execute, system, permissions, environment

Prerequisites:
    - Linux/Unix-like operating system
    - Appropriate shell access and permissions
    - ``pkexec`` and a running polkit agent (optional - for the window
      that asks the operator for a password; see :mod:`privilege`)
"""
import subprocess
import os
import logging
from typing import Dict, List, Optional, Any

# The privilege half of the toolkit: it decides what happens when a
# command asks for root.  It is a separate module, because it is a
# subject of its own - and because it carries no operation.
from .privilege import plan_privilege, privilege_status

# Logging is configured centrally in agent-torvalds.py.
# Do NOT call logging.basicConfig() here — it is a no-op after the first call.
logger = logging.getLogger(__name__)


def execute_shell_command(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    shell: bool = True,
    privilege: str = "auto",
) -> Dict[str, Any]:
    """
    Execute a shell command and return structured response with stdout, stderr, and return code.
    
    Use this tool for running any shell command, scripting, or system operations.
    Supports timeouts, custom working directories, and non-shell execution.

    A command that asks for root - a ``sudo`` in it - is **escalated
    through pkexec**: polkit puts the question in a window, and the
    operator types the password there.  The password never reaches the
    terminal the agent is drawing on.  See ``privilege`` below.

    Args:
        command (str): The shell command to execute
        timeout (int): Timeout in seconds for the command execution (default: 30)
        cwd (str, optional): Working directory for the command
        shell (bool): Whether to use shell (default: True)
        privilege (str): How a command that asks for root is run:
            'auto' (default) uses pkexec when it can show the window,
            'pkexec' insists on it, and 'sudo' runs the command exactly
            as it was written.

    Returns:
        Dict containing 'stdout', 'stderr', 'returncode', and 'success'
        keys, plus 'privilege' - what ran the command: 'none', 'pkexec'
        or 'sudo'.  A command that was escalated carries the notes of
        the escalation in 'privilege_notes'.

    Example:
        >>> execute_shell_command("ls -la")
        {'stdout': 'total 48\\n...', 'stderr': '', 'returncode': 0, 'success': True, 'privilege': 'none'}

        >>> execute_shell_command("ls /nonexistent")
        {'stdout': '', 'stderr': 'ls: cannot access...', 'returncode': 2, 'success': False, 'privilege': 'none'}

    Keywords: execute, run, shell, command, terminal, bash, stdout, stderr
    """
    effective_timeout = timeout

    try:
        plan = plan_privilege(command, privilege, timeout=timeout)

        if plan.error:
            logger.error(plan.error)
            return {
                "stdout": "",
                "stderr": plan.error,
                "returncode": -1,
                "success": False,
                "privilege": plan.backend,
            }

        for note in plan.notes:
            logger.info(note)

        effective_command = plan.command
        effective_timeout = plan.timeout if plan.timeout is not None else timeout

        logger.info(f"Executing command: {effective_command}")

        result = subprocess.run(
            effective_command,
            shell=shell,
            cwd=cwd,
            timeout=effective_timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        response = {
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
            "returncode": result.returncode,
            "success": result.returncode == 0,
            "privilege": plan.backend,
        }

        if plan.notes:
            response["privilege_notes"] = list(plan.notes)
        
        if response["success"]:
            logger.info(f"Command executed successfully. Return code: {response['returncode']}")
        else:
            logger.warning(f"Command failed with return code: {response['returncode']}")
            if response["stderr"]:
                logger.warning(f"Error output: {response['stderr']}")
        
        return response
        
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {effective_timeout} seconds: {command}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
            "privilege": "none",
        }
    except Exception as e:
        error_msg = f"Error executing command '{command}': {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
            "privilege": "none",
        }


def execute_multiple_commands(
    commands: List[str],
    timeout: int = 30,
    privilege: str = "auto",
) -> List[Dict[str, Any]]:
    """
    Execute multiple shell commands sequentially and return results for each.
    
    Use this tool for running a series of commands, batch operations, or pipelines.
    Commands are executed one after another, not in parallel.
    
    Args:
        commands (List[str]): List of shell commands to execute
        timeout (int): Timeout in seconds for each command execution
        privilege (str): How a command that asks for root is run:
            'auto' (default), 'pkexec' or 'sudo'.

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
        result = execute_shell_command(command, timeout, privilege=privilege)

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


def run_command_with_env(
    command: str,
    env_vars: Dict[str, str],
    privilege: str = "auto",
) -> Dict[str, Any]:
    """
    Execute a shell command with custom environment variables.
    
    Use this tool for running commands with specific environment configurations,
    testing environment-dependent behavior, or setting up isolated execution contexts.

    A command that asks for root is escalated through pkexec, exactly as in
    :func:`execute_shell_command`.

    Args:
        command (str): The shell command to execute
        env_vars (Dict[str, str]): Dictionary of environment variables
        privilege (str): How a command that asks for root is run:
            'auto' (default), 'pkexec' or 'sudo'.

    Returns:
        Dictionary with command execution results, including the 'privilege'
        key that says what ran the command.

    Example:
        >>> run_command_with_env("echo $MY_VAR", {"MY_VAR": "hello"})
        {'stdout': 'hello', 'stderr': '', 'returncode': 0, 'success': True, 'privilege': 'none'}

    Keywords: environment, env, variables, custom, isolated, context
    """
    try:
        plan = plan_privilege(command, privilege)

        if plan.error:
            logger.error(plan.error)
            return {
                "stdout": "",
                "stderr": plan.error,
                "returncode": -1,
                "success": False,
                "privilege": plan.backend,
            }

        for note in plan.notes:
            logger.info(note)

        env = os.environ.copy()
        env.update(env_vars)

        effective_command = plan.command
        effective_timeout = plan.timeout if plan.timeout is not None else 30

        logger.info(f"Executing command with custom env: {effective_command}")

        result = subprocess.run(
            effective_command,
            shell=True,
            env=env,
            timeout=effective_timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        response = {
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
            "returncode": result.returncode,
            "success": result.returncode == 0,
            "privilege": plan.backend,
        }

        if plan.notes:
            response["privilege_notes"] = list(plan.notes)
        
        return response
        
    except Exception as e:
        error_msg = f"Error executing command with custom env: {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
            "privilege": "none",
        }


def check_privilege_backend() -> Dict[str, Any]:
    """
    Report how a command that asks for root would be run on this machine.

    Use this tool before a command that needs root, or to tell the operator
    what to expect.  A command with a ``sudo`` in it is escalated through
    **pkexec**: polkit opens a window and asks the operator for the
    password there - the password never reaches the terminal the agent is
    drawing on.

    Returns:
        Dictionary with:
            - 'backend': 'pkexec' or 'sudo' - what would run the command
            - 'usable': whether the window can be shown
            - 'pkexec_path': the path of the pkexec program
            - 'gui_session': whether a graphical session is there
            - 'polkit_agent': the authentication agent that is running
            - 'terminal_managed': whether the terminal belongs to an
              application that draws the screen
            - 'reason': what is missing, when the window cannot be shown

    Example:
        >>> check_privilege_backend()
        {'backend': 'pkexec', 'usable': True, 'polkit_agent': 'gnome-shell', ...}

    Keywords: privilege, sudo, pkexec, polkit, root, password, window, dialog
    """
    status = privilege_status()
    status["success"] = True
    return status
