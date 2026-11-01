"""Planning agent (propose-only). See docs/agent.md.

It reads counts and enums through a fixed allowlist of read-only tools and returns a ranked list of suggested next
steps with links to the pages where a human acts. It cannot send, approve, execute or change anything: this package
imports no executor, no approval-creation and no mail code (tests/test_agent.py enforces that).
"""
