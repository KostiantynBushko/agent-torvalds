#!/usr/bin/env python3
"""Measure what a missing ``pandas`` does to the agent.

The data analysis toolkit used to be a mandatory top-level module: both
call sites imported it **unguarded**, so a missing ``pandas`` - or a
broken install - raised straight out of the tool discovery and the agent
did not boot at all.

The move makes the toolkit optional, the way every other toolkit under
``toolkits/`` already was.  This script measures that, on whichever tree
it is run from, by blocking ``pandas`` at the import machinery and
counting the tools that are still discovered.

Usage::

    python investigate/data-analysis-toolkit-module/verify_optional_dependency.py

Exit code 0 means the agent still boots without ``pandas``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class _Blocker:
    """A meta path finder that refuses to import ``pandas``."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pandas" or fullname.startswith("pandas."):
            raise ImportError(f"pandas is blocked: {fullname}")
        return None


def _stub_the_embedding_index() -> None:
    """Replace the embedding index with a stub.

    The tool *collection* happens before the index is built, and the
    index needs a live embedding model.  The question this script asks
    is whether the collection survives a missing ``pandas`` - so the
    index is stubbed out of the way.
    """
    import llama_index.core.objects as objects
    import llama_index.core.indices.vector_store.base as base

    class _StubIndex:
        @staticmethod
        def from_objects(objects_, index_cls=None):
            return _StubIndex()

        def as_retriever(self, similarity_top_k=8):
            return None

    objects.ObjectIndex = _StubIndex
    base.VectorStoreIndex = _StubIndex


def main() -> int:
    sys.meta_path.insert(0, _Blocker())
    _stub_the_embedding_index()

    # -- the retriever ------------------------------------------------------
    from agent_tool_retriever import build_tool_retriever

    try:
        _, retriever_tools = build_tool_retriever(llm=None)
    except Exception as exc:  # noqa: BLE001 - that is the failure
        print(f"THE RETRIEVER RAISED: {exc!r}")
        return 1
    print(f"retriever tools  : {len(retriever_tools)}")

    # -- the selection menu -------------------------------------------------
    from agent_tool_selection import _discover_tools

    try:
        menu_tools = _discover_tools()
    except Exception as exc:  # noqa: BLE001 - that is the failure
        print(f"THE SELECTION MENU RAISED: {exc!r}")
        return 1
    print(f"selection tools  : {len(menu_tools)}")

    # -- and none of them is a data analysis tool ---------------------------
    analysis = [
        tool.metadata.name
        for tool in menu_tools
        if tool.metadata.name
        in (
            "read_excel_to_df",
            "read_csv_to_df",
            "describe_data",
            "filter_data",
            "aggregate_data",
            "pivot_table",
            "detect_missing_data",
            "correlation_matrix",
            "export_dataframe",
            "get_unique_values",
            "sort_data",
            "compute_statistics",
            "get_dataframe_info",
        )
    ]
    print(f"analysis tools   : {len(analysis)}")

    if analysis:
        print("THE DATA ANALYSIS TOOLS ARE STILL THERE - the guard did not fire")
        return 1

    print()
    print("The agent still boots without pandas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
