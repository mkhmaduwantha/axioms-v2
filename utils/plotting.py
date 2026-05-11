import os
import sys
import logging
import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker

# config.py sits one level up — add project root to path if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import REPLENISHMENT_PATTERN

_log = logging.getLogger("axioms.plot")

_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

_PHASE_COLORS = {
    "moderate": "#fffacd",   # light yellow
    "low":      "#ffe4e1",   # light red / rose
    "high":     "#e8f5e9",   # light green
}


def _shade_phases(ax, total_steps: int, phase_len: int = 50):
    """Shade replenishment-phase bands using REPLENISHMENT_PATTERN."""
    n = len(REPLENISHMENT_PATTERN)
    i = 0
    while i * phase_len < total_steps:
        phase_name = REPLENISHMENT_PATTERN[i % n]
        start = i * phase_len
        end   = min(start + phase_len, total_steps)
        ax.axvspan(start, end, color=_PHASE_COLORS[phase_name], alpha=0.55, linewidth=0)
        i += 1


def plot_results(result: dict, config, out_path: str | None = None) -> str:
    """
    Generate a two-panel figure from a CPRModel run result.

    Panel 1 — Active members over time.
    Panel 2 — Resource pool P (after replenishment) over time,
               with shaded bands for the replenishment phases.

    Returns the path of the saved PNG.
    """
    model_df  = result["model_df"]
    lifespan  = result["lifespan"]
    steps     = model_df.index.tolist()

    if out_path is None:
        out_path = os.path.join(_OUT_DIR, "simulation_results.png")

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"hspace": 0.35},
    )
    fig.patch.set_facecolor("#fafafa")

    # ── Panel 1: Active members ───────────────────────────────────────────────
    ax1.set_facecolor("#fafafa")
    ax1.plot(
        steps, model_df["ActiveMembers"],
        color="#1565c0", linewidth=1.8, label="Active members",
    )
    ax1.set_ylabel("Active members", fontsize=11)
    ax1.set_title("Active agents over time", fontsize=12, fontweight="bold")
    ax1.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax1.set_ylim(bottom=0)
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax1.set_xlim(0, lifespan)

    # ── Panel 2: Resource pool ────────────────────────────────────────────────
    ax2.set_facecolor("#fafafa")

    # Phase shading first so the line sits on top
    _shade_phases(ax2, lifespan)

    ax2.plot(
        steps, model_df["ResourcePool"] / 1000,
        color="#2e7d32", linewidth=1.8, label="Pool P (post-replenishment)",
    )

    # p_max reference line
    ax2.axhline(config.p_max / 1000, color="#555", linewidth=0.8,
                linestyle=":", label=f"P_max ({config.p_max / 1000:.0f}k)")

    ax2.set_xlabel("Round", fontsize=11)
    ax2.set_ylabel("Resource pool P (×10³)", fontsize=11)
    ax2.set_title(
        "Resource pool after replenishment  "
        "(shading: ░░ moderate | ░░ low | ░░ high)",
        fontsize=12, fontweight="bold",
    )
    ax2.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)

    # Custom legend patches for the phases
    phase_patches = [
        mpatches.Patch(color=_PHASE_COLORS["moderate"], label=f"Moderate (+{config.replenishment_moderate*100:.0f}% P_max)"),
        mpatches.Patch(color=_PHASE_COLORS["low"],      label=f"Low (+{config.replenishment_low*100:.0f}% P_max)"),
        mpatches.Patch(color=_PHASE_COLORS["high"],     label=f"High (+{config.replenishment_high*100:.0f}% P_max)"),
    ]
    handles, labels = ax2.get_legend_handles_labels()
    ax2.legend(
        handles + phase_patches, labels + [p.get_label() for p in phase_patches],
        loc="upper right", fontsize=8, ncol=2,
    )

    # X-axis ticks every 100 rounds
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(100))
    ax2.xaxis.set_minor_locator(ticker.MultipleLocator(50))
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(100))
    ax1.xaxis.set_minor_locator(ticker.MultipleLocator(50))

    # Overall title
    fig.suptitle(
        f"CPR Simulation  |  lifespan={lifespan} rounds  |  "
        f"final pool={result['final_resource']:.0f}  |  "
        f"final members={result['final_members']}",
        fontsize=11, y=0.98,
    )

    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    _log.info("Plot saved to %s", out_path)
    return out_path
