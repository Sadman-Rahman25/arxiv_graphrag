"""Day 9 Script 2 - Correlation analysis between retrieval and answer quality.

Computes Spearman rank correlations between:
  - Retrieval R@10 vs Faithfulness   (does better retrieval -> more grounded answers?)
  - Retrieval R@10 vs Coverage       (does better retrieval -> more complete answers?)
  - Faithfulness vs Coverage         (do these two quality dimensions agree?)
  - Self-reported confidence vs Faithfulness  (calibration: do high-conf answers score better?)
  - Self-reported confidence vs Coverage      (calibration on the coverage axis)

Computed per-retriever and pooled across all retrievers.

Spearman rho is rank-based and robust to outliers - appropriate for small samples
and the bounded [0,1] judge scores. Reports rho + p-value, flags low-N cells.

Pure analysis - no Groq calls. Reruns as judge cache fills.

Usage:
    python src/correlation_analysis.py
    python src/correlation_analysis.py --plot     # save matplotlib scatter to PNG
"""
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime

logging.getLogger("neo4j").setLevel(logging.ERROR)

from scipy import stats

RESULTS_DIR = Path("eval/results")

CONF_MAP = {"high": 3, "medium": 2, "low": 1, "abstain": 0, None: None}


def load_latest_diagnostic():
    files = sorted(RESULTS_DIR.glob("diagnostic_*.json"))
    if not files:
        return None, None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f), files[-1]


def extract_pairs(diagnostics, x_field, y_field, retriever=None):
    """Return (xs, ys) for valid datapoints (both x and y non-None)."""
    xs, ys = [], []
    for d in diagnostics:
        for ret, dr in d["per_retriever"].items():
            if retriever and ret != retriever:
                continue
            x = dr.get(x_field)
            y = dr.get(y_field)
            if x is None or y is None:
                continue
            xs.append(x)
            ys.append(y)
    return xs, ys


def extract_pairs_conf(diagnostics, y_field, retriever=None):
    """Confidence (mapped to numeric) vs y_field."""
    xs, ys = [], []
    for d in diagnostics:
        for ret, dr in d["per_retriever"].items():
            if retriever and ret != retriever:
                continue
            x = CONF_MAP.get(dr.get("confidence"))
            y = dr.get(y_field)
            if x is None or y is None:
                continue
            xs.append(x)
            ys.append(y)
    return xs, ys


def fmt_corr(xs, ys, min_n=10):
    """Compute Spearman and format. Flags low-N and zero-variance."""
    n = len(xs)
    if n < 2:
        return f"N={n:>3}   -                     (insufficient)"
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return f"N={n:>3}   rho=NaN               (no variance)"
    rho, p = stats.spearmanr(xs, ys)
    if rho != rho:  # NaN guard
        return f"N={n:>3}   rho=NaN               (degenerate)"
    warn = "  (low-N)" if n < min_n else ""
    return f"N={n:>3}   rho={rho:>+6.3f}  p={p:.3f}{warn}"


def make_plot(diagnostics, out_path):
    """Optional scatter plot of R@10 vs Faithfulness, R@10 vs Coverage."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = {"vector": "tab:blue", "graph": "tab:orange", "dual": "tab:green"}

    for ax, y_field, ylabel in [
        (axes[0], "faithfulness", "Faithfulness"),
        (axes[1], "coverage", "Coverage"),
    ]:
        for ret in ("vector", "graph", "dual"):
            xs, ys = extract_pairs(diagnostics, "recall_at_10", y_field, retriever=ret)
            if xs:
                ax.scatter(xs, ys, label=f"{ret} (n={len(xs)})",
                           color=colors[ret], alpha=0.7, s=60)
        ax.set_xlabel("Retrieval Recall@10")
        ax.set_ylabel(ylabel)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left")
        ax.set_title(f"R@10 vs {ylabel}")

    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    print(f"  Saved scatter plot: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot", action="store_true",
                        help="Save scatter plot PNG (needs matplotlib)")
    args = parser.parse_args()

    data, src = load_latest_diagnostic()
    if not data:
        print("No diagnostic JSON found. Run src/diagnostic_report.py first.")
        return

    print(f"Source:          {src}")
    print(f"Judge model:     {data.get('judge_model')}")
    print(f"Retrieval eval:  {data.get('retrieval_eval_source')}\n")

    diagnostics = data["diagnostics"]

    pairs = [
        ("R@10 vs Faithfulness",       "recall_at_10",  "faithfulness", False),
        ("R@10 vs Coverage",           "recall_at_10",  "coverage",     False),
        ("Faithfulness vs Coverage",   "faithfulness",  "coverage",     False),
        ("Confidence vs Faithfulness", None,            "faithfulness", True),
        ("Confidence vs Coverage",     None,            "coverage",     True),
    ]

    print("=" * 84)
    print("SPEARMAN CORRELATIONS")
    print("=" * 84)
    print(f"  {'Pair':<28}  {'Retriever':<8}  {'Result'}")
    print(f"  {'-'*28}  {'-'*8}  {'-'*44}")

    all_results = []
    for label, xf, yf, use_conf in pairs:
        for ret in ("vector", "graph", "dual", "pooled"):
            sel = None if ret == "pooled" else ret
            if use_conf:
                xs, ys = extract_pairs_conf(diagnostics, yf, retriever=sel)
            else:
                xs, ys = extract_pairs(diagnostics, xf, yf, retriever=sel)
            line = fmt_corr(xs, ys)
            print(f"  {label:<28}  {ret:<8}  {line}")

            n = len(xs)
            if n >= 2 and len(set(xs)) >= 2 and len(set(ys)) >= 2:
                rho, p = stats.spearmanr(xs, ys)
                if rho == rho:
                    all_results.append({
                        "pair": label, "retriever": ret,
                        "n": n, "rho": rho, "p": p,
                    })
        print()  # blank line between pairs

    if args.plot:
        ts_p = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_path = RESULTS_DIR / f"correlations_{ts_p}.png"
        try:
            make_plot(diagnostics, plot_path)
        except ImportError:
            print("\n  matplotlib not installed. pip install matplotlib")
        except Exception as e:
            print(f"\n  Plot failed: {e}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"correlations_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "diagnostic_source": str(src),
            "correlations": all_results,
        }, f, indent=2)
    print(f"Saved: {out_file}")

    print("\nInterpretation:")
    print("  |rho| < 0.3   weak     |  0.3-0.5  moderate")
    print("  0.5-0.7      strong    |  > 0.7    very strong")
    print("  p < 0.05     significant (with N>=10)")
    print("  'no variance' = all values identical in one dimension (common for graph faith/cov when all-zero)")
    print("\nN<10 cells are reported but not interpretable.")
    print("Rerun after each retriever's eval completes for stronger statistics.")


if __name__ == "__main__":
    main()
    