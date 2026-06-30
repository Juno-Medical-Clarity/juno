"""utils/env.py — Centralized environment-variable accessor.

Usage:
    from utils.env import get_env
    from utils.constants import Constants

    project_id = get_env(Constants.EnvVars.GCP_PROJECT_ID)
    bucket     = get_env(Constants.EnvVars.GCS_BUCKET, required=True)

Why:
    - Single patch point for test mocking (mock utils.env.get_env).
    - Explicit required=True raises at startup with a clear message
      instead of silently passing None into downstream code.
"""

import os
from typing import Optional


def get_env(key: str, default: Optional[str] = None, *, required: bool = False) -> Optional[str]:
    """Return os.environ.get(key, default).

    Args:
        key: Environment variable name (use Constants.EnvVars.* for all names).
        default: Value to return when the variable is absent. Ignored when
            required=True.
        required: If True and the variable is absent or empty, raise
            EnvironmentError with a descriptive message.

    Returns:
        The variable value as a string, or default if absent (and not required).

    Raises:
        EnvironmentError: When required=True and the variable is absent or empty.
    """
    value = os.environ.get(key)
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Set it before starting the server."
        )
    return value if value is not None else default
