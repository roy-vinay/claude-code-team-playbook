"""A small claims registry for parallel coding agents.

Before an agent edits code, it claims what it will touch. Claims that overlap
another ticket's claim, or code owned by someone else, are routed to that
owner instead of being silently built twice.
"""

__version__ = "0.1.0"
