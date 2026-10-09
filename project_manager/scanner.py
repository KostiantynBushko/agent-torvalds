"""
Project Scanner - Project type detection engine.

Scans directories and identifies project types based on file indicators,
using a confidence scoring algorithm to handle ambiguous cases.

Category: Project Management
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .types import (
    PROJECT_INDICATORS,
    EXTENSION_INDICATORS,
    IndicatorTuple,
)

logger = logging.getLogger(__name__)


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

    def get_project_indicators(self, project_type: str) -> List[IndicatorTuple]:
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
