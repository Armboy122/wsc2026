"""Project-wide pytest safety configuration."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


# Production file-backed state requires an operator-managed durable key. Tests use
# an in-memory app database and one ephemeral key so imports of app.main cannot
# modify or depend on a developer's persistent state.
os.environ["DB_PATH"] = ":memory:"
os.environ["PEA_STATE_KEY"] = Fernet.generate_key().decode("ascii")
