
"""
Project Scanner Module - Project type detection engine.

This module scans directories and identifies project types based on file indicators,
using a confidence scoring algorithm to handle ambiguous cases.

Category: Project Management
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Project Type Indicator Database
# ============================================================================
# Each project type maps to a list of (indicator, weight) tuples.
# Primary indicators have higher weights than secondary ones.
# Weights are normalized later to produce a 0.0-1.0 confidence score.

PROJECT_INDICATORS: Dict[str, List[Tuple[str, float]]] = {
    "Python": [
        ("pyproject.toml", 0.9),
        ("setup.py", 0.8),
        ("requirements.txt", 0.7),
        ("Pipfile", 0.6),
        ("poetry.lock", 0.7),
        ("setup.cfg", 0.6),
        ("tox.ini", 0.5),
        ("pytest.ini", 0.5),
        ("pyrightconfig.json", 0.4),
        (".python-version", 0.5),
        ("__init__.py", 0.3),
    ],
    "Node.js": [
        ("package.json", 0.9),
        ("package-lock.json", 0.8),
        ("yarn.lock", 0.8),
        ("pnpm-lock.yaml", 0.7),
        (".npmrc", 0.5),
        ("tsconfig.json", 0.6),
        ("next.config.js", 0.5),
        ("next.config.mjs", 0.5),
        ("nuxt.config.js", 0.5),
        ("vue.config.js", 0.5),
        ("angular.json", 0.6),
    ],
    "Java": [
        ("pom.xml", 0.9),
        ("build.gradle", 0.9),
        ("build.gradle.kts", 0.9),
        ("settings.gradle", 0.7),
        ("settings.gradle.kts", 0.7),
        ("gradlew", 0.6),
        ("gradlew.bat", 0.5),
        ("mvnw", 0.6),
        ("mvnw.cmd", 0.5),
        ("gradle/wrapper/gradle-wrapper.properties", 0.4),
        (".mvn/wrapper/maven-wrapper.properties", 0.4),
    ],
    "C/C++": [
        ("CMakeLists.txt", 0.9),
        ("Makefile", 0.8),
        ("configure.ac", 0.7),
        ("autogen.sh", 0.5),
        ("meson.build", 0.8),
        ("SConstruct", 0.6),
        (".clang-format", 0.4),
        (".clang-tidy", 0.4),
        ("compile_commands.json", 0.5),
        ("meson_options.txt", 0.4),
    ],
    "Rust": [
        ("Cargo.toml", 0.9),
        ("Cargo.lock", 0.7),
        (".cargo/config.toml", 0.5),
        ("rust-toolchain", 0.5),
        ("rustfmt.toml", 0.4),
        ("clippy.toml", 0.4),
    ],
    "Go": [
        ("go.mod", 0.9),
        ("go.sum", 0.8),
        ("Gopkg.toml", 0.6),
        ("Gopkg.lock", 0.6),
        ("glide.yaml", 0.5),
        (".go-version", 0.5),
        ("golangci-lint.yaml", 0.4),
    ],
    "ESP32/FreeRTOS": [
        ("sdkconfig", 0.9),
        ("partitions.csv", 0.7),
        ("sdkconfig.defaults", 0.6),
        ("CMakeLists.txt", 0.5),  # shared with C/C++ but lower weight here
        ("main.c", 0.3),
        ("Kconfig", 0.5),
        ("Kconfig.projbuild", 0.4),
    ],
    "PX4/UAV": [
        ("ROMFS", 0.8),
        ("px4fmu_common", 0.7),
        ("CMakeLists.txt", 0.5),
        ("platforms/", 0.4),
        ("src/modules/", 0.4),
    ],
    "Motorola TRBO": [
        (".rdt", 0.9),
        ("config.json", 0.4),
        (".bin", 0.3),
    ],
    "FPGA": [
        (".vhd", 0.8),
        (".sv", 0.8),
        (".v", 0.8),
        (".xdc", 0.7),
        (".qsf", 0.7),
        ("constraints.xdc", 0.6),
        ("system_top.vhd", 0.5),
        ("system_top.sv", 0.5),
    ],
    "Yocto": [
        ("conf/local.conf", 0.9),
        ("conf/bblayers.conf", 0.9),
        ("meta-", 0.5),
        ("bitbake", 0.6),
        ("oe-init-build-env", 0.6),
        ("layers/meta-", 0.5),
    ],
    "System Software": [
        ("Makefile", 0.6),
        ("Kconfig", 0.8),
        ("arch/", 0.4),
        ("drivers/", 0.4),
        ("include/", 0.3),
        (".gitignore", 0.1),
    ],
    "Documentation": [
        ("mkdocs.yml", 0.8),
        ("docs/", 0.5),
        ("README.md", 0.3),
        ("CONTRIBUTING.md", 0.3),
        (".rst", 0.4),
        ("sphinx/", 0.5),
        ("conf.py", 0.5),
    ],
    "Data Science": [
        (".ipynb", 0.8),
        ("notebooks/", 0.6),
        ("requirements.txt", 0.5),
        ("JupyterNotebook", 0.7),
        ("environment.yml", 0.5),
        ("Pipfile", 0.3),
    ],
    "Configuration": [
        (".json", 0.3),
        (".yaml", 0.3),
        (".ini", 0.3),
        (".conf", 0.3),
        (".cfg", 0.3),
        (".toml", 0.3),
    ],
}

# File extension-based indicators (for file types without specific filenames)
EXTENSION_INDICATORS: Dict[str, Dict[str, float]] = {
    "FPGA": {".vhd": 0.8, ".sv": 0.8, ".v": 0.8, ".xdc": 0.7, ".qsf": 0.7},
    "Data Science": {".ipynb": 0.8},
    "Python": {".py": 0.3, ".pyi": 0.3},
    "Rust": {".rs": 0.4},
    "Go": {".go": 0.4},
    "Java": {".java": 0.5},
    "C/C++": {".c": 0.3, ".cpp": 0.3, ".h": 0.2, ".hpp": 0.2, ".cc": 0.3},
    "Node.js": {".js": 0.2, ".ts": 0.3, ".tsx": 0.3, ".jsx": 0.2},
}


class ProjectScanner:
    """
    Scans directories and identifies project types based on file indicators.
    
    Uses a confidence scoring algorithm to handle ambiguous cases where
    multiple project types could be detected.
    
    Args:
        max_depth: Maximum directory depth to scan (default: 3)
        confidence_threshold: Minimum confidence to auto-detect (default: 0.6)
    """

    def __init__(self, max_depth: int = 3, confidence_threshold: float = 0.6):
        self.max_depth = max_depth
        self.confidence_threshold = confidence_threshold

    def scan_directory(self, path: str) -> Dict[str, float]:
        """
        Scan directory and return dict of {project_type: confidence_score}.
        
        Walks the directory up to max_depth and checks for indicator files.
        Confidence is calculated based on the presence and weight of indicators.
        
        Args:
            path: Directory path to scan
            
        Returns:
            Dictionary mapping project types to confidence scores (0.0-1.0)
        """
        project_path = Path(path).resolve()
        
        if not project_path.is_dir():
            logger.warning(f"Path is not a directory: {path}")
            return {}

        # Accumulate scores for each project type
        scores: Dict[str, float] = {}
        max_possible: Dict[str, float] = {}

        # Initialize max_possible scores from indicator database
        for proj_type, indicators in PROJECT_INDICATORS.items():
            max_possible[proj_type] = sum(weight for _, weight in indicators)

        # Walk directory up to max_depth
        for root, dirs, files in os.walk(project_path):
            # Calculate current depth
            rel_path = Path(root).relative_to(project_path)
            depth = len(rel_path.parts)
            
            if depth > self.max_depth:
                dirs.clear()  # Don't recurse deeper
                continue

            # Check filename-based indicators
            for proj_type, indicators in PROJECT_INDICATORS.items():
                for indicator, weight in indicators:
                    # Check if indicator is a directory or file
                    indicator_path = Path(root) / indicator
                    if indicator_path.exists():
                        scores[proj_type] = scores.get(proj_type, 0.0) + weight

            # Check file extension-based indicators
            for file in files:
                file_ext = Path(file).suffix.lower()
                if not file_ext:
                    continue
                    
                for proj_type, ext_weights in EXTENSION_INDICATORS.items():
                    if file_ext in ext_weights:
                        # Reduce weight for deeper files (less relevant)
                        depth_factor = max(0.5, 1.0 - (depth * 0.15))
                        scores[proj_type] = scores.get(proj_type, 0.0) + (
                            ext_weights[file_ext] * depth_factor
                        )

            # Check for directory-based indicators
            for dir_name in dirs:
                for proj_type, indicators in PROJECT_INDICATORS.items():
                    for indicator, weight in indicators:
                        if indicator == dir_name or indicator.startswith(f"{dir_name}/"):
                            scores[proj_type] = scores.get(proj_type, 0.0) + (weight * 0.5)

        # Normalize scores to 0.0-1.0 range
        normalized_scores: Dict[str, float] = {}
        for proj_type, score in scores.items():
            max_score = max_possible.get(proj_type, 1.0)
            if max_score > 0:
                normalized = min(score / max_score, 1.0)
                # Only include if there's meaningful confidence
                if normalized > 0.05:
                    normalized_scores[proj_type] = round(normalized, 3)

        logger.debug(f"Scan results for {path}: {normalized_scores}")
        return normalized_scores

    def detect_project_type(self, path: str) -> Optional[str]:
        """
        Return the detected project type or None if ambiguous.
        
        Args:
            path: Directory path to detect project type for
            
        Returns:
            The project type string if detected with sufficient confidence,
            None if ambiguous or below threshold
        """
        scores = self.scan_directory(path)
        
        if not scores:
            return None

        best_type = max(scores, key=scores.get)
        
        if scores[best_type] >= self.confidence_threshold:
            return best_type
        
        # Check if there's a clear winner (significant gap between top 2)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0][1] - sorted_scores[1][1]
            if gap >= 0.2:
                return sorted_scores[0][0]
        
        return None  # Below threshold, ambiguous

    def get_candidates(self, path: str) -> List[Tuple[str, float]]:
        """
        Return all candidate types with their confidence scores.
        
        Args:
            path: Directory path to scan
            
        Returns:
            List of (project_type, confidence) tuples sorted by confidence descending
        """
        scores = self.scan_directory(path)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def get_project_indicators(self, project_type: str) -> List[Tuple[str, float]]:
        """
        Get the indicator definitions for a specific project type.
        
        Args:
            project_type: The project type name
            
        Returns:
            List of (indicator, weight) tuples
        """
        return PROJECT_INDICATORS.get(project_type, [])

    def get_supported_types(self) -> List[str]:
        """
        Get all supported project types.
        
        Returns:
            List of supported project type names
        """
        return list(PROJECT_INDICATORS.keys())


def scan_path(path: str = ".", max_depth: int = 3, confidence_threshold: float = 0.6) -> Dict:
    """
    Convenience function to scan a path and get results.
    
    Args:
        path: Directory path to scan
        max_depth: Maximum directory depth to scan
        confidence_threshold: Minimum confidence for auto-detection
        
    Returns:
        Dictionary with scan results
    """
    scanner = ProjectScanner(max_depth=max_depth, confidence_threshold=confidence_threshold)
    
    detected = scanner.detect_project_type(path)
    candidates = scanner.get_candidates(path)
    
    return {
        "path": str(Path(path).resolve()),
        "detected_type": detected,
        "confidence_threshold": confidence_threshold,
        "candidates": [{"type": t, "confidence": c} for t, c in candidates],
        "is_ambiguous": detected is None and len(candidates) > 1,
    }


if __name__ == "__main__":
    # Quick test
    import sys
    
    target_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print(f"Scanning: {target_path}")
    print("=" * 60)
    
    result = scan_path(target_path)
    
    print(f"Path: {result['path']}")
    print(f"Detected: {result['detected_type']}")
    print(f"Ambiguous: {result['is_ambiguous']}")
    print(f"\nCandidates:")
    for candidate in result['candidates']:
        bar = "#" * int(candidate['confidence'] * 40)
        print(f"  {candidate['type']:<20} {candidate['confidence']:.3f} {bar}")
