import subprocess
import os

def git_get_latest_commit(path: str) -> str:
    """
    This function is useful to get the latest commit in the given path.
    """
    try:
        # Execute git log command to get the latest commit
        result = subprocess.run(['git', 'log', '-1', '--format=%H'],
                               cwd=path,
                               capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e}"

def git_init_repo(path: str) -> bool:
    """
    Initialize a new Git repository at the given path.
    
    Args:
        path (str): The directory path where the Git repository should be initialized
        
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    try:
        # Check if path exists
        if not os.path.exists(path):
            return False
            
        # Execute git init command
        result = subprocess.run(['git', 'init'], 
                               cwd=path,
                               capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error initializing Git repository: {e}")
        return False

def git_add_files(path: str, files: list) -> bool:
    """
    Add files to the staging area for commit.
    
    Args:
        path (str): The directory path of the Git repository
        files (list): List of file paths to add
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Build git add command
        cmd = ['git', 'add'] + files
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error adding files: {e}")
        return False

def git_commit(path: str, message: str) -> bool:
    """
    Create a commit with the given message.
    
    Args:
        path (str): The directory path of the Git repository
        message (str): Commit message
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if we have any changes to commit
        result = subprocess.run(['git', 'diff-index', '--cached', 'HEAD'], 
                               cwd=path, capture_output=True, text=True)
        if result.stdout.strip() == "":
            print("No changes to commit")
            return False
            
        # Create commit
        cmd = ['git', 'commit', '-m', message]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating commit: {e}")
        return False

def git_get_status(path: str) -> dict:
    """
    Get current repository status.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        dict: Dictionary containing status information
    """
    try:
        # Get git status
        result = subprocess.run(['git', 'status', '--porcelain'], 
                               cwd=path, capture_output=True, text=True, check=True)
        return {
            'status': 'success',
            'output': result.stdout.strip()
        }
    except subprocess.CalledProcessError as e:
        return {
            'status': 'error',
            'message': f"Error getting status: {e}"
        }