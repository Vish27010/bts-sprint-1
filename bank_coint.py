"""Engle-Granger cointegration test (ADF on the spread) for every pair of bank stocks.

Usage:
    python bank_coint.py                  # all pairs, full sample
    python bank_coint.py --plot 6         # also plot spreads of the 6 best pairs
    python bank_coint.py --data data --out data

Reads (in --data dir):
    bank_prices_close.csv   wide adj close (date x ticker)

Writes (in --out dir):
    coint_results.csv       one row per pair, sorted by raw p-value
    coint_summary.txt       counts, top pairs, correlation-vs-cointegration breakdown
    coint_top_spreads.png   only with --plot N

Method: regress log price of Y on log price of X (OLS), run an ADF test on the
residual spread using statsmodels `coint` (Engle-Granger critical values, which
are stricter than a plain ADF on residuals). EG is asymmetric, so both
directions are run and the lower p-value is kept. Correlations are reported
only; they are not used to filter pairs.
"""
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint

ALPHA = 0.05
CORR_REF = 0.75  # only used to split the summary, not to filter


def half_life(spread: pd.Series) -> float:
    """Mean-reversion half-life in days from AR(1) on the spread; NaN if not mean-reverting."""
    lag = spread.shift(1).iloc[1:]
    delta = spread.diff().iloc[1:]
    b = sm.OLS(delta, sm.add_constant(lag)).fit().params.iloc[1]
    phi = 1 + b
    return float(-np.log(2) / np.log(phi)) if 0 < phi < 1 else np.nan


def test_direction(y: pd.Series, x: pd.Series) -> dict:
    """Engle-Granger with y regressed on x."""
    t_stat, p_val, crit = coint(y, x, trend="c", autolag="aic")
    ols = sm.OLS(y, sm.add_constant(x)).fit()
    alpha, beta = ols.params.iloc[0], ols.params.iloc[1]
    spread = y - beta * x - alpha
    return {
        "eg_tstat": t_stat, "p_value": p_val,
        "crit_1": crit[0], "crit_5": crit[1], "crit_10": crit[2],
        "hedge_ratio": beta, "intercept": alpha,
        "spread_adf_p": adfuller(spread, autolag="AIC")[1],
        "half_life": half_life(spread),
    }


def run_all(logp: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    ret_corr = rets.corr()
    lvl_corr = logp.corr()
    rows = []
    for a, b in combinations(logp.columns, 2):
        res_ab = test_direction(logp[a], logp[b])   # a = y, b = x
        res_ba = test_direction(logp[b], logp[a])   # b = y, a = x
        best, other, (y, x) = (res_ab, res_ba, (a, b)) if res_ab["p_value"] <= res_ba["p_value"] \
            else (res_ba, res_ab, (b, a))
        rows.append({
            "ticker_y": y, "ticker_x": x,
            "return_corr": ret_corr.loc[a, b], "level_corr": lvl_corr.loc[a, b],
            **best, "p_value_other_dir": other["p_value"],
        })
    df = pd.DataFrame(rows).sort_values("p_value").reset_index(drop=True)
    return df


def summarise(df: pd.DataFrame, n_obs: int, span: tuple) -> list[str]:
    n = len(df)
    hi = df["return_corr"] >= CORR_REF
    sig = df["p_value"] < ALPHA
    lines = [
        f"Engle-Granger cointegration, {n} pairs, {n_obs} daily obs ({span[0]} to {span[1]}), log prices",
        "Note: best of two directions is kept per pair, so p-values are slightly optimistic.",
        "",
        f"Significant at {ALPHA:.0%}:",
        f"   {int(sig.sum())} of {n} pairs",
        "",
        f"Return correlation vs cointegration (significant pairs), split at {CORR_REF}:",
        f"   corr >= {CORR_REF}: {int((sig & hi).sum())} of {int(hi.sum())} pairs",
        f"   corr <  {CORR_REF}: {int((sig & ~hi).sum())} of {int((~hi).sum())} pairs",
        "",
        "Top 15 pairs by raw p-value:",
    ]
    cols = ["ticker_y", "ticker_x", "return_corr", "level_corr", "p_value",
            "hedge_ratio", "half_life"]
    lines.extend(df[cols].head(15).to_string(float_format=lambda v: f"{v:.3f}").splitlines())
    return lines


def plot_spreads(df: pd.DataFrame, logp: pd.DataFrame, n: int, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = df.head(n)
    cols = 2
    rows = int(np.ceil(len(top) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(13, 3 * rows), squeeze=False)
    for ax, (_, r) in zip(axes.flat, top.iterrows()):
        s = logp[r.ticker_y] - r.hedge_ratio * logp[r.ticker_x] - r.intercept
        ax.plot(s.index, s.values, lw=0.9)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(f"{r.ticker_y} vs {r.ticker_x}  (p={r.p_value:.3f}, beta={r.hedge_ratio:.2f})", fontsize=9)
    for ax in axes.flat[len(top):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default="data", help="dir containing bank_prices_close.csv")
    p.add_argument("--out", default="data", help="output directory")
    p.add_argument("--plot", type=int, default=0, help="plot spreads of the top N pairs")
    args = p.parse_args()

    prices = pd.read_csv(Path(args.data) / "bank_prices_close.csv", index_col="date", parse_dates=True)
    prices = prices.dropna()  # full sample, common dates only
    logp = np.log(prices)
    rets = prices.pct_change().dropna()

    df = run_all(logp, rets)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "coint_results.csv", index=False)
    report = summarise(df, len(prices), (prices.index[0].date(), prices.index[-1].date()))
    (out / "coint_summary.txt").write_text("\n".join(report) + "\n")
    if args.plot:
        plot_spreads(df, logp, args.plot, out / "coint_top_spreads.png")

    print("\n".join(report))
    print(f"\nSaved to {out.resolve()}")


if __name__ == "__main__":
    main()
