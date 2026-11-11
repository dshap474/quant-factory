"""Measure how much a winner picked from a grid of return series is inflated by the pick.

Returns-only selection statistics (SPEC §7 increment 5) over a ``T × N`` array of aligned
per-period returns (rows = dates, oldest first; columns = configurations). Inputs must be
finite; the caller drops or zero-fills missing dates. Every operation returns a plain dict.
When the inputs cannot support a statistic (too few rows, fewer than two columns, zero
variance) the dict is ``{"available": False, "reason": ...}`` instead of a degenerate number.

- ``probabilistic_sharpe``: Bailey & López de Prado PSR of one series.
- ``effective_trials``: eigenvalue participation ratio of the column correlation matrix.
- ``deflated_sharpe``: PSR of the selected column against the expected maximum Sharpe of N trials.
- ``pbo_cscv``: probability of backtest overfitting by combinatorially symmetric cross-validation.
- ``reality_check``: White reality check and Hansen-style studentized max-t, paired with a base.
- ``holm``: Holm step-down adjusted p-values.
- ``rademacher_bound``: Paleologo ch. 8 Rademacher Anti-Serum bound: Procedure 8.2 on
  standardized returns (default), or Procedure 8.1 on cosine ICs (``metric="ic"``).

These measure selection inflation; they do not remove it, select, or promote anything. Apart
from ``rademacher_bound(metric="ic")``, IC and ICIR are not supported: DSR and the reality check
here are defined for returns only.

USAGE:

    from signal_analysis.selection import (deflated_sharpe, effective_trials, pbo_cscv,
                                           probabilistic_sharpe, rademacher_bound, reality_check)

    psr = probabilistic_sharpe(returns[:, k])
    n_eff = effective_trials(returns)["effective_trials"]
    dsr = deflated_sharpe(returns, k, trials=n_eff)
    pbo = pbo_cscv(returns, blocks=16)
    rc = reality_check(returns[:, family], np.repeat(returns[:, [control]], len(family), axis=1),
                       statistic="sharpe", block=28, draws=2000, seed=7)
    ras = rademacher_bound(returns[:, family], block=7, draws=2000, seed=7)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import math
from collections.abc import Sequence
from itertools import combinations
from typing import Any, Literal

import numpy as np
from scipy.stats import norm

Statistic = Literal["sharpe", "sortino", "mean"]
_EULER_GAMMA = 0.5772156649015329
_TINY = 1e-12


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _matrix(returns_2d: Any, label: str = "returns_2d") -> np.ndarray:
    x = np.asarray(returns_2d, dtype=np.float64)
    if x.ndim != 2:
        raise ValueError(f"{label} must be a T x N array")
    if not np.isfinite(x).all():
        raise ValueError(f"{label} must be finite; drop or zero-fill missing dates before calling")
    return x


def _names(names: Sequence[str] | None, n: int) -> list[str]:
    if names is None:
        return [str(i) for i in range(n)]
    out = [str(name) for name in names]
    if len(out) != n or len(set(out)) != n:
        raise ValueError("names must be unique and match the column count")
    return out


def _moments(x: np.ndarray) -> tuple[float, float, float]:
    """Per-period Sharpe, skewness and raw (non-excess) kurtosis with population moments."""
    sd = float(np.std(x))
    z = (x - np.mean(x)) / sd
    return float(np.mean(x) / sd), float(np.mean(z**3)), float(np.mean(z**4))


# --------------------------------------------------------------------------- #
# Probabilistic and deflated Sharpe
# --------------------------------------------------------------------------- #


def probabilistic_sharpe(returns_1d: Any, *, benchmark_sharpe: float = 0.0) -> dict[str, Any]:
    """Bailey & López de Prado PSR: P(true per-period Sharpe > ``benchmark_sharpe``).

    ``Z[(SR − SR*)·√(T−1) / √(1 − γ3·SR + (γ4−1)/4·SR²)]`` with per-period SR, skewness γ3 and
    raw kurtosis γ4 (population moments).
    """
    x = np.asarray(returns_1d, dtype=np.float64)
    if x.ndim != 1 or not np.isfinite(x).all():
        raise ValueError("returns_1d must be a finite one-dimensional array")
    if not math.isfinite(benchmark_sharpe):
        raise ValueError("benchmark_sharpe must be finite")
    if x.size < 3:
        return _unavailable(f"needs at least 3 observations, got {x.size}")
    if float(np.std(x)) <= _TINY:
        return _unavailable("zero return variance")
    sharpe, skew, kurtosis = _moments(x)
    denominator = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if denominator <= _TINY:
        return _unavailable("nonpositive PSR variance term")
    z = (sharpe - benchmark_sharpe) * math.sqrt(x.size - 1) / math.sqrt(denominator)
    return {
        "available": True,
        "psr": float(norm.cdf(z)),
        "z": float(z),
        "sharpe": sharpe,
        "benchmark_sharpe": float(benchmark_sharpe),
        "skew": skew,
        "kurtosis": kurtosis,
        "observations": int(x.size),
    }


def _expected_max_sharpe(variance: float, trials: float) -> float:
    """Expected maximum of ``trials`` Sharpe estimates with cross-trial variance ``variance``."""
    return math.sqrt(variance) * (
        (1.0 - _EULER_GAMMA) * float(norm.ppf(1.0 - 1.0 / trials))
        + _EULER_GAMMA * float(norm.ppf(1.0 - 1.0 / (trials * math.e)))
    )


def effective_trials(returns_2d: Any) -> dict[str, Any]:
    """Participation ratio ``(Σλ)² / Σλ²`` of the column correlation matrix, in [1, N].

    Identity correlation gives N; perfectly correlated columns give 1. A dependence summary
    for DSR's trial count, not an estimate of independent hypotheses.
    """
    x = _matrix(returns_2d)
    t, n = x.shape
    if n < 2:
        return _unavailable(f"needs at least 2 columns, got {n}")
    if t < 3:
        return _unavailable(f"needs at least 3 rows, got {t}")
    if (x.std(axis=0) <= _TINY).any():
        return _unavailable("a column has zero return variance")
    eigenvalues = np.clip(np.linalg.eigvalsh(np.corrcoef(x, rowvar=False)), 0.0, None)
    ratio = float(eigenvalues.sum() ** 2 / (eigenvalues**2).sum())
    return {"available": True, "effective_trials": float(min(max(ratio, 1.0), n)), "columns": n}


def deflated_sharpe(returns_2d: Any, selected: int, *, trials: float | None = None) -> dict[str, Any]:
    """PSR of column ``selected`` against the expected maximum Sharpe of ``trials`` draws.

    ``SR* = √V[SR_n] · ((1−γ)·Z⁻¹[1−1/N] + γ·Z⁻¹[1−1/(N·e)])``, γ = Euler–Mascheroni, V[SR_n]
    the sample variance (ddof=1) of the per-period Sharpe across this grid's columns, and
    N = ``trials`` (default: the column count). √V is the cross-trial dispersion,
    following Bailey & López de Prado (2014), not the selected series' own Sharpe
    standard error.
    """
    x = _matrix(returns_2d)
    t, n = x.shape
    if not 0 <= selected < n:
        raise ValueError("selected must index a column")
    count = float(n if trials is None else trials)
    if not math.isfinite(count):
        raise ValueError("trials must be finite")
    if n < 2:
        return _unavailable(f"needs at least 2 columns, got {n}")
    if count <= 1.0:
        return _unavailable(f"needs more than one trial, got {count:g}")
    if t < 3:
        return _unavailable(f"needs at least 3 rows, got {t}")
    sd = x.std(axis=0)
    if (sd <= _TINY).any():
        return _unavailable("a column has zero return variance")
    sharpes = x.mean(axis=0) / sd
    variance = float(np.var(sharpes, ddof=1))
    sr_star = _expected_max_sharpe(variance, count)
    psr = probabilistic_sharpe(x[:, selected], benchmark_sharpe=sr_star)
    if not psr["available"]:
        return psr
    return {
        "available": True,
        "dsr": psr["psr"],
        "sr_star": sr_star,
        "n_trials": count,
        "columns": n,
        "trial_sharpe_variance": variance,
        "selected": int(selected),
        "selected_sharpe": psr["sharpe"],
        "skew": psr["skew"],
        "kurtosis": psr["kurtosis"],
        "observations": t,
    }


# --------------------------------------------------------------------------- #
# Combinatorially symmetric cross-validation
# --------------------------------------------------------------------------- #


def pbo_cscv(returns_2d: Any, *, blocks: int = 16) -> dict[str, Any]:
    """Bailey et al. probability of backtest overfitting by CSCV.

    T is trimmed to a multiple of ``blocks`` by dropping the oldest rows. For each of the
    C(S, S/2) in-sample halves, the in-sample per-period Sharpe winner's out-of-sample
    relative rank ω = rank/(N+1) (ties averaged) gives λ = ln(ω/(1−ω)); PBO = share(λ ≤ 0).
    """
    x = _matrix(returns_2d)
    t, n = x.shape
    if blocks < 2 or blocks % 2:
        raise ValueError("blocks must be an even integer of at least 2")
    if n < 2:
        return _unavailable(f"needs at least 2 columns, got {n}")
    size = t // blocks
    if size < 2:
        return _unavailable(f"needs at least {2 * blocks} rows for {blocks} blocks, got {t}")
    dropped = t - size * blocks
    chunks = x[dropped:].reshape(blocks, size, n)
    sums, squares = chunks.sum(axis=1), (chunks**2).sum(axis=1)
    halves = np.array(list(combinations(range(blocks), blocks // 2)))
    membership = np.zeros((len(halves), blocks))
    membership[np.arange(len(halves))[:, None], halves] = 1.0
    rows = size * blocks // 2

    def sharpe(mask: np.ndarray) -> np.ndarray:
        mean = mask @ sums / rows
        return mean / np.sqrt(np.maximum(mask @ squares / rows - mean**2, 0.0))

    with np.errstate(divide="ignore", invalid="ignore"):
        in_sample, out_of_sample = sharpe(membership), sharpe(1.0 - membership)
    if not (np.isfinite(in_sample).all() and np.isfinite(out_of_sample).all()):
        return _unavailable("a column has zero return variance in some half")
    winner = in_sample.argmax(axis=1)
    chosen = out_of_sample[np.arange(len(halves)), winner][:, None]
    rank = (out_of_sample < chosen).sum(axis=1) + ((out_of_sample == chosen).sum(axis=1) + 1) / 2.0
    omega = rank / (n + 1)
    logits = np.log(omega / (1.0 - omega))
    return {
        "available": True,
        "pbo": float((logits <= 0).mean()),
        "median_logit": float(np.median(logits)),
        "splits": len(halves),
        "blocks": blocks,
        "block_rows": size,
        "dropped_rows": dropped,
        "columns": n,
    }


# --------------------------------------------------------------------------- #
# Reality check and multiple testing
# --------------------------------------------------------------------------- #


def circular_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """One circular block bootstrap draw of ``n`` row indices with blocks of length ``block``."""
    starts = rng.integers(0, n, size=-(-n // block))
    return ((starts[:, None] + np.arange(block)).ravel()[:n]) % n


def _statistic(x: np.ndarray, statistic: Statistic, periods_per_year: float) -> np.ndarray:
    mean = x.mean(axis=0)
    if statistic == "mean":
        return mean * periods_per_year
    if statistic == "sharpe":
        scale = x.std(axis=0)
    else:
        downside = np.minimum(x, 0)
        scale = np.sqrt((downside * downside).mean(axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        return mean / scale * math.sqrt(periods_per_year)


def holm(pvalues: Any) -> np.ndarray:
    """Holm step-down adjusted p-values in input order."""
    p = np.asarray(pvalues, dtype=np.float64)
    order = np.argsort(p, kind="stable")
    m = len(p)
    adjusted = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adjusted[i] = running
    return adjusted


def reality_check(
    candidates_2d: Any,
    bases_2d: Any,
    *,
    statistic: Statistic = "sharpe",
    block: int = 28,
    draws: int = 2000,
    seed: int = 7,
    periods_per_year: float = 365,
    names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """White reality check and Hansen-style studentized reality check, paired by column.

    Column k of ``bases_2d`` is candidate k's base (repeat one control for a single base).
    Every draw resamples the same circular-block row indices for all columns. Deltas
    ``d̂ = f(cand) − f(base)``, bootstrap deltas ``B``, ``se = B.std(ddof=1)``, ``t = d̂/se``:
    raw p = P(max(B − d̂) ≥ max d̂); studentized p = P(max((B − d̂)/se) ≥ max t); per-candidate
    one-sided p_k = P(B_k − d̂_k ≥ d̂_k), Holm-adjusted. Sharpe and Sortino are annualized by
    √periods_per_year; the mean by periods_per_year. Sortino uses
    ``mean / sqrt(mean(min(x, 0)²))``; Sharpe the population standard deviation.
    """
    candidates, bases = _matrix(candidates_2d, "candidates_2d"), _matrix(bases_2d, "bases_2d")
    if candidates.shape != bases.shape:
        raise ValueError("candidates_2d and bases_2d must share one shape")
    if statistic not in ("sharpe", "sortino", "mean"):
        raise ValueError("statistic must be 'sharpe', 'sortino', or 'mean'")
    if block < 1 or draws < 2 or periods_per_year <= 0:
        raise ValueError("block must be positive, draws at least 2, periods_per_year positive")
    t, n = candidates.shape
    labels = _names(names, n)
    settings = dict(
        statistic=statistic,
        block=block,
        draws=draws,
        seed=seed,
        periods_per_year=periods_per_year,
        bootstrap="circular block, identical row draws for every column",
    )
    if n < 1 or t < 2 * block:
        return _unavailable(f"needs at least one candidate and {2 * block} rows, got {n} and {t}") | settings
    observed = _statistic(candidates, statistic, periods_per_year) - _statistic(bases, statistic, periods_per_year)
    if not np.isfinite(observed).all():
        return _unavailable(f"{statistic} undefined on the full sample for some column") | settings
    rng = np.random.default_rng(seed)
    boot = np.empty((draws, n))
    for j in range(draws):
        index = circular_block_indices(t, block, rng)
        boot[j] = _statistic(candidates[index], statistic, periods_per_year) - _statistic(
            bases[index], statistic, periods_per_year
        )
    if not np.isfinite(boot).all():
        return _unavailable(f"{statistic} undefined in some bootstrap draw") | settings
    se = boot.std(axis=0, ddof=1)
    if (se <= 0).any():
        return _unavailable("zero bootstrap standard error for some candidate") | settings
    centered = boot - observed
    tstat = observed / se
    raw_p = float((centered.max(axis=1) >= observed.max()).mean())
    studentized_p = float(((centered / se).max(axis=1) >= tstat.max()).mean())
    pvalues = (centered >= observed).mean(axis=0)
    adjusted = holm(pvalues)
    best = int(np.argmax(tstat))
    return {
        "available": True,
        **settings,
        "observations": t,
        "candidates": n,
        "raw_p": raw_p,
        "studentized_p": studentized_p,
        "max_delta": float(observed.max()),
        "argmax_t": labels[best],
        "t_max": float(tstat[best]),
        "se_median": float(np.median(se)),
        "holm_survivors": int((adjusted < 0.05).sum()),
        "per_candidate": [
            {"name": name, "delta": float(d), "se": float(s), "t": float(z), "p": float(p), "holm_p": float(h)}
            for name, d, s, z, p, h in zip(labels, observed, se, tstat, pvalues, adjusted, strict=True)
        ],
    }


# --------------------------------------------------------------------------- #
# Rademacher Anti-Serum
# --------------------------------------------------------------------------- #


def rademacher_bound(
    returns_2d: Any,
    *,
    block: int = 7,
    draws: int = 2000,
    seed: int = 7,
    delta: float = 0.05,
    periods_per_year: float = 365,
    selected: int | None = None,
    standardize: bool = True,
    names: Sequence[str] | None = None,
    metric: str = "sharpe",
) -> dict[str, Any]:
    """Paleologo, *Elements of Quantitative Investing* ch. 8 Rademacher Anti-Serum lower bound.

    This is the published bound, not a sign-flip max-statistic hypothesis test. Rows are
    averaged over non-overlapping blocks of ``block`` (incomplete tail dropped; §8.3.1);
    R̂ = E_ε[max_n ε·x_n/T] with T the block count. ``metric`` picks the book's result:

    - ``"sharpe"`` (Procedure 8.2, eq. 8.3, Theorem 8.4: sub-Gaussian x with unit proxy):
      bound_n = θ_n − 2R̂ − 3√(2 ln(2/δ)/T) − √(2 ln(2N/δ)/T). The book's x is each
      return z-scored by its predicted volatility; a returns-only grid has none, so
      ``standardize=True`` divides each column by its full-sample standard deviation as the
      stand-in (θ is then a per-period Sharpe). Pass ``standardize=False`` for returns
      already z-scored by predicted volatility.
    - ``"ic"`` (Procedure 8.1 as printed; Theorem 8.3's a = 1 assumption): bound_n = θ_n − 2R̂
      − 2√(ln(2/δ)/T) on cosine ICs, which must satisfy |x| ≤ 1; never standardized. (Theorem 8.3
      itself, eq. 8.8, gives the looser 3√(2 ln(2/δ)/T).)

    For ``"sharpe"`` block means keep per-period units, so the annualized values multiply by
    √periods_per_year; ICs are not annualized.
    """
    if metric not in ("sharpe", "ic"):
        raise ValueError("metric must be 'sharpe' or 'ic'")
    x = _matrix(returns_2d)
    t0, n = x.shape
    labels = _names(names, n)
    if block < 1 or draws < 1 or not 0 < delta < 1:
        raise ValueError("block and draws must be positive and delta in (0, 1)")
    if selected is not None and not 0 <= selected < n:
        raise ValueError("selected must index a column")
    if n < 2:
        return _unavailable(f"needs at least 2 columns, got {n}")
    if t0 // block < 2:
        return _unavailable(f"needs at least 2 complete blocks of {block}, got {t0} rows")
    if metric == "ic" and (np.abs(x) > 1).any():
        return _unavailable("an IC exceeds 1 in absolute value (Theorem 8.3 needs |x| <= 1)")
    standardize = standardize and metric == "sharpe"
    if standardize:
        sd = x.std(axis=0)
        if (sd <= _TINY).any():
            return _unavailable("a column has zero return variance")
        x = x / sd
    if block > 1:
        t = len(x) // block
        x = x[: t * block].reshape(t, block, -1).mean(axis=1)
    t = len(x)
    eps = np.random.default_rng(seed).integers(0, 2, size=(draws, t)) * 2.0 - 1.0
    r_hat = float(np.mean(np.max(eps @ x / t, axis=1)))
    theta = x.mean(axis=0)
    if metric == "sharpe":
        rule = "procedure_8_2"
        estimation = 3 * math.sqrt(2 * math.log(2 / delta) / t) + math.sqrt(2 * math.log(2 * n / delta) / t)
        annualize = math.sqrt(periods_per_year)
    else:
        rule = "procedure_8_1"
        estimation = 2 * math.sqrt(math.log(2 / delta) / t)
        annualize = 1.0

    def bounds(k: int) -> dict[str, Any]:
        bound = float(theta[k] - 2 * r_hat - estimation)
        return {
            "name": labels[k],
            "theta": float(theta[k]),
            "bound": bound,
            "theta_annualized": float(theta[k]) * annualize,
            "bound_annualized": bound * annualize,
            "rademacher_positive": bool(theta[k] - 2 * r_hat > 0),  # eq. 8.6
        }

    return {
        "available": True,
        "metric": metric,
        "rule": rule,
        "estimation_error": estimation,
        "standardized": standardize,
        "block": block,
        "blocks": t,
        "dropped_rows": t0 - t * block,
        "draws": draws,
        "seed": seed,
        "delta": delta,
        "periods_per_year": periods_per_year,
        "columns": n,
        "r_hat": r_hat,
        "best": bounds(int(np.argmax(theta))),
        "selected": bounds(selected) if selected is not None else None,
    }
