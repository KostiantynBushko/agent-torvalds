# Step 06: Testing & Validation

## Objective
Create comprehensive tests for the project manager feature, including unit tests, integration tests, and end-to-end workflow tests.

## Files to Create
- `project-manager/tests/test_project_scanner.py`
- `project-manager/tests/test_workspace_config.py`
- `project-manager/tests/test_project_manager_toolkit.py`
- `project-manager/tests/test_project_manager_integration.py`

## Implementation Details

### 1. Unit Tests for Project Scanner

```python
# test_project_scanner.py
import pytest
import tempfile
import os
from pathlib import Path
from project_scanner import ProjectScanner

class TestProjectScanner:
    def test_detect_python_project(self, tmp_path):
        """Test Python project detection."""
        (tmp_path / "requirements.txt").write_text("pytest")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "Python"
    
    def test_detect_nodejs_project(self, tmp_path):
        """Test Node.js project detection."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "Node.js"
    
    def test_detect_java_project(self, tmp_path):
        """Test Java/Maven project detection."""
        (tmp_path / "pom.xml").write_text("<project></project>")
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "Java"
    
    def test_detect_cpp_project(self, tmp_path):
        """Test C/C++ CMake project detection."""
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.0)")
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "C/C++"
    
    def test_detect_rust_project(self, tmp_path):
        """Test Rust/Cargo project detection."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "Rust"
    
    def test_detect_go_project(self, tmp_path):
        """Test Go module detection."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result == "Go"
    
    def test_empty_directory(self, tmp_path):
        """Test empty directory returns None."""
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result is None
    
    def test_ambiguous_detection(self, tmp_path):
        """Test ambiguous case returns multiple candidates."""
        (tmp_path / "requirements.txt").write_text("pytest")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        scanner = ProjectScanner()
        result = scanner.detect_project_type(str(tmp_path))
        assert result is None  # Below threshold
        
        candidates = scanner.get_candidates(str(tmp_path))
        assert len(candidates) >= 2
    
    def test_confidence_scoring(self, tmp_path):
        """Test confidence scores are normalized."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        (tmp_path / "requirements.txt").write_text("pytest")
        
        scanner = ProjectScanner()
        candidates = scanner.get_candidates(str(tmp_path))
        
        for _, confidence in candidates:
            assert 0.0 <= confidence <= 1.0
    
    def test_max_depth_limit(self, tmp_path):
        """Test scanning respects max_depth."""
        # Create nested structure
        deep_path = tmp_path / "a" / "b" / "c" / "d"
        deep_path.mkdir(parents=True)
        (deep_path / "Cargo.toml").write_text('[package]')
        
        scanner = ProjectScanner(max_depth=2)
        result = scanner.detect_project_type(str(tmp_path))
        assert result is None  # Too deep to detect
```

### 2. Unit Tests for Workspace Config

```python
# test_workspace_config.py
import pytest
import json
from pathlib import Path
from workspace_config import WorkspaceConfig

class TestWorkspaceConfig:
    def test_create_default_config(self, tmp_path):
        """Test default config creation."""
        config = WorkspaceConfig(str(tmp_path))
        assert "version" in config.config
        assert "projects" in config.config
        assert config.config["projects"] == []
    
    def test_add_project(self, tmp_path):
        """Test adding a project."""
        config = WorkspaceConfig(str(tmp_path))
        config.add_project(
            name="test_project",
            path=".",
            project_type="Python",
            indicators=["requirements.txt"],
            confidence=0.9,
            git_repo=True,
        )
        
        project = config.get_project("test_project")
        assert project is not None
        assert project["type"] == "Python"
        assert project["git_repo"] is True
    
    def test_update_project(self, tmp_path):
        """Test updating a project."""
        config = WorkspaceConfig(str(tmp_path))
        config.add_project("test", ".", "Python", [], 0.9, False)
        config.update_project("test", confidence=0.95)
        
        project = config.get_project("test")
        assert project["confidence"] == 0.95
    
    def test_remove_project(self, tmp_path):
        """Test removing a project."""
        config = WorkspaceConfig(str(tmp_path))
        config.add_project("test", ".", "Python", [], 0.9, False)
        result = config.remove_project("test")
        
        assert result is True
        assert config.get_project("test") is None
    
    def test_persistence(self, tmp_path):
        """Test config persists to disk."""
        config = WorkspaceConfig(str(tmp_path))
        config.add_project("test", ".", "Python", [], 0.9, False)
        config.save()
        
        # Reload
        config2 = WorkspaceConfig(str(tmp_path))
        project = config2.get_project("test")
        assert project is not None
    
    def test_set_actions(self, tmp_path):
        """Test setting project actions."""
        config = WorkspaceConfig(str(tmp_path))
        config.add_project("test", ".", "Python", [], 0.9, False)
        config.set_actions("test", {"build": "make", "test": "pytest"})
        
        project = config.get_project("test")
        assert project["actions"]["build"] == "make"
```

### 3. Integration Tests

```python
# test_project_manager_integration.py
import pytest
from pathlib import Path
from agent_project_manager import (
    scan_current_directory,
    initialize_project,
    get_workspace_config,
)

class TestProjectManagerIntegration:
    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test complete project detection and initialization workflow."""
        # Create a Python project structure
        (tmp_path / "requirements.txt").write_text("pytest")
        (tmp_path / "main.py").write_text("print('hello')")
        
        # Change to temp dir
        monkeypatch.chdir(tmp_path)
        
        # Scan
        result = scan_current_directory()
        assert "Python" in result
        
        # Initialize
        init_result = initialize_project("test_project", "Python")
        assert "git_repo" in init_result
        
        # Get config
        config_result = get_workspace_config()
        assert "projects" in config_result
```

### 4. Test Execution
```bash
# Run tests
cd self-development
python -m pytest tests/test_project_scanner.py -v
python -m pytest tests/test_workspace_config.py -v
python -m pytest tests/test_project_manager_integration.py -v
```

## Acceptance Criteria
- [ ] All unit tests pass
- [ ] Integration tests verify end-to-end workflow
- [ ] Test coverage > 80% for new modules
- [ ] Tests run in CI/CD pipeline
- [ ] Edge cases are tested (empty dirs, ambiguous cases, errors)

## Dependencies
- Step 01: `project_scanner.py`
- Step 02: `workspace_config.py`
- Step 03: `agent_project_manager.py`
- pytest
