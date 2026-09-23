"""
Windows PowerShell Toolkit - PowerShell command execution and system inspection.

This module provides functionality to execute PowerShell commands on Windows systems,
parse outputs, check file permissions, and gather system information.

Category: System
Retriever Keywords: shell, command, windows, powershell, execute, system, permissions, environment

Prerequisites:
    - Windows operating system
    - PowerShell 5.1+ (Windows PowerShell) or PowerShell Core 7+ (pwsh)
    - Appropriate execution policy and permissions
"""
import subprocess
import os
import logging
from typing import Dict, List, Optional, Any
from llama_index.core.tools import FunctionTool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_powershell_command() -> str:
    """
    Determine which PowerShell executable to use.
    
    Tries pwsh (PowerShell Core) first, falls back to powershell.exe (Windows PowerShell).
    
    Returns:
        str: Path to PowerShell executable
    """
    # Try PowerShell Core first
    try:
        result = subprocess.run(
            ["where", "pwsh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "pwsh"
    except Exception:
        pass
    
    # Fall back to Windows PowerShell
    return "powershell.exe"


def execute_shell_command(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    shell: bool = True,
) -> Dict[str, Any]:
    """
    Execute a PowerShell command and return structured response with stdout, stderr, and return code.
    
    Use this tool for running any PowerShell command, scripting, or system operations on Windows.
    Supports timeouts, custom working directories, and non-shell execution.
    
    Args:
        command (str): The PowerShell command to execute
        timeout (int): Timeout in seconds for the command execution (default: 30)
        cwd (str, optional): Working directory for the command
        shell (bool): Whether to use shell (default: True)
        
    Returns:
        Dict containing 'stdout', 'stderr', 'returncode', and 'success' keys
        
    Example:
        >>> execute_shell_command("Get-Process | Select-Object -First 5")
        {'stdout': 'NPM(K)    PM(M)...', 'stderr': '', 'returncode': 0, 'success': True}
        
        >>> execute_shell_command("Get-Item /nonexistent")
        {'stdout': '', 'stderr': 'Get-Item: Cannot find path...', 'returncode': 1, 'success': False}
        
    Keywords: execute, run, shell, command, terminal, powershell, stdout, stderr
    """
    try:
        logger.info(f"Executing PowerShell command: {command}")
        
        # Use PowerShell for execution
        ps_command = _get_powershell_command()
        full_command = f'{ps_command} -NoProfile -NonInteractive -Command "{command}"'
        
        result = subprocess.run(
            full_command,
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
    Execute multiple PowerShell commands sequentially and return results for each.
    
    Use this tool for running a series of commands, batch operations, or pipelines.
    Commands are executed one after another, not in parallel.
    
    Args:
        commands (List[str]): List of PowerShell commands to execute
        timeout (int): Timeout in seconds for each command execution
        
    Returns:
        List of response dictionaries for each command
        
    Example:
        >>> execute_multiple_commands(["whoami", "Get-Location", "Get-Date"])
        [{'stdout': 'user', ...}, {'stdout': 'C:\\Users\\user', ...}, ...]
        
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
    Get basic system information using PowerShell commands.
    
    Use this tool to inspect OS details, CPU info, memory usage, and disk space.
    Useful for diagnostics, monitoring, and system inspection.
    
    Returns:
        Dictionary with system information keys:
            - 'os_info': OS and version details
            - 'cpu_info': CPU architecture and model
            - 'memory_info': Memory usage summary
            - 'disk_usage': Filesystem disk space usage
            
    Example:
        >>> get_system_info()
        {'os_info': 'Microsoft Windows 11...', 'cpu_info': 'Intel64 Family...', ...}
        
    Keywords: system, info, os, cpu, memory, disk, diagnostics, monitor
    """
    info = {}
    
    # Get OS information
    result = execute_shell_command(
        "Get-ComputerInfo | Select-Object WindowsProductName, OsVersion, OsBuildNumber | Format-List"
    )
    if result["success"]:
        info["os_info"] = result["stdout"]
    
    # Get CPU info
    result = execute_shell_command(
        "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | Format-List"
    )
    if result["success"]:
        info["cpu_info"] = result["stdout"]
    
    # Get memory info
    result = execute_shell_command(
        "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory, @{Name='TotalGB';Expression={[math]::Round($_.TotalVisibleMemorySize/1MB,2)}}, @{Name='FreeGB';Expression={[math]::Round($_.FreePhysicalMemory/1MB,2)}} | Format-List"
    )
    if result["success"]:
        info["memory_info"] = result["stdout"]
    
    # Get disk usage
    result = execute_shell_command(
        "Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{Name='UsedGB';Expression={[math]::Round(($_.Used/1GB),2)}}, @{Name='FreeGB';Expression={[math]::Round(($_.Free/1GB),2)}} | Format-Table -AutoSize"
    )
    if result["success"]:
        info["disk_usage"] = result["stdout"]
    
    return info


def check_file_permissions(filepath: str) -> Dict[str, Any]:
    """
    Check file permissions using PowerShell commands.
    
    Use this tool to inspect file ownership, permissions, and access rights.
    
    Args:
        filepath (str): Path to the file
        
    Returns:
        Dictionary with permission information:
            - 'owner': File owner username
            - 'access': Access control rules
            - 'success': Whether the check was successful
            
    Example:
        >>> check_file_permissions("C:\\Windows\\System32\\config")
        {'owner': 'NT AUTHORITY\\SYSTEM', 'access': [...], 'success': True}
        
    Keywords: permissions, owner, access, rights, acl, get-acl
    """
    result = execute_shell_command(
        f"Get-Acl '{filepath}' | Select-Object Owner, Access | ConvertTo-Json"
    )
    
    if result["success"]:
        try:
            import json
            data = json.loads(result["stdout"])
            
            return {
                "owner": data.get("Owner", ""),
                "access": data.get("Access", []),
                "success": True,
            }
        except json.JSONDecodeError:
            return {
                "owner": "",
                "access": [],
                "success": False,
                "error": "Failed to parse JSON output",
                "raw_output": result["stdout"],
            }
    
    return {
        "owner": "",
        "access": [],
        "success": False,
        "error": result.get("stderr", "Unknown error"),
    }


def run_command_with_env(command: str, env_vars: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute a PowerShell command with custom environment variables.
    
    Use this tool for running commands with specific environment configurations,
    testing environment-dependent behavior, or setting up isolated execution contexts.
    
    Args:
        command (str): The PowerShell command to execute
        env_vars (Dict[str, str]): Dictionary of environment variables
        
    Returns:
        Dictionary with command execution results
        
    Example:
        >>> run_command_with_env("echo $env:MY_VAR", {"MY_VAR": "hello"})
        {'stdout': 'hello', 'stderr': '', 'returncode': 0, 'success': True}
        
    Keywords: environment, env, variables, custom, isolated, context
    """
    try:
        logger.info(f"Executing command with custom env: {command}")
        
        # Build environment variable assignments
        env_assignments = []
        for key, value in env_vars.items():
            # Escape quotes in values
            escaped_value = value.replace('"', '`"')
            env_assignments.append(f'$env:{key}="{escaped_value}"')
        
        # Combine with the main command
        full_command = "; ".join(env_assignments) + "; " + command
        
        ps_command = _get_powershell_command()
        full_ps_command = f'{ps_command} -NoProfile -NonInteractive -Command "{full_command}"'
        
        result = subprocess.run(
            full_ps_command,
            shell=True,
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
    Return all Windows PowerShell tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Windows PowerShell FunctionTool objects
    """
    logger.info("get_all_tools called for windows tools")
    return [
        FunctionTool.from_defaults(
            fn=execute_shell_command,
            description="Execute a PowerShell command. Use for running any terminal command with timeout and working directory support. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=execute_multiple_commands,
            description="Execute multiple PowerShell commands sequentially. Use for batch operations and command pipelines. Category: System",
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
            description="Check file permissions, owner, and access rules. Use for inspecting file access rights. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=run_command_with_env,
            description="Execute command with custom environment variables. Use for isolated execution contexts. Category: System",
        ),
    ]
