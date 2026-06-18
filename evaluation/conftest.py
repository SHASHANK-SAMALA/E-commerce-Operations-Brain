"""pytest conftest for the evaluation suite.

Loads .env from the project root before any test module is imported so that
all Azure OpenAI credentials are available to the project's settings and to
DeepEval's LLM wrapper.  Must be the first file executed by pytest.
"""

from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path (same pattern as test_agents.py)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv  # noqa: E402  (must come after sys.path tweak)

_env_file = os.path.join(_ROOT, ".env")
load_dotenv(_env_file, override=False)

# Configure DeepEval to use Azure OpenAI — no-op when credentials are absent.
from evaluation.metrics import configure_deepeval_azure  # noqa: E402

configure_deepeval_azure()
