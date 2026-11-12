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
import signal
import time
from typing import Dict, List, Optional, Any

# The privilege half of the toolkit: it decides what happens when a
# command asks for root.  It is a separate module, because it is a
# subject of its own - and because it carries no operation.
from .privilege import plan_privilege, preserved_terminal, privilege_status

# Logging is configured centrally in agent-torvalds.py.
# Do NOT call logging.basicConfig() here — it is a no-op after the first call.
logger = logging.getLogger(__name__)


#: The seconds a command that outlived its timeout is given to end by
#: itself, before it is killed outright.
KILL_GRACE = 2.0

#: The seconds between two checks of whether a killed command is gone.
KILL_POLL = 0.05


def _is_zombie(pid: int) -> bool:
    """Whether a process has ended and only waits to be reaped.

    A zombie holds nothing: it cannot answer a signal, it cannot read
    the terminal, and it cannot keep a command alive.  It only waits for
    the process that has to reap it.

    Args:
        pid: The pid of the process.

    Returns:
        ``True`` when the process is a zombie.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            stat = handle.read()
    except OSError:
        return False

    # The command name is in brackets and may hold spaces, so the
    # fields after it are found from the last bracket.  The first of
    # them is the state of the process.
    fields = stat[stat.rfind(")") + 2:].split()
    return bool(fields) and fields[0] == "Z"


def _alive(pid: int) -> bool:
    """Whether a process is still running.

    Args:
        pid: The pid of the process.

    Returns:
        ``True`` when the process is running.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It is there; it belongs to somebody else.
        return True
    except OSError:
        return False

    return not _is_zombie(pid)


def _descendants(pid: int) -> List[int]:
    """The processes below *pid* - what the command started.

    The process that holds the terminal is not the process that is
    started: the shell is the child, and the program behind the shell -
    the ``sudo`` that asks for the password on the terminal - is its
    grandchild.  The tree is read from ``/proc``, so it is the tree as
    it is right now.

    Args:
        pid: The pid of the process.

    Returns:
        The pids of the processes below *pid*.
    """
    children: Dict[int, List[int]] = {}

    try:
        entries = os.listdir("/proc")
    except OSError:  # pragma: no cover - /proc is always there on Linux
        return []

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8",
                      errors="replace") as handle:
                stat = handle.read()
        except OSError:
            continue

        fields = stat[stat.rfind(")") + 2:].split()
        if len(fields) < 2:
            continue
        try:
            parent = int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(int(entry))

    found: List[int] = []
    pending = list(children.get(pid, []))
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.append(current)
        pending.extend(children.get(current, []))

    return found


def _kill_tree(pid: int, grace: float = KILL_GRACE) -> List[int]:
    """End a command that outlived its timeout, and everything it started.

    The timeout of a command used to kill the shell and nothing else:
    the program behind the shell - the ``sudo`` that asks for the
    password on the terminal - survived the timeout and kept the
    terminal with the echo off.

    The tree is ended the way a program is meant to be ended: a
    ``SIGTERM`` first, so a child that can catch it gives the terminal
    back itself, and a ``SIGKILL`` after the grace period, for a child
    that does not care.

    Args:
        pid: The pid of the process to end.
        grace: The seconds the tree is given to end by itself.

    Returns:
        The pids that had to be killed outright.
    """
    descendants = _descendants(pid)
    tree = descendants + [pid]

    # The children first: the shell is ended last, so it cannot start
    # anything new while the tree is being ended.
    for target in tree:
        try:
            os.kill(target, signal.SIGTERM)
        except OSError:
            continue

    # The grace period covers the **whole** tree, and not only the
    # children of the shell: the shell itself is a process that can
    # catch a SIGTERM, and a child that is given no time to react is a
    # child that is killed instead of being asked.
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not any(_alive(target) for target in tree):
            break
        time.sleep(KILL_POLL)

    survivors = [target for target in tree if _alive(target)]
    for target in survivors:
        try:
            os.kill(target, signal.SIGKILL)
        except OSError:
            continue

    return survivors


def _run_command(
    command: str,
    timeout: int,
    shell: bool = True,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    stdin: Optional[Any] = None,
) -> subprocess.CompletedProcess:
    """Run a command, and end it with everything it started on a timeout.

    ``subprocess.run(timeout=...)`` kills the **shell** it started and
    nothing else, so the program behind the shell outlives the timeout
    of the command.  The timeout here ends the whole tree.

    Args:
        command: The command line.
        timeout: The seconds the command is given.
        shell: Whether the command is run through a shell.
        cwd: The working directory of the command.
        env: The environment of the command.
        stdin: The standard input of the command.

    Returns:
        The completed process: its output and its return code.

    Raises:
        subprocess.TimeoutExpired: when the command outlived its timeout.
    """
    process = subprocess.Popen(
        command,
        shell=shell,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        survivors = _kill_tree(process.pid)
        if survivors:
            logger.warning(
                "the command did not end by itself; %d process(es) were killed",
                len(survivors),
            )
        # The output the command produced before it was ended.
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            command, timeout, output=stdout, stderr=stderr
        )

    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _stdin_for(plan) -> Optional[Any]:
    """The standard input of the child of a command.

    An **escalated** command gets nothing to read.  The child of a
    privilege escalation runs as another user, and it must not be able
    to take the terminal of the operator over: it cannot read the
    keystrokes the operator types, and it cannot ask a question that
    the operator cannot answer.

    An ordinary command keeps the terminal, as it always did.

    Args:
        plan: The plan of the command.

    Returns:
        ``subprocess.DEVNULL`` for an escalated command, and ``None``
        (the terminal is inherited) for an ordinary one.
    """
    if getattr(plan, "escalated", False):
        return subprocess.DEVNULL
    return None


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
    backend = "none"

    try:
        plan = plan_privilege(command, privilege, timeout=timeout)
        backend = plan.backend

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

        # The terminal is given back exactly as it was found, whatever
        # the command did to it - and whether the timeout killed it
        # while it held the echo off.
        with preserved_terminal():
            result = _run_command(
                effective_command,
                timeout=effective_timeout,
                shell=shell,
                cwd=cwd,
                stdin=_stdin_for(plan),
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
            "privilege": backend,
        }
    except Exception as e:
        error_msg = f"Error executing command '{command}': {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "returncode": -1,
            "success": False,
            "privilege": backend,
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
    backend = "none"

    try:
        plan = plan_privilege(command, privilege)
        backend = plan.backend

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

        with preserved_terminal():
            result = _run_command(
                effective_command,
                timeout=effective_timeout,
                shell=True,
                env=env,
                stdin=_stdin_for(plan),
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
            "privilege": backend,
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
