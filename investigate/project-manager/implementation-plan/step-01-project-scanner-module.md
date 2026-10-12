# Step 01: Project Scanner Module

## Objective
Create the core project type detection engine that scans directories and identifies project types based on file indicators.

## Files to Create
- `investigate/project-manager/scanner.py`

## Implementation Details

### 1. Project Type Indicator Database
Define a comprehensive mapping of project types to their file indicators:

```python
PROJECT_INDICATORS = {
    "Python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
    "Node.js": ["package.json", "yarn.lock", "package-lock.json", ".npmrc"],
    "Java": ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
    "C/C++": ["CMakeLists.txt", "Makefile", "configure.ac", "autogen.sh"],
    "Rust": ["Cargo.toml", "Cargo.lock"],
    "Go": ["go.mod", "go.sum", "Gopkg.toml"],
    "ESP32/FreeRTOS": ["sdkconfig", "CMakeLists.txt", "main.c", "partitions.csv"],
    "PX4/UAV": ["ROMFS", "CMakeLists.txt", "px4fmu_common"],
    "Motorola TRBO": [".rdt", "config.json", ".bin"],
    "FPGA": [".vhd", ".sv", ".xdc", ".qsf"],
    "Yocto": ["conf/local.conf", "conf/bblayers.conf", "meta-"],
    "System Software": ["Makefile", "Kconfig", "arch/"],
    "Documentation": [".md", ".rst", "mkdocs.yml", "docs/"],
    "Data Science": [".ipynb", "requirements.txt", "notebooks/"],
    "Configuration": [".json", ".yaml", ".ini", ".conf"],
}
```

### 2. Scanner Class
Create a `ProjectScanner` class with the following methods:

```python
class ProjectScanner:
    def __init__(self, max_depth=3, confidence_threshold=0.6):
        self.max_depth = max_depth
        self.confidence_threshold = confidence_threshold
    
    def scan_directory(self, path: str) -> Dict[str, float]:
        """Scan directory and return dict of {project_type: confidence_score}"""
        # Walk directory up to max_depth
        # Check for indicator files
        # Calculate confidence based on indicator presence
        pass
    
    def detect_project_type(self, path: str) -> Optional[str]:
        """Return the detected project type or None if ambiguous"""
        scores = self.scan_directory(path)
        if not scores:
            return None
        
        best_type = max(scores, key=scores.get)
        if scores[best_type] >= self.confidence_threshold:
            return best_type
        return None  # Below threshold, ambiguous
    
    def get_candidates(self, path: str) -> List[Tuple[str, float]]:
        """Return all candidate types with their confidence scores"""
        scores = self.scan_directory(path)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 3. Confidence Scoring Algorithm
- Each indicator file found adds points to the corresponding project type
- Weight indicators: primary indicators (e.g., `pyproject.toml`) score higher than secondary
- Normalize scores to 0.0-1.0 range
- Handle multiple project types in one directory (workspace mode)

### 4. Edge Cases
- Empty directories: return `None`
- Directories with no recognizable indicators: return `"Unknown"`
- Multiple strong candidates: return all candidates for HITL resolution
- Nested projects: scan subdirectories recursively up to `max_depth`

## Acceptance Criteria
- [ ] Scanner correctly identifies Python, Node.js, Java, C/C++, Rust, Go projects
- [ ] Confidence scores are calculated and normalized
- [ ] Ambiguous cases return multiple candidates
- [ ] Scanning respects `max_depth` limit
- [ ] Unit tests pass for all project types

## Dependencies
- None (uses only standard library: `os`, `pathlib`, `typing`)
