import os
import shutil
from pathlib import Path
import platform

def pwd():
    """
    Returns the current working directory as a string.
    """
    try:
        return os.getcwd()
    except Exception as e:
        return f"Error getting directory: {str(e)}"


def ls(path = '.'):
    """
    List files and directories in the specified path.
    """
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return f"Directory not found: {path}"
    except PermissionError:
        return f"Permission denied accessing: {path}"
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def touch(abs_path: str) -> str:
    """
    Creates an empty file at the given absolute path.
    If the file already exists, leave it unchanged.
    """
    try:
        path = Path(abs_path).expanduser().resolve()
        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            path.touch(exist_ok=False)

        return f"{path}"
    except Exception as e:
        return f"Error creating file: {e}"

def check_path_exists(abs_path: str) -> dict:
    """
    Check if the given absolute path exists and whether it is a file or directory.
    Works on Linux, Windows, and macOS.

    :param abs_path: Absolute path to check.
    :return: Dictionary with keys:
             - 'exists': True/False
             - 'is_file': True/False
             - 'is_dir': True/False
             - 'path': resolved absolute path string
    """
    try:
        path = Path(abs_path).expanduser().resolve()
        return {
            "exists": path.exists(),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "path": str(path)
        }
    except Exception as e:
        return {
            "exists": False,
            "is_file": False,
            "is_dir": False,
            "path": abs_path,
            "error": str(e)
        }

def mkdir(path: str):
    """
    Create a new directory.
    """
    try:
        os.makedirs(path, exist_ok=True)
        return f"Directory created: {path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"

def rm(path: str):
    """
    Remove a file or directory from the specified path.
    """
    print(f"Remove file or directory {path}")
    try:
        if os.path.isfile(path):
            os.remove(path)
            return f"File removed: {path}"
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"Directory removed: {path}"
        else:
            return f"Path not found: {path}"
    except Exception as e:
        return f"Error removing path: {str(e)}"

def cp(src: str, dst: str):
    """
    Copy file or directory from source to destination.
    """
    try:
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return f"File copied: {src} -> {dst}"
        elif os.path.isdir(src):
            shutil.copytree(src, dst)
            return f"Directory copied: {src} -> {dst}"
        else:
            return f"Source not found: {src}"
    except Exception as e:
        return f"Error copying path: {str(e)}"

def mv(src: str, dst: str):
    """
    Move/rename file or directory from source to destination.
    """
    try:
        shutil.move(src, dst)
        return f"Moved: {src} -> {dst}"
    except Exception as e:
        return f"Error moving path: {str(e)}"

def read_file(path: str):
    """
    Read and return the contents of a file.
    """
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str):
    """
    Write content to a file.
    """
    try:
        with open(path, 'w') as f:
            f.write(content)
        return f"File written: {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def get_system_info() -> dict:
    """
    Gather system information: OS, version, kernel, architecture, etc.
    This function is also useful to gather information about active user.
    Works on Linux, macOS, and Windows.

    :return: Dictionary with system details
    """
    print(f"Getting system info:")
    try:
        info = {
            "system": platform.system(),  # e.g. 'Linux', 'Windows', 'Darwin'
            "node": platform.node(),  # hostname
            "release": platform.release(),  # OS release
            "version": platform.version(),  # OS version
            "machine": platform.machine(),  # hardware type (e.g. 'x86_64')
            "processor": platform.processor(),  # CPU info
            "architecture": platform.architecture(),  # (bits, linkage)
            "platform": platform.platform(),  # full platform string
            "uname": platform.uname()._asdict(),  # detailed uname info
            "env_user": os.getenv("USER") or os.getenv("USERNAME")
        }
        return info
    except Exception as e:
        return {"error": str(e)}