# BTS Sprint 1

Shared repo for Sprint 1. Everyone's doing a different sector. This repo is for code only, data goes on Teams.

## Where the data goes

**Keep all your data in a folder called `data`.** Put everything in there (CSVs, outputs, reports, whatever). The `.gitignore` ignores that folder, so none of it gets pushed to GitHub.

Don't rename it or the data will show up in git. Before you commit, run `git status` to check no data files are listed.

## Files

- `bank_data.py` - downloads and cleans banking sector data from Yahoo Finance
- `bank_corr.py` - plots a daily-return correlation heatmap of the banking tickers
- `bank_coint.py` - Engle-Granger cointegration test (ADF on the spread) for every pair of banks; correlation is reported, not used as a filter
- `.gitignore` - ignores `data/` and `__pycache__/`

If you're doing another sector, make your own script named after it (e.g. `energy_data.py`).

## Setup

```bash
git clone https://github.com/Vish27010/bts-sprint-1.git
cd bts-sprint-1
pip install yfinance pandas numpy statsmodels seaborn matplotlib
```

## The banking script

```bash
python3 bank_data.py                                    # last 5 years of daily data
python3 bank_data.py --start 2018-01-01 --end 2025-01-01
python3 bank_data.py --tickers JPM BAC C --no-info      # your own tickers, skip fundamentals
```

It saves to `data/` by default:

- `bank_prices_clean.csv` - one row per date and ticker (OHLC, adj close, volume, returns)
- `bank_prices_close.csv` - adj close, one column per ticker
- `bank_info.csv` - market cap, P/E, P/B, beta, etc.
- `cleaning_report.txt` - what got fixed or dropped

Default tickers: JPM, BAC, C, WFC, GS, MS, USB, PNC, TFC, FITB, KEY, RF, HBAN, MTB, CFG, BNY, STT, NTRS, HSBC, BCS, UBS, TD, RY. (BNY Mellon is `BNY` now, not `BK`.)

Cleaning: drops duplicates and empty rows, fills gaps of up to 3 days, fixes bad high/low values, and adds returns. Moves over 40% in a day get flagged in the report but kept.


## The cointegration script

```bash
python3 bank_coint.py            # all pairs, full sample
python3 bank_coint.py --plot 6   # also plot spreads of the 6 best pairs
```

Run `bank_data.py` first. It saves `coint_results.csv` and `coint_summary.txt` to `data/` (plus `coint_top_spreads.png` with `--plot`).
