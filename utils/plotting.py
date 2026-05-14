import os
import sys
import logging
import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import REPLENISHMENT_PATTERN

_log = logging.getLogger("axioms.plot")

_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

_PHASE_COLORS = {
    "moderate": "#fffacd",
    "low":      "#ffe4e1",
    "high":     "#e8f5e9",
}

_RA_COLORS = {
    "queue":  "#bbdefb",   # soft blue
    "ration": "#ffe0b2",   # soft amber
}


def _shade_phases(ax, total_steps: int, phase_len: int = 50):
    n = len(REPLENISHMENT_PATTERN)
    i = 0
    while i * phase_len < total_steps:
        phase_name = REPLENISHMENT_PATTERN[i % n]
        start = i * phase_len
        end   = min(start + phase_len, total_steps)
        ax.axvspan(start, end, color=_PHASE_COLORS[phase_name], alpha=0.55, linewidth=0)
        i += 1


def _shade_ra_method(ax, steps: list, ra_series, alpha: float = 0.35, strip: bool = False):
    """Shade contiguous blocks of the same RA method on *ax*.

    strip=True draws a narrow band at the bottom of the axes instead of
    filling the whole background — useful when the axes already has other shading.
    """
    if not steps or ra_series.empty:
        return

    # Find contiguous runs
    segments = []
    seg_start = steps[0]
    prev = ra_series.iloc[0]
    for step, method in zip(steps[1:], ra_series.iloc[1:]):
        if method != prev:
            segments.append((seg_start, step, prev))
            seg_start = step
            prev = method
    segments.append((seg_start, steps[-1] + 1, prev))

    if strip:
        ymin, ymax = ax.get_ylim()
        strip_h = (ymax - ymin) * 0.04          # 4 % of y-range
        for start, end, method in segments:
            ax.axvspan(start, end,
                       ymin=0, ymax=0.04,        # bottom 4 % in axes coords
                       color=_RA_COLORS.get(method, "#ffffff"),
                       alpha=0.9, linewidth=0)
    else:
        for start, end, method in segments:
            ax.axvspan(start, end,
                       color=_RA_COLORS.get(method, "#ffffff"),
                       alpha=alpha, linewidth=0)


def plot_results(result: dict, config, out_path: str | None = None) -> str:
    model_df = result["model_df"]
    lifespan = result["lifespan"]
    steps    = model_df.index.tolist()

    if out_path is None:
        out_path = os.path.join(_OUT_DIR, "simulation_results.png")

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"hspace": 0.35},
    )
    fig.patch.set_facecolor("#fafafa")

    # ── Panel 1: Active members ── RA method shading as background ────────────
    ax1.set_facecolor("#fafafa")
    if "RAMethod" in model_df.columns:
        _shade_ra_method(ax1, steps, model_df["RAMethod"], alpha=0.45)

    ax1.plot(
        steps, model_df["ActiveMembers"],
        color="#1565c0", linewidth=1.8, label="Active members",
    )
    ax1.set_ylabel("Active members", fontsize=11)
    ax1.set_title("Active agents over time", fontsize=12, fontweight="bold")
    ax1.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax1.set_ylim(bottom=0)
    ax1.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax1.set_xlim(0, lifespan)

    # RA method legend for panel 1
    ra_patches = [
        mpatches.Patch(color=_RA_COLORS["queue"],  label="Queue allocation"),
        mpatches.Patch(color=_RA_COLORS["ration"], label="Ration allocation"),
    ]
    handles, labels = ax1.get_legend_handles_labels()
    ax1.legend(handles + ra_patches, labels + [p.get_label() for p in ra_patches],
               loc="upper right", fontsize=9)

    # ── Panel 2: Resource pool ── phase shading + RA strip at bottom ──────────
    ax2.set_facecolor("#fafafa")
    phase_len = getattr(config, "replenishment_phase_len", 50)
    _shade_phases(ax2, lifespan, phase_len=phase_len)

    ax2.plot(
        steps, model_df["ResourcePool"] / 1000,
        color="#2e7d32", linewidth=1.8, label="Pool P (post-replenishment)",
    )
    ax2.axhline(config.p_max / 1000, color="#555", linewidth=0.8,
                linestyle=":", label=f"P_max ({config.p_max / 1000:.0f}k)")

    ax2.set_xlabel("Round", fontsize=11)
    ax2.set_ylabel("Resource pool P (×10³)", fontsize=11)
    ax2.set_title(
        "Resource pool after replenishment  "
        "(shading: ░░ moderate | ░░ low | ░░ high  ·  strip: queue | ration)",
        fontsize=12, fontweight="bold",
    )
    ax2.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)

    # Draw RA strip after y-limits are set
    if "RAMethod" in model_df.columns:
        _shade_ra_method(ax2, steps, model_df["RAMethod"], strip=True)

    phase_patches = [
        mpatches.Patch(color=_PHASE_COLORS["moderate"], label=f"Moderate (+{config.replenishment_moderate*100:.0f}% P_max)"),
        mpatches.Patch(color=_PHASE_COLORS["low"],      label=f"Low (+{config.replenishment_low*100:.0f}% P_max)"),
        mpatches.Patch(color=_PHASE_COLORS["high"],     label=f"High (+{config.replenishment_high*100:.0f}% P_max)"),
        mpatches.Patch(color=_RA_COLORS["queue"],       label="Queue (strip)"),
        mpatches.Patch(color=_RA_COLORS["ration"],      label="Ration (strip)"),
    ]
    handles, labels = ax2.get_legend_handles_labels()
    ax2.legend(
        handles + phase_patches, labels + [p.get_label() for p in phase_patches],
        loc="upper right", fontsize=8, ncol=2,
    )

    # X-axis ticks
    if lifespan <= 30:
        major_tick, minor_tick = phase_len, max(1, phase_len // 5)
    elif lifespan <= 100:
        major_tick, minor_tick = phase_len * 2, phase_len
    elif lifespan <= 300:
        major_tick, minor_tick = 50, 10
    else:
        major_tick, minor_tick = 100, 50
    for ax in (ax1, ax2):
        ax.xaxis.set_major_locator(ticker.MultipleLocator(major_tick))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(minor_tick))

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
