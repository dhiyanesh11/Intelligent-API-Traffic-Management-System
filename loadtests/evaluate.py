"""Summarize Locust *_stats.csv exports for static vs adaptive comparisons."""
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument("--static", required=True, help="Locust stats CSV for static limits")
parser.add_argument("--adaptive", required=True, help="Locust stats CSV for adaptive limits")
parser.add_argument("--out", default="evaluation")
args = parser.parse_args()
frames = []
for mode, path in [("Static", args.static), ("Adaptive", args.adaptive)]:
    df = pd.read_csv(path)
    total = df[df["Name"] == "Aggregated"].iloc[0]
    frames.append({"mode": mode, "requests": int(total["Request Count"]), "failures": int(total["Failure Count"]), "RPS": float(total["Requests/s"]), "p95_ms": float(total["95%"]), "median_ms": float(total["Median Response Time"])})
summary = pd.DataFrame(frames)
Path(args.out).mkdir(parents=True, exist_ok=True)
summary.to_csv(Path(args.out) / "comparison.csv", index=False)
ax = summary.set_index("mode")[["RPS", "p95_ms"]].plot(kind="bar", subplots=True, layout=(1, 2), legend=False, figsize=(9, 4), color=["#93d64c"])
plt.tight_layout()
plt.savefig(Path(args.out) / "comparison.png", dpi=160)
print(summary.to_markdown(index=False))
