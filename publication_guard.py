"""Fail closed before publishing forecasts to live Metaculus tournaments.

This is an activation guard, not proof that API credentials, tournament access,
model availability, or the submitted forecasts are valid.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

LIVE_MODES = frozenset({"tournament", "metaculus_cup"})
ACTIVATION_ENV = "FUTUREEVAL_LIVE_ENABLED"


def require_publication_authorization(
    run_mode: str,
    will_publish: bool,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Reject unapproved live publication; allow dry runs and sandbox tests.

    Only the literal value 'true' authorizes live publishing.
    Never print environment values (especially credentials).
    """
    if run_mode not in LIVE_MODES | {"test_questions"}:
        raise ValueError(f"Unknown forecast mode: {run_mode}")

    if not will_publish or run_mode == "test_questions":
        return

    env = os.environ if environment is None else environment
    if env.get(ACTIVATION_ENV) != "true":
        raise RuntimeError(
            "Live Metaculus publishing blocked: repository variable "
            "FUTUREEVAL_LIVE_ENABLED must be explicitly set to 'true'. "
            "First validate the bot in bot-testing-area on the intended "
            "commit and confirm submissions from the bot account."
        )
