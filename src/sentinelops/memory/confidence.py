"""Confidence scoring — the core differentiator of SentinelOps.

Implements a Beta-Binomial posterior with time-decay to produce a
Lower Confidence Bound (LCB) that:
  - Cold-starts distrustfully (LCB ≈ 0.196 with no history)
  - Punishes thin evidence (1/1 is NOT more confident than 18/20)
  - Rises provably with consistent success
  - Decays old outcomes so stale patterns don't over-inflate trust
"""

from __future__ import annotations

import math
from typing import List, Tuple

# --- Constants ---
HALF_LIFE_DAYS: float = 90.0
PRIOR_A: float = 2.0  # Beta prior alpha
PRIOR_B: float = 2.0  # Beta prior beta
LCB_PERCENTILE: float = 0.10  # 10th percentile = lower confidence bound


from scipy.stats import beta

def _beta_ppf(q: float, a: float, b: float) -> float:
    """Percent Point Function (inverse of CDF) of the Beta distribution using SciPy."""
    return float(beta.ppf(q, a, b))


def _decayed_counts(outcomes: List[Tuple[bool, float]]) -> Tuple[float, float]:
    """Compute decayed alpha/beta counts from a list of outcomes.

    Args:
        outcomes: list of (success: bool, days_ago: float).
            Each tuple represents one fix attempt.

    Returns:
        (alpha, beta) — accumulated decayed counts on top of the prior.
    """
    a, b = PRIOR_A, PRIOR_B
    for success, days_ago in outcomes:
        w = math.exp(-math.log(2) / HALF_LIFE_DAYS * days_ago)
        if success:
            a += w
        else:
            b += w
    return a, b


def fix_lcb(outcomes: List[Tuple[bool, float]]) -> float:
    """Lower Confidence Bound of fix success rate from historical outcomes.

    This is the 10th percentile of the Beta posterior after applying
    time-decay to each outcome observation.

    Args:
        outcomes: list of (success, days_ago) tuples.

    Returns:
        LCB ∈ [0, 1].
    """
    a, b = _decayed_counts(outcomes)
    return _beta_ppf(LCB_PERCENTILE, a, b)


def action_confidence(p_diagnosis: float, outcomes: List[Tuple[bool, float]]) -> float:
    """Combined confidence = P(diagnosis right) × P(action fixes it | history).

    The second term uses the 10th-percentile (LCB) of the decayed Beta
    posterior — thin evidence is punished automatically.

    Args:
        p_diagnosis: probability the diagnosis is correct (from investigation agent).
        outcomes: list of (success, days_ago) tuples from past fix attempts.

    Returns:
        Combined confidence ∈ [0, 1].
    """
    p_fix_lcb = fix_lcb(outcomes)
    return p_diagnosis * p_fix_lcb


def decay_weight(days_ago: float) -> float:
    """Compute the decay weight for an outcome that occurred days_ago days ago.

    Uses exponential decay with a configurable half-life (90 days default).

    Returns:
        Weight ∈ (0, 1].
    """
    return math.exp(-math.log(2) / HALF_LIFE_DAYS * days_ago)
