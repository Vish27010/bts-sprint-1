"""Download and clean daily price data for banking-sector stocks from Yahoo Finance.

Usage:
    python bank_data.py                       # defaults: 5y of daily data
    python bank_data.py --start 2020-01-01 --end 2025-01-01
    python bank_data.py --tickers JPM BAC C --out data

Outputs (in --out dir):
    bank_prices_clean.csv   long format: date, ticker, open, high, low, close, adj_close, volume, ret, log_ret
    bank_prices_close.csv   wide format of adjusted close (date x ticker)
    bank_info.csv           static snapshot (name, industry, market cap, ...)
    cleaning_report.txt     what was fixed / dropped
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Large US banks + regionals + a few major international banks
DEFAULT_TICKERS = {
    "money_center": ["JPM", "BAC", "C", "WFC"],
    "investment": ["GS", "MS"],
    "regional": ["USB", "PNC", "TFC", "FITB", "KEY", "RF", "HBAN", "MTB", "CFG"],
    "custody": ["BNY", "STT", "NTRS"],
    "intl": ["HSBC", "BCS", "UBS", "TD", "RY"],
}
ALL_TICKERS = [t for group in DEFAULT_TICKERS.values() for t in group]

PRICE_COLS = ["open", "high", "low", "close", "adj_close"]
MAX_FFILL_DAYS = 3        # forward-fill gaps no longer than this
OUTLIER_RET = 0.40        # flag absolute daily returns above 40%


def download(tickers: list[str], start: str | None, end: str | None, period: str) -> pd.DataFrame:
    """Download raw OHLCV; returns long-format frame."""
    kwargs = dict(auto_adjust=False, group_by="ticker", progress=False, threads=True)
    if start:
        raw = yf.download(tickers, start=start, end=end, **kwargs)
    else:
        raw = yf.download(tickers, period=period, **kwargs)
    if raw.empty:
        raise SystemExit("No data returned from Yahoo Finance.")

    if not isinstance(raw.columns, pd.MultiIndex):  # single ticker
        raw.columns = pd.MultiIndex.from_product([tickers[:1], raw.columns])

    frames = []
    for t in raw.columns.get_level_values(0).unique():
        df = raw[t].copy()
        df["ticker"] = t
        frames.append(df)
    long = pd.concat(frames)
    long.index.name = "date"
    long = long.reset_index()
    long.columns = [str(c).lower().replace(" ", "_") for c in long.columns]
    return long[["date", "ticker", *PRICE_COLS, "volume"]]


def clean(long: pd.DataFrame, requested: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Clean the long-format frame. Returns (clean_df, report_lines)."""
    log: list[str] = []
    df = long.copy()

    # Normalise dates (tz-naive, midnight) and types
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    for c in PRICE_COLS + ["volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Duplicates
    n = len(df)
    df = df.drop_duplicates(subset=["date", "ticker"], keep="last")
    log.append(f"Dropped {n - len(df)} duplicate (date, ticker) rows")

    # Rows with no price info at all
    n = len(df)
    df = df.dropna(subset=PRICE_COLS, how="all")
    missing = sorted(set(requested) - set(df["ticker"].unique()))
    if missing:
        log.append(f"WARNING: tickers with no data returned: {missing}")
    log.append(f"Dropped {n - len(df)} rows with all prices missing")

    # Non-positive prices are invalid -> NaN
    bad = (df[PRICE_COLS] <= 0).any(axis=1)
    log.append(f"Set prices to NaN on {int(bad.sum())} rows with non-positive values")
    df.loc[:, PRICE_COLS] = df[PRICE_COLS].where(df[PRICE_COLS] > 0)

    # Negative volume invalid; zero volume on a priced day is kept but counted
    df.loc[df["volume"] < 0, "volume"] = np.nan

    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Per-ticker: limited forward-fill of price gaps
    before = df[PRICE_COLS].isna().sum().sum()
    df[PRICE_COLS] = df.groupby("ticker")[PRICE_COLS].transform(lambda s: s.ffill(limit=MAX_FFILL_DAYS))
    after = df[PRICE_COLS].isna().sum().sum()
    log.append(f"Forward-filled {int(before - after)} missing price cells (limit {MAX_FFILL_DAYS} days)")

    # Drop rows still missing close / adj_close
    n = len(df)
    df = df.dropna(subset=["close", "adj_close"])
    log.append(f"Dropped {n - len(df)} rows still missing close/adj_close")

    # OHLC consistency: repair high/low to bracket open & close
    hi = df[["open", "high", "low", "close"]].max(axis=1)
    lo = df[["open", "high", "low", "close"]].min(axis=1)
    inconsistent = ((df["high"] < hi) | (df["low"] > lo)).sum()
    df["high"], df["low"] = hi, lo
    log.append(f"Repaired high/low on {int(inconsistent)} rows with inconsistent OHLC")

    # Returns from adjusted close
    g = df.groupby("ticker")["adj_close"]
    df["ret"] = g.pct_change()
    df["log_ret"] = np.log(df["adj_close"] / g.shift(1))

    # Flag (don't remove) extreme moves — often real for banks (e.g. March 2020, SVB)
    outliers = df[df["ret"].abs() > OUTLIER_RET]
    log.append(f"{len(outliers)} daily returns exceed ±{OUTLIER_RET:.0%} (kept, review below)")
    for _, r in outliers.iterrows():
        log.append(f"   {r['date'].date()} {r['ticker']}: {r['ret']:+.1%}")

    # Coverage summary
    cov = df.groupby("ticker")["date"].agg(["min", "max", "count"])
    log.append("\nCoverage per ticker:")
    log.extend(cov.to_string().splitlines())

    return df, log


def fetch_info(tickers: list[str]) -> pd.DataFrame:
    """Static snapshot of key fields; tolerant of failures."""
    fields = ["shortName", "sector", "industry", "country", "marketCap",
              "trailingPE", "priceToBook", "dividendYield", "beta", "currency"]
    rows = []
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
        except Exception as e:  # network / rate limit
            print(f"  info failed for {t}: {e}")
            info = {}
        rows.append({"ticker": t, **{f: info.get(f) for f in fields}})
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=ALL_TICKERS)
    p.add_argument("--start", help="YYYY-MM-DD (overrides --period)")
    p.add_argument("--end", help="YYYY-MM-DD")
    p.add_argument("--period", default="5y", help="yfinance period if no --start (default 5y)")
    p.add_argument("--out", default="data", help="output directory")
    p.add_argument("--no-info", action="store_true", help="skip fundamentals snapshot")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(args.tickers)} tickers...")
    raw = download(args.tickers, args.start, args.end, args.period)
    df, report = clean(raw, args.tickers)

    df.to_csv(out / "bank_prices_clean.csv", index=False)
    df.pivot(index="date", columns="ticker", values="adj_close").to_csv(out / "bank_prices_close.csv")
    (out / "cleaning_report.txt").write_text("\n".join(report) + "\n")

    if not args.no_info:
        print("Fetching ticker info...")
        fetch_info(sorted(df["ticker"].unique())).to_csv(out / "bank_info.csv", index=False)

    print("\n".join(report))
    print(f"\nSaved to {out.resolve()}")


if __name__ == "__main__":
    main()
