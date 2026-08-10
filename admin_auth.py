"""Centralized administrator ID parsing and checks."""

import re

# Required administrator IDs that must remain active even if Railway has stale values.
REQUIRED_ADMIN_IDS = frozenset({8003980992, 5913177424})


def parse_admin_ids(raw_value: str | None) -> set[int]:
    """Parse Telegram IDs from comma/space/semicolon-separated configuration text."""
    configured: set[int] = set()
    for token in re.split(r"[,;\s]+", raw_value or ""):
        token = token.strip()
        if token.isdigit():
            configured.add(int(token))
    return configured | set(REQUIRED_ADMIN_IDS)


def is_configured_admin(user_id: int, raw_value: str | None) -> bool:
    """Return whether a Telegram user ID is configured as an administrator."""
    return int(user_id) in parse_admin_ids(raw_value)
