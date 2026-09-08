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

def git_generate_changelog(path: str, output_file: str = "CHANGELOG.md") -> bool:
    """
    Generate a changelog file from Git commit history.
    
    Args:
        path (str): The directory path of the Git repository
        output_file (str): Name of the changelog file to create
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get all commits with their messages and dates
        result = subprocess.run([
            'git', 'log', '--pretty=format:%h|%ad|%s', 
            '--date=short', '--no-merges'
        ], cwd=path, capture_output=True, text=True, check=True)
        
        commits = result.stdout.strip().split('\n') if result.stdout.strip() else []
        
        # Format changelog content
        changelog_content = "# Changelog\n\n"
        changelog_content += "All notable changes to this project will be documented in this file.\n\n"
        
        current_date = ""
        for commit in commits:
            if not commit:
                continue
            try:
                commit_hash, date, message = commit.split('|', 2)
                # Format the date for better readability
                formatted_date = date
                
                # Add date header if different from previous
                if date != current_date:
                    changelog_content += f"## {date}\n\n"
                    current_date = date
                
                changelog_content += f"- {message} ({commit_hash})\n"
            except ValueError:
                # Skip malformed commit entries
                continue
        
        # Write to file
        with open(os.path.join(path, output_file), 'w') as f:
            f.write(changelog_content)
            
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error generating changelog: {e}")
        return False

def git_get_recent_changes(path: str, num_commits: int = 10) -> list:
    """
    Get recent commits from the Git repository.
    
    Args:
        path (str): The directory path of the Git repository
        num_commits (int): Number of recent commits to retrieve (default: 10)
        
    Returns:
        list: List of dictionaries containing commit information
    """
    try:
        # Get specified number of recent commits
        result = subprocess.run([
            'git', 'log', f'-{num_commits}', '--pretty=format:%h|%ad|%s|%an', 
            '--date=short', '--no-merges'
        ], cwd=path, capture_output=True, text=True, check=True)
        
        commits = result.stdout.strip().split('\n') if result.stdout.strip() else []
        recent_changes = []
        
        for commit in commits:
            if not commit:
                continue
            try:
                commit_hash, date, message, author = commit.split('|', 3)
                recent_changes.append({
                    'hash': commit_hash,
                    'date': date,
                    'message': message,
                    'author': author
                })
            except ValueError:
                # Skip malformed commit entries
                continue
                
        return recent_changes
    except subprocess.CalledProcessError as e:
        print(f"Error getting recent changes: {e}")
        return []

def git_update_changelog(path: str, change_type: str, description: str) -> bool:
    """
    Update the changelog with a new entry.
    
    Args:
        path (str): The directory path of the Git repository
        change_type (str): Type of change (feature, fix, docs, etc.)
        description (str): Description of the change
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get current date
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        
        # Read existing changelog
        changelog_path = os.path.join(path, "CHANGELOG.md")
        changelog_content = ""
        
        if os.path.exists(changelog_path):
            with open(changelog_path, 'r') as f:
                changelog_content = f.read()
        
        # Create new entry
        new_entry = f"- [{change_type}] {description} ({today})\n"
        
        # Find the first header to insert after
        header_pos = changelog_content.find("# Changelog")
        if header_pos == -1:
            # If no header found, create basic structure
            changelog_content = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n"
        
        # Insert the new entry after the header
        insert_pos = changelog_content.find("\n\n") + 2  # Position after first double newline
        
        if insert_pos > 0:
            updated_content = changelog_content[:insert_pos] + f"## {today}\n\n{new_entry}\n" + changelog_content[insert_pos:]
        else:
            updated_content = changelog_content + f"\n## {today}\n\n{new_entry}\n"
        
        # Write back to file
        with open(changelog_path, 'w') as f:
            f.write(updated_content)
            
        return True
    except Exception as e:
        print(f"Error updating changelog: {e}")
        return False

def git_get_email(path: str) -> str:
    """
    Get the user's email from Git configuration.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        str: User's email address or empty string if not found
    """
    try:
        # Try to get user.email from git config
        result = subprocess.run(['git', 'config', '--get', 'user.email'], 
                               cwd=path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""

def git_init_and_commit(path: str, message: str) -> bool:
    """
    Initialize a Git repository and make the first commit.
    
    Args:
        path (str): The directory path where the Git repository should be initialized
        message (str): Commit message
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Initialize git repo if not already initialized
        if not os.path.exists(os.path.join(path, '.git')):
            result = subprocess.run(['git', 'init'], cwd=path, capture_output=True, text=True, check=True)
        
        # Get user email for commit
        email = git_get_email(path)
        
        # Add all files to staging
        add_result = subprocess.run(['git', 'add', '.'], cwd=path, capture_output=True, text=True)
        
        # Configure user if not already set
        if not email:
            subprocess.run(['git', 'config', 'user.email', 'torvalds@agent.com'], cwd=path, capture_output=True, text=True)
            subprocess.run(['git', 'config', 'user.name', 'Torvalds Agent'], cwd=path, capture_output=True, text=True)
        
        # Create commit
        cmd = ['git', 'commit', '-m', message]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error initializing and committing: {e}")
        return False

def git_remote_add(path: str, name: str, url: str) -> bool:
    """
    Add a remote repository.
    
    Args:
        path (str): The directory path of the Git repository
        name (str): Name of the remote (e.g., 'origin')
        url (str): URL of the remote repository
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cmd = ['git', 'remote', 'add', name, url]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error adding remote: {e}")
        return False

def git_push(path: str, remote: str = "origin", branch: str = "main", set_upstream: bool = False) -> bool:
    """
    Push changes to a remote repository.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository (default: 'origin')
        branch (str): Branch name to push (default: 'main')
        set_upstream (bool): Whether to set upstream tracking (default: False)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # If we need to set upstream
        if set_upstream:
            cmd = ['git', 'push', '--set-upstream', remote, branch]
        else:
            cmd = ['git', 'push', remote, branch]
            
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error pushing to remote: {e}")
        return False

def git_remote_get(path: str) -> list[dict]:
    """
    Get list of configured remotes.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        list[dict]: List of dictionaries containing remote information
    """
    try:
        result = subprocess.run(['git', 'remote', '-v'], 
                               cwd=path, capture_output=True, text=True, check=True)
        
        remotes = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    url = parts[1]
                    remotes.append({'name': name, 'url': url})
        
        return remotes
    except subprocess.CalledProcessError as e:
        print(f"Error getting remotes: {e}")
        return []

def git_set_upstream(path: str, remote: str, branch: str) -> bool:
    """
    Set upstream tracking for a branch.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository
        branch (str): Branch name to set upstream for
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cmd = ['git', 'branch', '--set-upstream-to', f'{remote}/{branch}']
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error setting upstream: {e}")
        return False