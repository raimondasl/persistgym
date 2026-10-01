"""pytest plugin that turns python-dotenv into a no-op for the upstream harness tests.

The upstream conftest and live tests call ``load_dotenv()`` with no path. That
walks up parent directories and could load a real ``.env`` (for example the
researcher's, at the repository root). apply_patches.py loads this plugin with
``-p no_dotenv_plugin`` so that tests only ever see the sanitized environment.
"""

from __future__ import annotations

from typing import Any

import dotenv
import dotenv.main


def _load_dotenv_disabled(*_args: Any, **_kwargs: Any) -> bool:
    return False


dotenv.load_dotenv = _load_dotenv_disabled
dotenv.main.load_dotenv = _load_dotenv_disabled
