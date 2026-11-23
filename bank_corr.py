import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

prices = pd.read_csv("data/bank_prices_close.csv", index_col="date", parse_dates=True)
corr = prices.pct_change().corr()

plt.figure(figsize=(12, 10))
sns.heatmap(corr, cmap="coolwarm", vmin=-1, vmax=1, annot=True, fmt=".2f", annot_kws={"size": 7})
plt.title("Bank daily return correlations")
plt.savefig("data/bank_corr_heatmap.png", dpi=150, bbox_inches="tight")
