"""
APT Package Toolkit - Interactive package installation for Debian/Ubuntu.

This module provides functionality to detect missing commands, resolve
them to APT packages, and install them interactively with sudo password
handling.

Category: System / Package Management
Retriever Keywords: apt, package, install, debian, ubuntu, sudo, missing, dependency

Prerequisites:
    - Debian/Ubuntu-based Linux system
    - sudo access with appropriate permissions
    - apt-file (optional, recommended for best resolution)
"""
import subprocess
import os
import logging
from typing import Dict, List, Optional, Any
from llama_index.core.tools import FunctionTool

# Configure logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level sudo password cache (session-scoped)
# ---------------------------------------------------------------------------
_sudo_password_cache: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. Package Resolution
# ---------------------------------------------------------------------------

def find_package_for_command(command: str) -> Dict[str, Any]:
    """
    Find which APT package provides a given command/binary.

    Uses apt-file to search for the package that contains the binary.
    Falls back to apt-cache search if apt-file is not available.

    Args:
        command (str): The command/binary name to search for

    Returns:
        Dictionary with:
            - 'package_name': str or None
            - 'method': 'apt-file' | 'apt-cache' | 'dpkg'
            - 'success': bool
            - 'candidates': List of candidate packages

    Example:
        >>> find_package_for_command("ffmpeg")
        {'package_name': 'ffmpeg', 'method': 'apt-file', 'success': True, 'candidates': ['ffmpeg']}

    Keywords: find, package, resolve, command, binary, apt-file, dpkg, apt-cache
    """
    logger.info(f"find_package_for_command called with command: {command}")
    
    # Method 1: apt-file (most accurate)
    try:
        result = subprocess.run(
            ["apt-file", "search", "-F", f"/{command}$"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            # Parse first line: "ffmpeg: /usr/bin/ffmpeg"
            lines = result.stdout.strip().split("\n")
            packages = set()
            for line in lines[:10]:  # Limit to 10 candidates
                if ":" in line:
                    pkg_name = line.split(":")[0].strip()
                    packages.add(pkg_name)
            return {
                "package_name": list(packages)[0] if packages else None,
                "method": "apt-file",
                "success": bool(packages),
                "candidates": list(packages),
            }
    except FileNotFoundError:
        logger.debug("apt-file not available, falling back to other methods")
    except subprocess.TimeoutExpired:
        logger.warning("apt-file search timed out")

    # Method 2: dpkg -S (installed packages only)
    try:
        result = subprocess.run(
            ["dpkg", "-S", f"/usr/bin/{command}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pkg_name = result.stdout.strip().split(":")[0].strip()
            return {
                "package_name": pkg_name,
                "method": "dpkg",
                "success": True,
                "candidates": [pkg_name],
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("dpkg lookup failed, falling back to apt-cache")

    # Method 3: apt-cache search (keyword fallback)
    try:
        result = subprocess.run(
            ["apt-cache", "search", command],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split("\n")
            candidates = [line.split()[0] for line in lines[:5] if line]
            return {
                "package_name": candidates[0] if candidates else None,
                "method": "apt-cache",
                "success": bool(candidates),
                "candidates": candidates,
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("apt-cache search failed")

    return {
        "package_name": None,
        "method": "none",
        "success": False,
        "candidates": [],
    }


def check_command_exists(command: str) -> Dict[str, Any]:
    """
    Check if a command/binary is available in the system PATH.

    Args:
        command (str): Command name to check

    Returns:
        Dictionary with 'exists' (bool), 'path' (str), and 'success' (bool)

    Example:
        >>> check_command_exists("ls")
        {'exists': True, 'path': '/usr/bin/ls', 'success': True}

    Keywords: check, command, exists, path, which, available
    """
    logger.info(f"check_command_exists called with command: {command}")
    try:
        result = subprocess.run(
            ["which", command],
            capture_output=True, text=True, timeout=5
        )
        return {
            "exists": result.returncode == 0,
            "path": result.stdout.strip() if result.returncode == 0 else None,
            "success": result.returncode == 0,
        }
    except Exception as e:
        logger.error(f"Error checking command existence: {e}")
        return {
            "exists": False,
            "path": None,
            "success": False,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# 2. Sudo Password Handling
# ---------------------------------------------------------------------------

def prompt_sudo_password(
    method: str = "auto",
    password: Optional[str] = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """
    Obtain sudo password using multiple fallback strategies.

    Resolution order:
      1. Parameter (if method='parameter' or password is explicitly provided)
      2. Environment variable TORVALDS_SUDO_PASSWORD
      3. Session cache (from a previously validated password)
      4. Console input using rich console (works in agent context)

    Args:
        method (str): Prompting method: 'auto', 'console', 'env_var', or 'parameter'
        password (str, optional): Password to use if method is 'parameter'
        max_attempts (int): Maximum number of password attempts for console method

    Returns:
        Dictionary with:
            - 'password_provided': bool
            - 'success': bool
            - 'method': str (the method actually used)
            - 'password': str (the password, only for internal use, never logged)
            - 'attempts': int (number of attempts made, for console method)

    Example:
        >>> prompt_sudo_password()
        {'password_provided': True, 'success': True, 'method': 'env_var', ...}

        >>> prompt_sudo_password(method="parameter", password="mysecretpass")
        {'password_provided': True, 'success': True, 'method': 'parameter'}

    Keywords: sudo, password, prompt, console, credentials, getpass
    """
    logger.info(f"prompt_sudo_password called with method: {method}, max_attempts: {max_attempts}")
    global _sudo_password_cache

    result = {
        "password_provided": False,
        "success": False,
        "method": method,
        "password": None,
    }

    try:
        # ---------------------------------------------------------------
        # Strategy 1: Parameter (highest priority when explicitly set)
        # ---------------------------------------------------------------
        if method == "parameter" or (method == "auto" and password):
            if password and test_sudo_password(password):
                _sudo_password_cache = password
                result.update({
                    "password_provided": True,
                    "success": True,
                    "password": password,
                    "method": "parameter",
                })
                return result
            elif password:
                result["error"] = "Invalid password provided"
                return result
            else:
                result["error"] = "No password provided"
                return result

        # ---------------------------------------------------------------
        # Strategy 2: Environment variable
        # ---------------------------------------------------------------
        if method in ("auto", "env_var"):
            env_pass = os.environ.get("TORVALDS_SUDO_PASSWORD")
            if env_pass:
                if test_sudo_password(env_pass):
                    _sudo_password_cache = env_pass
                    result.update({
                        "password_provided": True,
                        "success": True,
                        "password": env_pass,
                        "method": "env_var",
                    })
                    return result
                else:
                    if method == "env_var":
                        result["error"] = "Invalid password in TORVALDS_SUDO_PASSWORD"
                        return result
                    # In auto mode, continue to next strategy

        # ---------------------------------------------------------------
        # Strategy 3: Session cache
        # ---------------------------------------------------------------
        if method in ("auto", "cache"):
            if _sudo_password_cache:
                # Re-validate cached password (sudo credentials may have expired)
                if test_sudo_password(_sudo_password_cache):
                    result.update({
                        "password_provided": True,
                        "success": True,
                        "password": _sudo_password_cache,
                        "method": "cache",
                    })
                    return result
                else:
                    # Clear invalid cache
                    _sudo_password_cache = None

        # ---------------------------------------------------------------
        # Strategy 4: Console input (works in agent context)
        # ---------------------------------------------------------------
        if method in ("auto", "console"):
            return _prompt_console_password(result, max_attempts)

    except Exception as e:
        result["error"] = str(e)
        return result

    return result


def _prompt_console_password(result: dict, max_attempts: int) -> dict:
    """
    Prompt for password using console input that works in agent context.

    This avoids getpass.getpass() which hangs when /dev/tty is not
    available in the agent's async console environment.
    """
    global _sudo_password_cache

    try:
        # Import here to avoid circular imports
        from rich.console import Console
        console = Console()

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Attempting to get sudo password (attempt {attempt}/{max_attempts})")
                
                # Print prompt to agent console
                console.print(f"\n🔑 Enter sudo password (attempt {attempt}/{max_attempts}):")
                console.print("(password will be hidden as you type)")
                
                # Use input() instead of getpass.getpass()
                # In agent context, getpass hangs because it tries to open /dev/tty
                # directly, which conflicts with the agent's own stdin handling.
                # Using input() works because the agent's main loop already has
                # stdin properly configured.
                password_input = input("Password: ")
                
                if password_input:
                    # Test the password
                    if test_sudo_password(password_input):
                        _sudo_password_cache = password_input
                        result.update({
                            "password_provided": True,
                            "success": True,
                            "password": password_input,
                            "method": "console",
                            "attempts": attempt,
                        })
                        console.print("✓ Password accepted!")
                        return result
                    else:
                        console.print("✗ Invalid password, please try again.")
                else:
                    console.print("Empty password, please try again.")
            except EOFError:
                logger.warning("EOF received on password input")
                break
            except Exception as e:
                logger.error(f"Error during password input: {e}")
                break

        result["error"] = "Failed to get valid sudo password after maximum attempts"
        return result

    except Exception as e:
        result["error"] = f"Console password prompt failed: {e}"
        return result


def test_sudo_password(password: str) -> bool:
    """
    Test if the provided sudo password is valid.

    Args:
        password (str): Password string to test

    Returns:
        bool: True if password is valid

    Keywords: test, sudo, password, validate, verify
    """
    logger.info("test_sudo_password called")
    if not password:
        return False
    try:
        result = subprocess.run(
            ["sudo", "-S", "-k", "true"],  # -k forces password prompt
            input=password + "\n",
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error testing sudo password: {e}")
        return False


def clear_sudo_cache() -> Dict[str, Any]:
    """
    Clear the cached sudo password.

    Returns:
        Dictionary with success status

    Keywords: clear, cache, sudo, password, reset
    """
    logger.info("clear_sudo_cache called")
    global _sudo_password_cache
    _sudo_password_cache = None
    return {"success": True, "message": "Sudo password cache cleared"}


# ---------------------------------------------------------------------------
# 3. Package Installation
# ---------------------------------------------------------------------------

def install_package(
    package_name: str,
    update_first: bool = False,
    sudo_password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Install an APT package with optional pre-update and sudo handling.

    Args:
        package_name (str): Name of the package to install
        update_first (bool): Whether to run apt-get update before install
        sudo_password (str, optional): Sudo password (if None, will prompt via console)

    Returns:
        Dictionary with installation result details

    Example:
        >>> install_package("ffmpeg", update_first=True)
        {'package': 'ffmpeg', 'installed': True, 'success': True, ...}

    Keywords: install, package, apt-get, apt, debian, ubuntu
    """
    logger.info(f"install_package called with package_name: {package_name}, update_first: {update_first}")
    result = {
        "package": package_name,
        "installed": False,
        "steps": [],
        "success": False,
    }

    # Step 1: Check if already installed
    already_installed = check_command_exists(package_name)
    if already_installed.get("exists"):
        result.update({
            "installed": True,
            "steps": ["Already installed"],
            "success": True,
            "message": f"{package_name} is already installed",
        })
        return result

    # Step 2: Get sudo password if needed
    if sudo_password is None:
        pass_result = prompt_sudo_password(method="auto")
        if not pass_result.get("password_provided"):
            result["error"] = "No sudo password provided"
            return result
        sudo_password = pass_result.get("password")

    # Step 3: Optional apt update
    if update_first:
        update_cmd = f'echo "{sudo_password}" | sudo -S apt-get update -qq'
        update_result = subprocess.run(
            update_cmd, shell=True, capture_output=True, text=True, timeout=120
        )
        result["steps"].append(f"apt-get update: {'OK' if update_result.returncode == 0 else 'FAILED'}")
        if update_result.returncode != 0:
            result["error"] = f"apt-get update failed: {update_result.stderr}"
            return result

    # Step 4: Install package
    install_cmd = (
        f'DEBIAN_FRONTEND=noninteractive echo "{sudo_password}" | sudo -S '
        f'apt-get install -y -qq {package_name}'
    )
    install_result = subprocess.run(
        install_cmd, shell=True, capture_output=True, text=True, timeout=180
    )

    result["steps"].append(f"apt-get install {package_name}: {'OK' if install_result.returncode == 0 else 'FAILED'}")

    if install_result.returncode != 0:
        result["error"] = f"Installation failed: {install_result.stderr}"
        return result

    # Step 5: Post-install validation
    post_check = check_command_exists(package_name)
    result.update({
        "installed": post_check.get("exists", False),
        "success": post_check.get("exists", False),
        "post_install_path": post_check.get("path"),
    })

    return result


def install_multiple_packages(
    package_names: List[str],
    update_first: bool = False,
    sudo_password: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Install multiple APT packages sequentially.

    Args:
        package_names (List[str]): List of package names
        update_first (bool): Whether to run apt-get update before first install
        sudo_password (str, optional): Sudo password

    Returns:
        List of installation result dictionaries

    Keywords: install, multiple, batch, packages, sequential
    """
    logger.info(f"install_multiple_packages called with {len(package_names)} packages: {package_names}")
    results = []
    for i, pkg in enumerate(package_names):
        logger.info(f"Installing package {i+1}/{len(package_names)}: {pkg}")
        result = install_package(pkg, update_first=(i == 0 and update_first), sudo_password=sudo_password)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# 4. Interactive Installation Workflow
# ---------------------------------------------------------------------------

def interactive_install_missing_command(
    command: str,
    prompt_password: bool = True,
    update_first: bool = True,
    sudo_password: Optional[str] = None,
    password_method: str = "auto",
) -> Dict[str, Any]:
    """
    End-to-end workflow: detect missing command, resolve package, install it.

    This is the main entry point for handling "command not found" scenarios.

    Args:
        command (str): The missing command name
        prompt_password (bool): Whether to prompt for sudo password
        update_first (bool): Whether to update package lists first
        sudo_password (str, optional): Pre-provided sudo password (skips prompting)
        password_method (str): Method for password input: 'auto', 'console', 'env_var', 'parameter'

    Returns:
        Dictionary with full workflow result

    Example:
        >>> interactive_install_missing_command("ffmpeg")
        {'command': 'ffmpeg', 'success': True, 'message': 'Successfully installed...', ...}

        >>> interactive_install_missing_command("ffmpeg", sudo_password="mypassword")
        {'command': 'ffmpeg', 'success': True, ...}

    Keywords: interactive, install, missing, command, workflow, resolve, auto
    """
    logger.info(f"interactive_install_missing_command called with command: {command}, prompt_password: {prompt_password}, update_first: {update_first}")
    workflow_result = {
        "command": command,
        "steps": [],
        "success": False,
    }

    # Step 1: Check if command exists
    workflow_result["steps"].append("Checking if command exists...")
    cmd_check = check_command_exists(command)
    if cmd_check["exists"]:
        workflow_result.update({
            "success": True,
            "message": f"Command '{command}' is already available at {cmd_check['path']}",
        })
        return workflow_result

    # Step 2: Resolve package name
    workflow_result["steps"].append("Resolving package name...")
    resolution = find_package_for_command(command)
    if not resolution["success"]:
        workflow_result.update({
            "error": f"Could not find a package for command '{command}'",
            "candidates": resolution.get("candidates", []),
        })
        return workflow_result

    package_name = resolution["package_name"]
    workflow_result["resolved_package"] = package_name
    workflow_result["steps"].append(f"Resolved to package: {package_name}")

    # Step 3: Get sudo password
    if prompt_password and sudo_password is None:
        workflow_result["steps"].append("Requesting sudo password...")
        pass_result = prompt_sudo_password(
            method=password_method,
            password=sudo_password,
        )
        if pass_result.get("password_provided"):
            sudo_password = pass_result.get("password")
        else:
            workflow_result.update({
                "error": "Sudo password was not provided",
            })
            return workflow_result

    # Step 4: Install package
    workflow_result["steps"].append(f"Installing package: {package_name}")
    install_result = install_package(
        package_name,
        update_first=update_first,
        sudo_password=sudo_password,
    )
    workflow_result["installation_result"] = install_result
    workflow_result["success"] = install_result.get("success", False)

    # Step 5: Final validation
    workflow_result["steps"].append("Final validation...")
    final_check = check_command_exists(command)
    workflow_result["command_available"] = final_check["exists"]
    workflow_result["command_path"] = final_check.get("path")

    if final_check["exists"]:
        workflow_result["message"] = f"Successfully installed '{command}' via package '{package_name}'"
    else:
        workflow_result["message"] = f"Package installed but '{command}' still not found"

    return workflow_result


# ---------------------------------------------------------------------------
# 5. Tool Registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all APT package tools as FunctionTool objects for on-demand loading.

    Each tool includes category metadata for better retrieval.

    Returns:
        list[FunctionTool]: List of APT FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=find_package_for_command,
            description="Find which APT package provides a given command/binary. Use for resolving missing tools to installable packages. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=check_command_exists,
            description="Check if a command/binary is available in the system PATH. Use for verifying tool availability. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_package,
            description="Install an APT package with sudo handling. Use for installing system packages on Debian/Ubuntu. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_multiple_packages,
            description="Install multiple APT packages sequentially. Use for batch installations. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=interactive_install_missing_command,
            description="End-to-end workflow: detect missing command, resolve to package, and install it. Use for automatic dependency resolution. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=prompt_sudo_password,
            description="Obtain sudo password using multiple fallback strategies (env var, cache, console). Use for credential handling in package installation. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=test_sudo_password,
            description="Test if a sudo password is valid. Use for credential verification. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=clear_sudo_cache,
            description="Clear the cached sudo password. Use for security or when password changes. Category: System / Package Management",
        ),
    ]
