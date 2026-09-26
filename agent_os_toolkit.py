"""
OS/File Toolkit - File system operations and system information.

This module provides essential file and directory operations for interacting
with the operating system's file system safely and efficiently.

Category: Operating System / File Operations
Retriever Keywords: file, directory, path, copy, move, delete, create, read, write, system info
"""
import os
import shutil
import logging
from pathlib import Path
import platform
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


def pwd() -> str:
    """
    Get the current working directory.
    
    Use this tool to find out where you currently are in the file system.
    
    Returns:
        str: The absolute path of the current working directory
        
    Example:
        >>> pwd()
        '/home/user/projects'
        
    Keywords: current directory, working directory, location, path
    """
    logger.info("pwd called")
    try:
        cwd = os.getcwd()
        logger.info(f"cwd: {cwd}")
        return cwd
    except Exception as e:
        return f"Error getting directory: {str(e)}"


def ls(path: str = '.') -> list:
    """
    List files and directories in the specified path.
    
    Use this tool to see what files and folders exist in a directory.
    For more detailed information, consider using shell commands.
    
    Args:
        path (str): Directory path to list (default: current directory)
        
    Returns:
        list: List of file/directory names in the specified path
        
    Example:
        >>> ls('/home/user')
        ['documents', 'downloads', 'file.txt']
        >>> ls('.')
        ['file1.py', 'file2.py', 'README.md']
        
    Keywords: list, directory contents, files, folders, directory listing
    """
    logger.info(f"ls called with path: {path}")
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
    Create an empty file at the given absolute path.
    
    Use this tool to create new empty files or update timestamps of existing files.
    If the file already exists, it remains unchanged.
    
    Args:
        abs_path (str): Absolute path where the file should be created
        
    Returns:
        str: The absolute path of the created file
        
    Example:
        >>> touch('/home/user/newfile.txt')
        '/home/user/newfile.txt'
        
    Keywords: create file, new file, empty file, timestamp
    """
    logger.info(f"touch called with abs_path: {abs_path}")
    try:
        path = Path(abs_path).expanduser().resolve()
        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            path.touch(exist_ok=False)

        return str(path)
    except Exception as e:
        return f"Error creating file: {e}"


def check_path_exists(abs_path: str) -> dict:
    """
    Check if a file or directory exists at the given path.
    
    Use this tool to verify if a path exists before performing operations on it.
    Returns detailed information about the path type.
    
    Args:
        abs_path (str): Absolute path to check
        
    Returns:
        dict: Dictionary with keys:
            - 'exists': True/False
            - 'is_file': True/False
            - 'is_dir': True/False
            - 'path': resolved absolute path string
            
    Example:
        >>> check_path_exists('/home/user/file.txt')
        {'exists': True, 'is_file': True, 'is_dir': False, 'path': '/home/user/file.txt'}
        
    Keywords: exists, check path, file check, directory check, verify
    """
    logger.info(f"check_path_exists called with abs_path: {abs_path}")
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


def mkdir(path: str) -> str:
    """
    Create a new directory (and any missing parent directories).
    
    Use this tool to create new folders in the file system.
    Parent directories are created automatically if they don't exist.
    
    Args:
        path (str): Path of the directory to create
        
    Returns:
        str: Success message with the created path
        
    Example:
        >>> mkdir('/home/user/new_folder/subfolder')
        'Directory created: /home/user/new_folder/subfolder'
        
    Keywords: create directory, mkdir, folder, new folder, create path
    """
    logger.info(f"mkdir called with path: {path}")
    try:
        os.makedirs(path, exist_ok=True)
        return f"Directory created: {path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"


def rm(path: str) -> str:
    """
    Remove a file or directory from the specified path.
    
    ⚠️  DANGEROUS: This operation is destructive and cannot be undone.
    - For files: deletes the file
    - For directories: recursively deletes the directory and all contents
    
    Use with caution! Always verify the path before removing.
    
    Args:
        path (str): Path to the file or directory to remove
        
    Returns:
        str: Success message with the removed path
        
    Example:
        >>> rm('/home/user/old_file.txt')
        'File removed: /home/user/old_file.txt'
        >>> rm('/home/user/old_directory')
        'Directory removed: /home/user/old_directory'
        
    Keywords: delete, remove, delete file, delete directory, rm, destroy
    Safety: destructive, irreversible
    """
    logger.info(f"rm called with path: {path}")
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


def cp(src: str, dst: str) -> str:
    """
    Copy a file or directory from source to destination.
    
    Use this tool to duplicate files or directories.
    For files: copies the file content
    For directories: recursively copies the entire directory tree
    
    Args:
        src (str): Source path (file or directory)
        dst (str): Destination path
        
    Returns:
        str: Success message with the copy operation details
        
    Example:
        >>> cp('/home/user/file.txt', '/home/user/backup/file.txt')
        'File copied: /home/user/file.txt -> /home/user/backup/file.txt'
        
    Keywords: copy, duplicate, clone, backup, file copy, directory copy
    """
    logger.info(f"cp called with src: {src}, dst: {dst}")
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


def mv(src: str, dst: str) -> str:
    """
    Move or rename a file or directory from source to destination.
    
    Use this tool to relocate files/folders or rename them.
    The source will no longer exist at the original location after the move.
    
    Args:
        src (str): Source path (file or directory)
        dst (str): Destination path
        
    Returns:
        str: Success message with the move operation details
        
    Example:
        >>> mv('/home/user/old_name.txt', '/home/user/new_name.txt')
        'Moved: /home/user/old_name.txt -> /home/user/new_name.txt'
        
    Keywords: move, rename, relocate, move file, move directory, rename file
    """
    logger.info(f"mv called with src: {src}, dst: {dst}")
    try:
        shutil.move(src, dst)
        return f"Moved: {src} -> {dst}"
    except Exception as e:
        return f"Error moving path: {str(e)}"


def read_file(path: str) -> str:
    """
    Read and return the contents of a file.
    
    Use this tool to view the content of text files, configuration files, logs, etc.
    For binary files, consider using shell commands instead.
    
    Args:
        path (str): Path to the file to read
        
    Returns:
        str: The complete content of the file
        
    Example:
        >>> read_file('/home/user/config.yaml')
        'key: value\nsetting: enabled'
        
    Keywords: read, file content, view file, cat, open file, text file
    """
    logger.info(f"read_file called with path: {path}")
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """
    Write content to a file.
    
    Use this tool to create new files or overwrite existing files with new content.
    ⚠️  Warning: If the file exists, it will be completely overwritten.
    
    Args:
        path (str): Path where the file should be written
        content (str): Content to write to the file
        
    Returns:
        str: Success message with the written path
        
    Example:
        >>> write_file('/home/user/notes.txt', 'My important notes here')
        'File written: /home/user/notes.txt'
        
    Keywords: write, save file, create file, overwrite, file content, text file
    """
    logger.info(f"write_file called with path: {path}")
    try:
        with open(path, 'w') as f:
            f.write(content)
        return f"File written: {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def get_system_info() -> dict:
    """
    Get comprehensive system information including OS, hardware, and user details.
    
    Use this tool to gather information about the host system for diagnostics,
    compatibility checks, or configuration purposes.
    
    Returns:
        dict: Dictionary containing:
            - system: OS name (Linux, Windows, Darwin)
            - node: hostname
            - release: OS release version
            - version: OS version details
            - machine: hardware architecture
            - processor: CPU information
            - architecture: bit architecture (32/64)
            - platform: full platform string
            - uname: detailed uname information
            - env_user: current user
            
    Example:
        >>> get_system_info()
        {'system': 'Linux', 'node': 'myhost', 'release': '5.15.0', ...}
        
    Keywords: system info, system details, OS, hardware, platform, user, diagnostics
    """
    logger.info("get_system_info called")
    try:
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "architecture": platform.architecture(),
            "platform": platform.platform(),
            "uname": platform.uname()._asdict(),
            "env_user": os.getenv("USER") or os.getenv("USERNAME")
        }
        return info
    except Exception as e:
        return {"error": str(e)}


def get_all_tools() -> list[FunctionTool]:
    """
    Return all OS/File tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of OS/File FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=pwd,
            description="Get current working directory. Use for checking current location. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=ls,
            description="List files and directories. Use for browsing directory contents. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=touch,
            description="Create an empty file. Use for creating new files or updating timestamps. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=check_path_exists,
            description="Check if a file or directory exists. Use for verifying paths before operations. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=mkdir,
            description="Create a new directory. Use for making folders with automatic parent directory creation. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=rm,
            description="Remove a file or directory. Use with caution - this is destructive and irreversible. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=cp,
            description="Copy a file or directory. Use for duplicating files or backing up data. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=mv,
            description="Move or rename a file or directory. Use for relocating or renaming files. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=read_file,
            description="Read file contents. Use for viewing text files, configs, and logs. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=write_file,
            description="Write content to a file. Use for creating or overwriting files. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=get_system_info,
            description="Get system information. Use for OS details, hardware info, and diagnostics. Category: Operating System",
        ),
    ]
