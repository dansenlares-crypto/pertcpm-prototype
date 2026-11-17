"""Static network diagram (Matplotlib). Layout: columns by longest-path depth.
Each box shows ID, duration, ES and EF; critical activities and links are highlighted
with both colour and a thicker outline so meaning does not depend on colour alone."""
from __future__ import annotations
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

import engine as e

CRIT = "#b42318"
NORM = "#475467"
FILL_CRIT = "#fef3f2"
FILL_NORM = "#f9fafb"


def layout(res: e.CPMResult):
    depth: dict[str, int] = {}
    for n in res.order:
        depth[n] = max((depth[p] + 1 for p in res.predecessors[n]), default=0)
    cols: dict[int, list[str]] = {}
    for n in res.order:
        cols.setdefault(depth[n], []).append(n)
    pos = {}
    for d, nodes in cols.items():
        k = len(nodes)
        for j, n in enumerate(nodes):
            pos[n] = (d, (k - 1) / 2 - j)
    return pos, cols


def draw(res: e.CPMResult, title: str = "", names: dict | None = None):
    names = names or {}
    pos, cols = layout(res)
    ncols = max(cols) + 1
    nrows = max(len(v) for v in cols.values())
    w, h = 1.9, 1.25
    fig, ax = plt.subplots(figsize=(max(6, 2.4 * ncols), max(3, 1.5 * nrows + 1)), dpi=110)
    crit = set(res.critical)
    crit_edges = set()
    for path in res.critical_paths:
        crit_edges.update(zip(path, path[1:]))
    def rad(p, n):
        gap = pos[n][0] - pos[p][0]
        if gap <= 1:
            return 0.0
        return 0.3 * min(gap - 1, 2) if pos[p][1] + pos[n][1] <= 0 else -0.3 * min(gap - 1, 2)
    X = lambda n: pos[n][0] * 2.6
    Y = lambda n: pos[n][1] * 1.5
    for n in res.order:
        for p in res.predecessors[n]:
            c = (p, n) in crit_edges
            ax.add_patch(FancyArrowPatch((X(p) + w / 2, Y(p)), (X(n) - w / 2, Y(n)),
                                         arrowstyle="-|>", mutation_scale=12,
                                         color=CRIT if c else "#98a2b3", lw=2.6 if c else 1.1,
                                         connectionstyle=f"arc3,rad={rad(p, n)}", zorder=1))
    for n in res.order:
        c = n in crit
        ax.add_patch(FancyBboxPatch((X(n) - w / 2, Y(n) - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=FILL_CRIT if c else FILL_NORM, ec=CRIT if c else NORM,
                                    lw=2.6 if c else 1.0, zorder=2))
        nm = textwrap.wrap(names.get(n, ""), 26)
        if len(nm) > 2:
            nm = [nm[0], nm[1][:23] + "..."]
        ax.text(X(n), Y(n) + 0.36, "\n".join(nm), ha="center", va="center", fontsize=6.5,
                color="#101828", linespacing=1.15, zorder=3)
        ax.text(X(n), Y(n) + 0.02, f"{n}  ({e.fmt(res.duration[n])} {res.unit[0]})", ha="center", va="center",
                fontsize=9, fontweight="bold", color="#101828", zorder=3)
        ax.text(X(n), Y(n) - 0.2, f"ES {e.fmt(res.es[n])}   EF {e.fmt(res.ef[n])}", ha="center", va="center",
                fontsize=7.5, color="#344054", zorder=3)
        ax.text(X(n), Y(n) - 0.42, f"LS {e.fmt(res.ls[n])}   LF {e.fmt(res.lf[n])}   float {e.fmt(res.total_float[n])}",
                ha="center", va="center", fontsize=6.5, color="#667085", zorder=3)
    ax.set_xlim(-w, X(max(res.order, key=lambda n: pos[n][0])) + w)
    ys = [Y(n) for n in res.order]
    ax.set_ylim(min(ys) - 1, max(ys) + 1)
    ax.axis("off")
    ttl = title or "Network diagram"
    ax.set_title(f"{ttl} — project duration {e.fmt(res.project_duration)} {res.unit}", fontsize=10, loc="left")
    ax.text(0, min(ys) - 0.85, "Red outline and thick arrows = critical path. Box unit letter: "
            f"{res.unit[0]} = {res.unit}.", fontsize=7.5, color="#475467")
    fig.tight_layout()
    return fig
