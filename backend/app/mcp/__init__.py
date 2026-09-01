"""Our custom Chicago-parking MCP server.

This is a standalone MCP server (spoken to over stdio, real JSON-RPC). It exposes
a small, fixed PARKING TOOLBOX to the agent -- not arbitrary HTTP, filesystem, or
code execution. Each tool wraps one authoritative City of Chicago dataset and
returns typed, normalized evidence.
"""
