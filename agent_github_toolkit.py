"""
GitHub Toolkit - GitHub API integration for Pull Request and repository management.

This module provides GitHub API functionality for creating, managing, and reviewing
Pull Requests, as well as authentication and user management operations.

Category: Version Control
Retriever Keywords: github, pull request, PR, api, review, comment, merge, authentication
"""
import os
import logging
import requests
from typing import Optional
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"

def _get_github_token() -> Optional[str]:
    """
    Get GitHub token from environment variables or GitHub CLI.
    
    Returns:
        str: GitHub token if available, None otherwise
    """
    # Check environment variable first
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    
    # Try to get token from GitHub CLI
    try:
        import subprocess
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return None


def _get_headers() -> dict:
    """
    Get headers for GitHub API requests with authentication.
    
    Returns:
        dict: Headers dictionary with authentication if available
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Torvalds-Agent/1.0",
    }
    
    token = _get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    
    return headers


def _make_request(method: str, endpoint: str, **kwargs) -> dict:
    """
    Make an HTTP request to the GitHub API.
    
    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        endpoint: API endpoint path
        **kwargs: Additional arguments to pass to requests
        
    Returns:
        dict: Response data or error information
    """
    url = f"{GITHUB_API_BASE}{endpoint}"
    headers = _get_headers()
    
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )
        
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        elif response.status_code == 201:
            return {"success": True, "data": response.json(), "status": "created"}
        elif response.status_code == 204:
            return {"success": True, "data": None, "status": "no_content"}
        else:
            # Try to parse error response
            try:
                error_data = response.json()
                error_message = error_data.get("message", "Unknown error")
                errors = error_data.get("errors", [])
                if errors:
                    error_details = "; ".join(str(e) for e in errors)
                    error_message = f"{error_message}: {error_details}"
            except:
                error_message = response.text[:200] if response.text else "Unknown error"
            
            return {
                "success": False,
                "status_code": response.status_code,
                "error": error_message,
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }


# =============================================================================
# Tier 4: Authentication & Configuration
# =============================================================================

def git_check_auth() -> dict:
    """
    Verify GitHub authentication status.
    
    Use this tool to check if GitHub authentication is properly configured
    and working. Tests both token availability and API access.
    
    Returns:
        dict: Dictionary containing:
            - 'authenticated': bool indicating if authentication is working
            - 'method': authentication method used (token, gh_cli, none)
            - 'user': username if authenticated, None otherwise
            - 'error': error message if authentication failed
            
    Example:
        >>> git_check_auth()
        {'authenticated': True, 'method': 'token', 'user': 'KostiantynBushko'}
        
    Keywords: auth, authentication, verify, token, credentials, check
    """
    logger.info("git_check_auth called")
    
    token = _get_github_token()
    if not token:
        return {
            "authenticated": False,
            "method": "none",
            "user": None,
            "error": "No GitHub token found. Set GITHUB_TOKEN environment variable or authenticate with GitHub CLI.",
        }
    
    # Determine authentication method
    method = "gh_cli" if os.environ.get("GITHUB_TOKEN") is None else "token"
    
    # Test API access by getting user info
    result = _make_request("GET", "/user")
    
    if result["success"]:
        return {
            "authenticated": True,
            "method": method,
            "user": result["data"].get("login"),
            "email": result["data"].get("email"),
            "name": result["data"].get("name"),
        }
    else:
        return {
            "authenticated": False,
            "method": method,
            "user": None,
            "error": result.get("error", "Failed to authenticate with GitHub API"),
        }


def git_get_user_info() -> dict:
    """
    Get GitHub user information.
    
    Use this tool to retrieve details about the authenticated GitHub user,
    including profile information, repositories, and organization memberships.
    
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the request succeeded
            - 'data': user information if successful
            - 'error': error message if failed
            
    Example:
        >>> git_get_user_info()
        {'success': True, 'data': {'login': 'KostiantynBushko', 'name': 'Konstantin Bushko', ...}}
        
    Keywords: user, profile, info, identity, details
    """
    logger.info("git_get_user_info called")
    
    result = _make_request("GET", "/user")
    return result


def git_configure_credentials(username: str, email: str) -> bool:
    """
    Configure Git credentials for the current repository.
    
    Use this tool to set up user identity for Git commits.
    This configures the local Git repository settings.
    
    Args:
        username (str): Git username
        email (str): Git email address
        
    Returns:
        bool: True if credentials were configured successfully, False otherwise
        
    Example:
        >>> git_configure_credentials("KostiantynBushko", "kbush@example.com")
        True
        
    Keywords: configure, credentials, user, email, identity, settings
    """
    logger.info(f"git_configure_credentials called with username: {username}, email: {email}")
    
    try:
        import subprocess
        
        # Get current directory or use self-development as default
        cwd = os.getcwd()
        
        # Configure user.name
        result_name = subprocess.run(
            ["git", "config", "user.name", username],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        
        # Configure user.email
        result_email = subprocess.run(
            ["git", "config", "user.email", email],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        
        return result_name.returncode == 0 and result_email.returncode == 0
        
    except subprocess.CalledProcessError:
        return False
    except Exception as e:
        logger.error(f"Failed to configure credentials: {e}")
        return False


# =============================================================================
# Tier 3: GitHub PR Operations (API)
# =============================================================================

def github_create_pull_request(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
    draft: bool = False,
    maintainer_can_modify: bool = True,
) -> dict:
    """
    Create a new Pull Request on GitHub.
    
    Use this tool to submit a PR from one branch to another.
    Requires authentication and proper permissions.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        title (str): PR title
        body (str): PR description/body (supports Markdown)
        head (str): Source branch name (must exist and be pushed)
        base (str): Target branch name (default: 'main')
        draft (bool): Create as draft PR (default: False)
        maintainer_can_modify (bool): Allow maintainers to modify PR (default: True)
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if PR was created
            - 'data': PR information including URL, number, etc. (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_create_pull_request(
        ...     owner="KostiantynBushko",
        ...     repo="agent-torvalds",
        ...     title="feat: Add new feature",
        ...     body="This PR adds...",
        ...     head="feature/new-thing",
        ...     base="main"
        ... )
        {'success': True, 'data': {'number': 42, 'html_url': 'https://github.com/...', ...}}
        
    Keywords: create, pull request, PR, submit, new PR, open PR
    """
    logger.info(f"github_create_pull_request called: {owner}/{repo} {head} -> {base}")
    
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
        "draft": draft,
        "maintainer_can_modify": maintainer_can_modify,
    }
    
    result = _make_request("POST", f"/repos/{owner}/{repo}/pulls", json=payload)
    
    if result["success"]:
        pr_data = result["data"]
        return {
            "success": True,
            "pr_number": pr_data.get("number"),
            "pr_url": pr_data.get("html_url"),
            "data": pr_data,
        }
    else:
        return result


def github_list_pull_requests(
    owner: str,
    repo: str,
    state: str = "open",
    head: str = None,
    base: str = None,
    sort: str = "created",
    direction: str = "desc",
    per_page: int = 30,
) -> dict:
    """
    List Pull Requests for a repository.
    
    Use this tool to inspect existing PRs, filter by state, branch, or other criteria.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        state (str): Filter by state: 'open', 'closed', or 'all' (default: 'open')
        head (str): Filter by head user/org and branch (format: 'user:branch')
        base (str): Filter by base branch name
        sort (str): Sort by: 'created', 'updated', 'popularity', 'long-running' (default: 'created')
        direction (str): Sort direction: 'asc' or 'desc' (default: 'desc')
        per_page (int): Number of results per page (default: 30, max: 100)
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if request succeeded
            - 'data': list of PR information (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_list_pull_requests("KostiantynBushko", "agent-torvalds", state="open")
        {'success': True, 'data': [{'number': 42, 'title': '...', 'state': 'open', ...}, ...]}
        
    Keywords: list, pull requests, PRs, open, closed, filter
    """
    logger.info(f"github_list_pull_requests called: {owner}/{repo} state={state}")
    
    params = {
        "state": state,
        "sort": sort,
        "direction": direction,
        "per_page": min(per_page, 100),  # GitHub API max is 100
    }
    
    if head:
        params["head"] = head
    if base:
        params["base"] = base
    
    result = _make_request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
    
    if result["success"]:
        return {
            "success": True,
            "count": len(result["data"]),
            "data": result["data"],
        }
    else:
        return result


def github_get_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict:
    """
    Get details of a specific Pull Request.
    
    Use this tool to view comprehensive information about a PR, including
    status, reviews, comments, and file changes.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if request succeeded
            - 'data': PR details including title, body, state, etc. (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_get_pull_request("KostiantynBushko", "agent-torvalds", 42)
        {'success': True, 'data': {'number': 42, 'title': '...', 'state': 'open', ...}}
        
    Keywords: get, pull request, PR, details, info, specific PR
    """
    logger.info(f"github_get_pull_request called: {owner}/{repo} #{pr_number}")
    
    result = _make_request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
    return result


def github_update_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    title: str = None,
    body: str = None,
    state: str = None,
    base: str = None,
    maintainer_can_modify: bool = None,
) -> dict:
    """
    Update a Pull Request's title, description, or other metadata.
    
    Use this tool to modify PR details after creation.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        title (str, optional): New PR title
        body (str, optional): New PR description
        state (str, optional): 'open' or 'closed'
        base (str, optional): New base branch
        maintainer_can_modify (bool, optional): Allow maintainers to modify
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if update succeeded
            - 'data': updated PR information (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_update_pull_request(
        ...     "KostiantynBushko", "agent-torvalds", 42,
        ...     title="Updated title",
        ...     body="Updated description"
        ... )
        {'success': True, 'data': {...}}
        
    Keywords: update, modify, edit, pull request, PR, title, description
    """
    logger.info(f"github_update_pull_request called: {owner}/{repo} #{pr_number}")
    
    payload = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if base is not None:
        payload["base"] = base
    if maintainer_can_modify is not None:
        payload["maintainer_can_modify"] = maintainer_can_modify
    
    if not payload:
        return {"success": False, "error": "No update fields provided"}
    
    result = _make_request("PATCH", f"/repos/{owner}/{repo}/pulls/{pr_number}", json=payload)
    return result


def github_close_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict:
    """
    Close a Pull Request without merging.
    
    Use this tool to close a PR that is no longer needed or should be abandoned.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if PR was closed
            - 'data': updated PR information (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_close_pull_request("KostiantynBushko", "agent-torvalds", 42)
        {'success': True, 'data': {...}}
        
    Keywords: close, pull request, PR, abandon, dismiss
    """
    logger.info(f"github_close_pull_request called: {owner}/{repo} #{pr_number}")
    
    return github_update_pull_request(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        state="closed",
    )


def github_merge_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    merge_method: str = "merge",
    commit_title: str = None,
    commit_message: str = None,
) -> dict:
    """
    Merge a Pull Request.
    
    Use this tool to complete the PR workflow by merging the changes.
    Supports merge, squash, and rebase merge methods.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        merge_method (str): Merge method: 'merge', 'squash', or 'rebase' (default: 'merge')
        commit_title (str, optional): Custom commit title for the merge
        commit_message (str, optional): Custom commit message for the merge
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if merge succeeded
            - 'data': merge result information (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_merge_pull_request("KostiantynBushko", "agent-torvalds", 42, merge_method="squash")
        {'success': True, 'data': {'merged': True, 'sha': '...', ...}}
        
    Keywords: merge, pull request, PR, complete, squash, rebase
    """
    logger.info(f"github_merge_pull_request called: {owner}/{repo} #{pr_number} method={merge_method}")
    
    payload = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message
    
    result = _make_request(
        "PUT",
        f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        json=payload,
    )
    
    if result["success"]:
        return {
            "success": True,
            "merged": True,
            "merge_commit_sha": result["data"].get("sha"),
            "data": result["data"],
        }
    else:
        return result


def github_comment_on_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    comment: str,
) -> dict:
    """
    Add a comment to a Pull Request.
    
    Use this tool to leave feedback or notes on a PR.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        comment (str): Comment text (supports Markdown)
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if comment was posted
            - 'data': comment information including URL (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_comment_on_pull_request(
        ...     "KostiantynBushko", "agent-torvalds", 42,
        ...     comment="LGTM! Nice work on this feature."
        ... )
        {'success': True, 'data': {'id': 12345, 'html_url': '...', ...}}
        
    Keywords: comment, review, feedback, pull request, PR, note
    """
    logger.info(f"github_comment_on_pull_request called: {owner}/{repo} #{pr_number}")
    
    payload = {"body": comment}
    
    result = _make_request(
        "POST",
        f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
        json=payload,
    )
    
    if result["success"]:
        return {
            "success": True,
            "comment_id": result["data"].get("id"),
            "comment_url": result["data"].get("html_url"),
            "data": result["data"],
        }
    else:
        return result


def github_review_file_changes(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict:
    """
    Get file changes in a Pull Request.
    
    Use this tool to review the diff and file modifications in a PR.
    Returns a list of changed files with patch information.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if request succeeded
            - 'data': list of file changes with patches (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_review_file_changes("KostiantynBushko", "agent-torvalds", 42)
        {'success': True, 'data': [
            {'filename': 'src/main.py', 'status': 'modified', 'patch': '...', ...},
            ...
        ]}
        
    Keywords: review, files, changes, diff, patch, pull request, PR
    """
    logger.info(f"github_review_file_changes called: {owner}/{repo} #{pr_number}")
    
    result = _make_request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
    
    if result["success"]:
        return {
            "success": True,
            "files_changed": len(result["data"]),
            "data": result["data"],
        }
    else:
        return result


def github_get_pull_request_comments(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict:
    """
    Get all comments on a Pull Request.
    
    Use this tool to retrieve review comments and discussion on a PR.
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if request succeeded
            - 'data': list of comments (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_get_pull_request_comments("KostiantynBushko", "agent-torvalds", 42)
        {'success': True, 'data': [{'id': 123, 'body': '...', 'user': {...}, ...}, ...]}
        
    Keywords: comments, discussion, review, pull request, PR, feedback
    """
    logger.info(f"github_get_pull_request_comments called: {owner}/{repo} #{pr_number}")
    
    result = _make_request("GET", f"/repos/{owner}/{repo}/issues/{pr_number}/comments")
    
    if result["success"]:
        return {
            "success": True,
            "count": len(result["data"]),
            "data": result["data"],
        }
    else:
        return result


def github_get_pull_request_reviews(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict:
    """
    Get review submissions for a Pull Request.
    
    Use this tool to check the review status (APPROVED, CHANGES_REQUESTED, COMMENTED, etc.)
    
    Args:
        owner (str): Repository owner (username or organization)
        repo (str): Repository name
        pr_number (int): PR number
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if request succeeded
            - 'data': list of reviews (on success)
            - 'error': error message if failed
            
    Example:
        >>> github_get_pull_request_reviews("KostiantynBushko", "agent-torvalds", 42)
        {'success': True, 'data': [{'id': 123, 'state': 'APPROVED', 'user': {...}, ...}, ...]}
        
    Keywords: reviews, approval, status, pull request, PR, check
    """
    logger.info(f"github_get_pull_request_reviews called: {owner}/{repo} #{pr_number}")
    
    result = _make_request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")
    
    if result["success"]:
        return {
            "success": True,
            "count": len(result["data"]),
            "data": result["data"],
        }
    else:
        return result


def get_all_tools() -> list[FunctionTool]:
    """
    Return all GitHub tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of GitHub FunctionTool objects
    """
    logger.info("github get_all_tools called")
    return [
        # Tier 4: Authentication & Configuration
        FunctionTool.from_defaults(
            fn=git_check_auth,
            description="Verify GitHub authentication status. Use for checking if GitHub API access is working. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_user_info,
            description="Get GitHub user information. Use for retrieving profile and identity details. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_configure_credentials,
            description="Configure Git credentials. Use for setting up user identity for commits. Category: Version Control",
        ),
        # Tier 3: GitHub PR Operations
        FunctionTool.from_defaults(
            fn=github_create_pull_request,
            description="Create a Pull Request on GitHub. Use for submitting PRs from feature branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_list_pull_requests,
            description="List Pull Requests for a repository. Use for inspecting open/closed PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request,
            description="Get details of a specific Pull Request. Use for viewing PR information. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_update_pull_request,
            description="Update a Pull Request's title, description, or other metadata. Use for modifying PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_close_pull_request,
            description="Close a Pull Request without merging. Use for abandoning or dismissing PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_merge_pull_request,
            description="Merge a Pull Request. Use for completing the PR workflow with merge/squash/rebase. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_comment_on_pull_request,
            description="Add a comment to a Pull Request. Use for leaving feedback or notes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_review_file_changes,
            description="Get file changes in a Pull Request. Use for reviewing diffs and patches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request_comments,
            description="Get all comments on a Pull Request. Use for retrieving discussion and feedback. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request_reviews,
            description="Get review submissions for a Pull Request. Use for checking approval status. Category: Version Control",
        ),
    ]
