"""PERT/CPM calculation engine for the educational scheduling prototype.

Scope (declared limits, see manuscript Appendix B):
  * activity-on-node network, finish-to-start links, zero lag
  * single time unit per dataset (default: hours), start at time zero
  * no resources, calendars, or probabilities
  * scenarios are deterministic "what-if" edits; they give conditional completion
    times, not probabilities. Survey scores never set durations.
  * at most MAX_ACTIVITIES activities and MAX_LINKS links

All calculations use full floating-point precision. Rounding is for display only
(see ``fmt``). Criticality uses a small tolerance (TOL) to absorb floating error.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx

APP_VERSION = "0.1.0-prototype"
MAX_ACTIVITIES = 50
MAX_LINKS = 100
TOL = 1e-9
DISPLAY_DECIMALS = 2
MAX_PATHS = 1000
DEFAULT_UNIT = "hours"

EDUCATIONAL_STATEMENT = (
    "EDUCATIONAL PROTOTYPE. This tool illustrates PERT/CPM arithmetic and "
    "what-if scheduling scenarios for learning. It is not approved for planning, "
    "releasing, or certifying real maintenance work, and its results are not "
    "predictions of actual delay. Survey scores never set durations; scenario "
    "changes are illustrative assumptions entered by the user."
)

ASSUMPTIONS = [
    "Activity-on-node network; every link is finish-to-start with zero lag.",
    "All activities start as early as possible from time zero.",
    "One time unit for the whole dataset.",
    "No resource, crew, shift, or calendar constraints are modelled.",
    "Expected time TE = (O + 4M + P) / 6, computed at full precision; displayed values are rounded.",
    "Scenario results are conditional completion times, not probabilities.",
]


# --------------------------------------------------------------------------- data
@dataclass
class Activity:
    id: str
    name: str = ""
    predecessors: list[str] = field(default_factory=list)
    o: float = 0.0
    m: float = 0.0
    p: float = 0.0
    milestone: bool = False
    unit: str = DEFAULT_UNIT


@dataclass
class Issue:
    code: str          # e.g. "DUPLICATE_ID"
    message: str
    ids: list[str] = field(default_factory=list)


class ValidationError(Exception):
    def __init__(self, issues: list[Issue]):
        super().__init__("; ".join(i.message for i in issues))
        self.issues = issues


# ----------------------------------------------------------------------- parsing
def _to_number(value) -> tuple[float | None, str | None]:
    """Return (number, error_code). Rejects blank, non-numeric, non-finite."""
    if value is None:
        return None, "MISSING"
    if isinstance(value, bool):
        return None, "NONNUMERIC"
    if isinstance(value, (int, float)):
        x = float(value)
    else:
        s = str(value).strip()
        if s == "":
            return None, "MISSING"
        try:
            x = float(s)
        except ValueError:
            return None, "NONNUMERIC"
    if math.isnan(x) or math.isinf(x):
        return None, "NONFINITE"
    return x, None


def _split_preds(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        s = str(value).replace(";", ",").replace(" and ", ",")
        parts = s.split(",")
    out = []
    for p in parts:
        p = p.strip()
        if p and p.lower() not in {"none", "nan", "-"}:
            out.append(p)
    return out


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y", "x", "milestone"}


def parse_rows(rows: Iterable[dict], default_unit: str = DEFAULT_UNIT):
    """Convert raw table rows to Activity objects, collecting every issue found.

    Keys (case-insensitive): id, name, predecessors, o, m, p, milestone, unit.
    Returns (activities, issues). Activities with unparseable numbers are omitted
    from the list, but the issues explain why.
    """
    issues: list[Issue] = []
    acts: list[Activity] = []
    for idx, raw in enumerate(rows, start=1):
        row = {str(k).strip().lower(): v for k, v in dict(raw).items()}
        rid = "" if row.get("id") is None else str(row.get("id"))
        rid_clean = rid.strip()
        if isinstance(row.get("id"), float) and math.isnan(row["id"]):
            rid_clean = ""
        label = rid_clean or f"row {idx}"
        if rid_clean == "":
            issues.append(Issue("BLANK_ID", f"Row {idx}: the activity ID is blank.", [f"row {idx}"]))
        nums = {}
        bad = False
        for key in ("o", "m", "p"):
            x, err = _to_number(row.get(key))
            if err == "MISSING":
                issues.append(Issue("MISSING_VALUE", f"Activity {label}: {key.upper()} is missing.", [label]))
                bad = True
            elif err == "NONNUMERIC":
                issues.append(Issue("NONNUMERIC", f"Activity {label}: {key.upper()} is not a number.", [label]))
                bad = True
            elif err == "NONFINITE":
                issues.append(Issue("NONFINITE", f"Activity {label}: {key.upper()} must be a finite number.", [label]))
                bad = True
            else:
                nums[key] = x
        unit = row.get("unit")
        unit = default_unit if unit is None or (isinstance(unit, float) and math.isnan(unit)) or str(unit).strip() == "" else str(unit).strip().lower()
        if bad:
            continue
        acts.append(Activity(
            id=rid_clean,
            name="" if row.get("name") is None or (isinstance(row.get("name"), float) and math.isnan(row["name"])) else str(row.get("name")).strip(),
            predecessors=_split_preds(row.get("predecessors", row.get("predecessor"))),
            o=nums["o"], m=nums["m"], p=nums["p"],
            milestone=_truthy(row.get("milestone")),
            unit=unit,
        ))
    return acts, issues


# --------------------------------------------------------------------- validation
def validate(acts: list[Activity]) -> list[Issue]:
    """Structural and numeric validation. Returns all issues (empty list = valid)."""
    issues: list[Issue] = []
    if not acts:
        return [Issue("EMPTY", "No activities were entered; no schedule can be calculated.")]

    if len(acts) > MAX_ACTIVITIES:
        issues.append(Issue("TOO_MANY_ACTIVITIES",
                            f"{len(acts)} activities entered; the limit is {MAX_ACTIVITIES}."))
    links = sum(len(a.predecessors) for a in acts)
    if links > MAX_LINKS:
        issues.append(Issue("TOO_MANY_LINKS", f"{links} links entered; the limit is {MAX_LINKS}."))

    seen: dict[str, int] = {}
    for a in acts:
        if a.id == "":
            issues.append(Issue("BLANK_ID", "An activity has a blank ID."))
            continue
        seen[a.id] = seen.get(a.id, 0) + 1
    for k, n in seen.items():
        if n > 1:
            issues.append(Issue("DUPLICATE_ID", f"Duplicate activity ID '{k}' appears {n} times.", [k]))

    units = {a.unit for a in acts}
    if len(units) > 1:
        issues.append(Issue("MIXED_UNITS",
                            "Mixed time units found (" + ", ".join(sorted(units)) + "). Use one unit for the whole dataset."))

    ids = set(seen)
    for a in acts:
        if a.id == "":
            continue
        for key, v in (("O", a.o), ("M", a.m), ("P", a.p)):
            if v < 0:
                issues.append(Issue("NEGATIVE", f"Activity {a.id}: {key} is negative ({v:g}).", [a.id]))
        if a.o > a.m:
            issues.append(Issue("ORDER", f"Activity {a.id}: O ({a.o:g}) is greater than M ({a.m:g}); O must be ≤ M ≤ P.", [a.id]))
        if a.m > a.p:
            issues.append(Issue("ORDER", f"Activity {a.id}: M ({a.m:g}) is greater than P ({a.p:g}); O must be ≤ M ≤ P.", [a.id]))
        zero = a.o == 0 and a.m == 0 and a.p == 0
        if zero and not a.milestone:
            issues.append(Issue("ZERO_DURATION",
                                f"Activity {a.id}: all estimates are 0 but it is not marked as a milestone.", [a.id]))
        if a.milestone and not zero:
            issues.append(Issue("MILESTONE_NONZERO",
                                f"Activity {a.id}: a milestone must have O = M = P = 0.", [a.id]))
        for pr in a.predecessors:
            if pr == a.id:
                issues.append(Issue("SELF_LINK", f"Activity {a.id} lists itself as a predecessor.", [a.id]))
            elif pr not in ids:
                issues.append(Issue("UNKNOWN_PREDECESSOR",
                                    f"Activity {a.id}: predecessor '{pr}' is not an activity in the table.", [a.id, pr]))
        if len(set(a.predecessors)) != len(a.predecessors):
            issues.append(Issue("DUPLICATE_LINK", f"Activity {a.id}: the same predecessor is listed more than once.", [a.id]))

    # cycles (only meaningful when ids/links are otherwise consistent)
    structural = {"BLANK_ID", "DUPLICATE_ID", "UNKNOWN_PREDECESSOR", "SELF_LINK"}
    if not any(i.code in structural for i in issues):
        g = nx.DiGraph()
        g.add_nodes_from(ids)
        for a in acts:
            for pr in a.predecessors:
                g.add_edge(pr, a.id)
        cyc = [sorted(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
        for c in cyc:
            issues.append(Issue("CYCLE", "Cycle detected among activities: " + ", ".join(c) + ".", c))
    return issues


# ------------------------------------------------------------------------- PERT
def expected_time(o: float, m: float, p: float) -> float:
    """PERT expected time, full precision."""
    return (o + 4.0 * m + p) / 6.0


def pert_table(acts: list[Activity]) -> list[dict]:
    return [{"id": a.id, "name": a.name, "O": a.o, "M": a.m, "P": a.p,
             "milestone": a.milestone, "TE": expected_time(a.o, a.m, a.p)} for a in acts]


# -------------------------------------------------------------------------- CPM
@dataclass
class CPMResult:
    unit: str
    duration: dict[str, float]
    es: dict[str, float]
    ef: dict[str, float]
    ls: dict[str, float]
    lf: dict[str, float]
    total_float: dict[str, float]
    critical: list[str]                 # activity ids with ~zero total float, in topological order
    project_duration: float
    critical_paths: list[list[str]]
    paths_truncated: bool
    order: list[str]
    predecessors: dict[str, list[str]]

    def table(self) -> list[dict]:
        return [{"id": i, "duration": self.duration[i], "ES": self.es[i], "EF": self.ef[i],
                 "LS": self.ls[i], "LF": self.lf[i], "float": self.total_float[i],
                 "critical": i in set(self.critical)} for i in self.order]


def cpm(acts: list[Activity], durations: dict[str, float] | None = None) -> CPMResult:
    """Forward and backward pass. Raises ValidationError if the dataset is invalid.

    ``durations`` optionally overrides the PERT expected time per activity id
    (used by scenarios). Overrides must be finite and non-negative.
    """
    issues = validate(acts)
    if issues:
        raise ValidationError(issues)
    dur = {a.id: expected_time(a.o, a.m, a.p) for a in acts}
    if durations:
        for k, v in durations.items():
            if k not in dur:
                raise ValidationError([Issue("UNKNOWN_ACTIVITY", f"Scenario refers to unknown activity '{k}'.", [k])])
            if not math.isfinite(v) or v < 0:
                raise ValidationError([Issue("BAD_DURATION", f"Scenario duration for '{k}' must be finite and ≥ 0.", [k])])
            dur[k] = float(v)

    g = nx.DiGraph()
    g.add_nodes_from(dur)
    preds = {a.id: list(a.predecessors) for a in acts}
    for a in acts:
        for pr in a.predecessors:
            g.add_edge(pr, a.id)
    order = list(nx.lexicographical_topological_sort(g, key=lambda n: [a.id for a in acts].index(n)))

    es, ef = {}, {}
    for n in order:
        es[n] = max((ef[p] for p in g.predecessors(n)), default=0.0)
        ef[n] = es[n] + dur[n]
    finish = max(ef.values())
    lf, ls = {}, {}
    for n in reversed(order):
        lf[n] = min((ls[s] for s in g.successors(n)), default=finish)
        ls[n] = lf[n] - dur[n]
    tf = {n: ls[n] - es[n] for n in order}
    # snap tiny floating noise to zero
    tf = {n: (0.0 if abs(v) <= TOL else v) for n, v in tf.items()}
    crit_set = {n for n in order if tf[n] <= TOL}

    # enumerate critical paths: start at critical activities with ES = 0,
    # follow critical successors whose ES equals this EF, end at EF = finish.
    paths: list[list[str]] = []
    truncated = False

    def walk(node: str, trail: list[str]):
        nonlocal truncated
        if truncated:
            return
        trail = trail + [node]
        nexts = [s for s in g.successors(node)
                 if s in crit_set and abs(es[s] - ef[node]) <= TOL]
        if abs(ef[node] - finish) <= TOL and not nexts:
            if len(paths) >= MAX_PATHS:
                truncated = True
                return
            paths.append(trail)
            return
        for s in nexts:
            walk(s, trail)

    for n in order:
        feeds = [p for p in g.predecessors(n) if p in crit_set and abs(ef[p] - es[n]) <= TOL]
        if n in crit_set and abs(es[n]) <= TOL and not feeds:
            walk(n, [])
    # de-duplicate while preserving order
    uniq, seen = [], set()
    for p in paths:
        t = tuple(p)
        if t not in seen:
            seen.add(t)
            uniq.append(p)

    unit = acts[0].unit
    return CPMResult(unit, dur, es, ef, ls, lf, tf,
                     [n for n in order if n in crit_set], finish, uniq, truncated, order, preds)


# --------------------------------------------------------------------- scenarios
@dataclass
class ScenarioChange:
    activity: str
    mode: str                  # "add" (add hours to the expected time) or "replace"
    value: float
    reason: str = ""
    source: str = ""
    reviewer: str = ""
    status: str = "Illustrative"   # Illustrative | Reviewed (basis stated)


def scenario_durations(acts: list[Activity], changes: list[ScenarioChange]) -> dict[str, float]:
    base = {a.id: expected_time(a.o, a.m, a.p) for a in acts}
    new: dict[str, float] = {}
    issues: list[Issue] = []
    for c in changes:
        if c.activity not in base:
            issues.append(Issue("UNKNOWN_ACTIVITY", f"Scenario refers to unknown activity '{c.activity}'.", [c.activity]))
            continue
        x, err = _to_number(c.value)
        if err:
            issues.append(Issue("BAD_SCENARIO_VALUE", f"Scenario value for '{c.activity}' is not a valid number.", [c.activity]))
            continue
        if c.mode not in ("add", "replace"):
            issues.append(Issue("BAD_MODE", f"Scenario mode for '{c.activity}' must be 'add' or 'replace'.", [c.activity]))
            continue
        cur = new.get(c.activity, base[c.activity])
        val = cur + x if c.mode == "add" else x
        if val < 0:
            issues.append(Issue("BAD_DURATION", f"Scenario makes '{c.activity}' negative ({val:g}).", [c.activity]))
            continue
        new[c.activity] = val
    if issues:
        raise ValidationError(issues)
    return new


@dataclass
class ScenarioResult:
    baseline: CPMResult
    scenario: CPMResult
    changes: list[ScenarioChange]
    finish_delta: float
    path_changed: bool
    changed_rows: list[dict]

    def comparison(self) -> list[dict]:
        rows = []
        for i in self.baseline.order:
            b, s = self.baseline, self.scenario
            rows.append({
                "id": i,
                "duration_base": b.duration[i], "duration_scn": s.duration[i],
                "ES_base": b.es[i], "ES_scn": s.es[i],
                "EF_base": b.ef[i], "EF_scn": s.ef[i],
                "float_base": b.total_float[i], "float_scn": s.total_float[i],
                "critical_base": i in set(b.critical), "critical_scn": i in set(s.critical),
            })
        return rows


def run_scenario(acts: list[Activity], changes: list[ScenarioChange]) -> ScenarioResult:
    base = cpm(acts)
    new = scenario_durations(acts, changes)
    scn = cpm(acts, durations=new)
    bp = sorted(tuple(p) for p in base.critical_paths)
    sp = sorted(tuple(p) for p in scn.critical_paths)
    rows = []
    for c in changes:
        rows.append({
            "activity": c.activity, "mode": c.mode, "value": c.value,
            "baseline_duration": base.duration.get(c.activity),
            "scenario_duration": scn.duration.get(c.activity),
            "unit": base.unit, "reason": c.reason, "source": c.source,
            "reviewer": c.reviewer, "status": c.status,
        })
    return ScenarioResult(base, scn, changes, scn.project_duration - base.project_duration,
                          bp != sp, rows)


# ---------------------------------------------------------------------- utilities
def fmt(x: float, decimals: int = DISPLAY_DECIMALS) -> str:
    """Display rounding only; calculations are never rounded."""
    if x is None:
        return ""
    r = round(float(x), decimals)
    if r == 0:
        r = 0.0
    s = f"{r:.{decimals}f}".rstrip("0").rstrip(".")
    return s if s else "0"


def fingerprint(acts: list[Activity], changes: list[ScenarioChange] | None = None) -> str:
    """Short hash identifying exactly which dataset (and scenario) a result belongs to."""
    payload = {
        "acts": [[a.id, a.name, a.predecessors, a.o, a.m, a.p, a.milestone, a.unit] for a in acts],
        "chg": [[c.activity, c.mode, c.value] for c in (changes or [])],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def path_text(path: list[str]) -> str:
    return "–".join(path)


def build_report(acts: list[Activity], base: CPMResult, scn: ScenarioResult | None = None,
                 title: str = "PERT/CPM Educational Report") -> str:
    """Plain-text (Markdown) report with version, dataset fingerprint, assumptions and status."""
    lines = [f"# {title}", "", f"**{EDUCATIONAL_STATEMENT}**", "",
             f"Prototype version: {APP_VERSION}",
             f"Dataset fingerprint: {fingerprint(acts, scn.changes if scn else None)}",
             f"Time unit: {base.unit}", ""]
    lines += ["## Assumptions", ""] + [f"- {a}" for a in ASSUMPTIONS] + [""]
    lines += ["## Activities and PERT expected times", "",
              "| ID | Name | Predecessors | O | M | P | TE |", "|---|---|---|---|---|---|---|"]
    for a in acts:
        lines.append(f"| {a.id} | {a.name} | {', '.join(a.predecessors) or 'None'} | {fmt(a.o)} | {fmt(a.m)} | {fmt(a.p)} | {fmt(expected_time(a.o, a.m, a.p))} |")
    lines += ["", "## CPM baseline", "",
              f"Project duration: {fmt(base.project_duration)} {base.unit}", "",
              "| ID | Duration | ES | EF | LS | LF | Total float | Critical |", "|---|---|---|---|---|---|---|---|"]
    for r in base.table():
        lines.append(f"| {r['id']} | {fmt(r['duration'])} | {fmt(r['ES'])} | {fmt(r['EF'])} | {fmt(r['LS'])} | {fmt(r['LF'])} | {fmt(r['float'])} | {'Yes' if r['critical'] else 'No'} |")
    lines += ["", "Critical path(s): " + "; ".join(path_text(p) for p in base.critical_paths) +
              (" (list truncated)" if base.paths_truncated else ""), ""]
    if scn:
        s = scn.scenario
        lines += ["## Scenario (illustrative what-if)", "",
                  "| Activity | Mode | Value | Baseline | Scenario | Unit | Reason | Source | Reviewer | Status |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in scn.changed_rows:
            lines.append(f"| {r['activity']} | {r['mode']} | {fmt(r['value'])} | {fmt(r['baseline_duration'])} | {fmt(r['scenario_duration'])} | {r['unit']} | {r['reason']} | {r['source']} | {r['reviewer']} | {r['status']} |")
        lines += ["", f"Baseline finish: {fmt(base.project_duration)} {base.unit}",
                  f"Scenario finish: {fmt(s.project_duration)} {base.unit}",
                  f"Change in finish: {fmt(scn.finish_delta)} {base.unit}",
                  f"Critical path changed: {'Yes' if scn.path_changed else 'No'}",
                  "Scenario critical path(s): " + "; ".join(path_text(p) for p in s.critical_paths), "",
                  "These are conditional completion times under the stated assumptions, not probabilities or predictions."]
    return "\n".join(lines) + "\n"


def to_rows(acts: list[Activity]) -> list[dict]:
    return [{"id": a.id, "name": a.name, "predecessors": ", ".join(a.predecessors),
             "o": a.o, "m": a.m, "p": a.p, "milestone": a.milestone, "unit": a.unit} for a in acts]


def example_n1() -> list[dict]:
    """Acceptance network N1 (Appendix C, Table C1). Durations as O = M = P = hours."""
    spec = [("A", "Open access panels, inspect pump bay", "", 2),
            ("B", "Drain system, remove old hydraulic pump", "A", 6),
            ("C", "Draw new pump from stores, check release certificate", "A", 3),
            ("D", "Install new pump, connect lines", "B", 4),
            ("E", "Leak test and functional check", "C, D", 2),
            ("F", "Close panels, complete task records", "E", 1)]
    return [{"id": i, "name": n, "predecessors": pr, "o": h, "m": h, "p": h,
             "milestone": False, "unit": DEFAULT_UNIT} for i, n, pr, h in spec]


def example_n2() -> list[dict]:
    """Example network N2: main wheel and brake assembly replacement (three-point estimates, hours)."""
    spec = [("A", "Jack aircraft, depressurize brake system", "", 1, 1.5, 2),
            ("B", "Remove wheel and brake assembly", "A", 1, 2, 3),
            ("C", "Inspect axle, bearings and brake components", "B", 2, 2.5, 3),
            ("D", "Draw replacement wheel and brake unit, check release certificates", "", 1, 2, 6),
            ("E", "Mount new tire on wheel, check pressure and balance", "D", 2, 3, 4),
            ("F", "Install wheel and brake assembly, torque", "C, E", 2, 2.5, 3),
            ("G", "Bleed brakes, service tire pressure", "F", 1, 1.5, 2),
            ("H", "Lower aircraft, brake functional check, complete records", "G", 0.5, 1, 1.5)]
    return [{"id": i, "name": n, "predecessors": pr, "o": o, "m": m, "p": p,
             "milestone": False, "unit": DEFAULT_UNIT} for i, n, pr, o, m, p in spec]


def clean_rows(records: Iterable[dict]) -> list[dict]:
    """Drop completely empty table rows (added by the editor) but keep partially filled ones
    so that validation can report them."""
    out = []
    for r in records:
        vals = [v for v in dict(r).values()
                if not (v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "")
                        or v is False)]
        if vals:
            out.append(dict(r))
    return out
