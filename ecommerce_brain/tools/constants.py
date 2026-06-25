"""Shared business-logic constants for tool functions.

Centralising these prevents magic-number duplication across action_tools.py,
marketing_tools.py, and any future tools that need the same thresholds.
"""

from __future__ import annotations

# Industry-average ROAS used to estimate revenue impact when resuming a
# paused campaign or projecting budget increases.
ROAS_MULTIPLIER: float = 3.8

# ROAS below this threshold signals an underperforming channel that warrants
# a budget review or campaign pause.
ROAS_UNDERPERFORM_THRESHOLD: float = 2.0
