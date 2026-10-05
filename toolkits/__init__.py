"""
Toolkits package - Reusable domain-specific toolkit modules.

This package contains self-contained Python modules that can be used both:
1. As standalone libraries by other application modules
2. Through optional LlamaIndex FunctionAgent adapters

Each toolkit package should have its own agent adapter at the project root
(e.g., agent_ssh_toolkit.py) that depends on LlamaIndex.
"""
