"""Fit an OU model (OLS on AR(1)) to the spreads of the top 10 cointegrated pairs.
Run bank_data.py and bank_coint.py first. Saves data/ou_results.csv and data/ou_spreads.png."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm

DT = 1 / 252

logp = np.log(pd.read_csv("data/bank_prices_close.csv", index_col="date", parse_dates=True).dropna())
pairs = pd.read_csv("data/coint_results.csv").sort_values("p_value").head(10)

rows = []
fig, axes = plt.subplots(5, 2, figsize=(13, 15))
for ax, r in zip(axes.flat, pairs.itertuples()):
    s = logp[r.ticker_y] - r.hedge_ratio * logp[r.ticker_x] - r.intercept
    fit = sm.OLS(s.iloc[1:], sm.add_constant(s.shift(1).iloc[1:])).fit()   # S_t = a + phi*S_{t-1} + e
    a, phi = fit.params
    theta = -np.log(phi) / DT
    mu, sd = a / (1 - phi), np.sqrt(fit.scale / (1 - phi**2))
    rows.append({"pair": f"{r.ticker_y}/{r.ticker_x}", "eg_p": r.p_value, "theta": theta, "mu": mu,
                 "sigma": np.sqrt(fit.scale * 2 * theta / (1 - phi**2)),
                 "half_life_days": np.log(2) / theta * 252, "z_now": (s.iloc[-1] - mu) / sd})
    ax.plot(s, lw=0.8)
    ax.axhline(mu, color="k", lw=0.8)
    for k in (-2, 2):
        ax.axhline(mu + k * sd, color="r", ls="--", lw=0.6)
    ax.set_title(f"{rows[-1]['pair']}  half-life={rows[-1]['half_life_days']:.1f}d", fontsize=9)

fig.tight_layout()
fig.savefig("data/ou_spreads.png", dpi=150)
df = pd.DataFrame(rows)
df.to_csv("data/ou_results.csv", index=False)
print(df.round(4).to_string(index=False))
