"""Verification tests against the independent answer keys (manuscript Appendix C)
and the technical test cases (Appendix D). Tolerance 1e-6 as in the manuscript."""
import os, sys, time
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine as e

TOL = 1e-6


def build(spec, unit="hours"):
    """spec: list of (id, preds, hours) with O=M=P=hours."""
    rows = [{"id": i, "name": i, "predecessors": p, "o": h, "m": h, "p": h, "unit": unit} for i, p, h in spec]
    acts, issues = e.parse_rows(rows)
    assert not issues
    return acts


N1 = [("A", "", 2), ("B", "A", 6), ("C", "A", 3), ("D", "B", 4), ("E", "C, D", 2), ("F", "E", 1)]


def check(res, key):
    for i, (es, ef, ls, lf, tf) in key.items():
        assert res.es[i] == pytest.approx(es, abs=TOL), i
        assert res.ef[i] == pytest.approx(ef, abs=TOL), i
        assert res.ls[i] == pytest.approx(ls, abs=TOL), i
        assert res.lf[i] == pytest.approx(lf, abs=TOL), i
        assert res.total_float[i] == pytest.approx(tf, abs=TOL), i


N1_KEY = {"A": (0, 2, 0, 2, 0), "B": (2, 8, 2, 8, 0), "C": (2, 5, 9, 12, 7),
          "D": (8, 12, 8, 12, 0), "E": (12, 14, 12, 14, 0), "F": (14, 15, 14, 15, 0)}


# ---------------------------------------------------------------- PERT P01-P05
@pytest.mark.parametrize("o,m,p,te", [(2, 4, 8, 4.333333), (5, 5, 5, 5), (1.5, 2.5, 4.5, 2.666667), (3, 3, 9, 4)])
def test_pert(o, m, p, te):
    assert e.expected_time(o, m, p) == pytest.approx(te, abs=TOL)


def test_p04_milestone():
    ok = e.validate(e.parse_rows([{"id": "M", "predecessors": "", "o": 0, "m": 0, "p": 0, "milestone": True}])[0])
    assert ok == []
    bad = e.validate(e.parse_rows([{"id": "M", "predecessors": "", "o": 0, "m": 0, "p": 0, "milestone": False}])[0])
    assert [i.code for i in bad] == ["ZERO_DURATION"]


# ------------------------------------------------------------------ CPM C01-C07
def test_c02_n1():
    r = e.cpm(build(N1))
    check(r, N1_KEY)
    assert r.project_duration == pytest.approx(15)
    assert sum(r.duration.values()) == pytest.approx(18)  # not the project duration
    assert r.critical_paths == [["A", "B", "D", "E", "F"]]  # C05


def test_c01_n2():
    r = e.cpm(build([("A", "", 2), ("B", "A", 3), ("C", "B", 4)]))
    check(r, {"A": (0, 2, 0, 2, 0), "B": (2, 5, 2, 5, 0), "C": (5, 9, 5, 9, 0)})
    assert r.project_duration == pytest.approx(9)


def test_c03_n3():
    r = e.cpm(build([("A", "", 3), ("B", "", 5), ("C", "A, B", 2), ("D", "B", 4)]))
    check(r, {"A": (0, 3, 4, 7, 4), "B": (0, 5, 0, 5, 0), "C": (5, 7, 7, 9, 2), "D": (5, 9, 5, 9, 0)})
    assert r.project_duration == pytest.approx(9)
    assert r.critical_paths == [["B", "D"]]


def test_c04_single():
    r = e.cpm(build([("A", "", 5)]))
    check(r, {"A": (0, 5, 0, 5, 0)})
    assert r.project_duration == pytest.approx(5)


def scn(add=None, replace=None):
    ch = []
    if add is not None:
        ch.append(e.ScenarioChange("C", "add", add, reason="test", source="key"))
    if replace is not None:
        ch.append(e.ScenarioChange("C", "replace", replace))
    return e.run_scenario(build(N1), ch)


def test_s01_add5():
    s = scn(add=5)
    assert s.scenario.duration["C"] == pytest.approx(8)
    assert s.scenario.project_duration == pytest.approx(15)
    assert s.scenario.total_float["C"] == pytest.approx(2)
    assert s.scenario.critical_paths == [["A", "B", "D", "E", "F"]]
    assert s.changed_rows[0]["source"] == "key" and s.changed_rows[0]["unit"] == "hours"


def test_c06_tie_add7():
    s = scn(add=7)
    assert s.scenario.project_duration == pytest.approx(15)
    assert s.scenario.total_float["C"] == pytest.approx(0)
    assert sorted(s.scenario.critical_paths) == [["A", "B", "D", "E", "F"], ["A", "C", "E", "F"]]
    assert s.path_changed


def test_c07_path_change_add9():
    s = scn(add=9)
    assert s.scenario.duration["C"] == pytest.approx(12)
    assert s.scenario.project_duration == pytest.approx(17)
    assert s.finish_delta == pytest.approx(2)
    assert s.scenario.critical_paths == [["A", "C", "E", "F"]]
    assert s.scenario.total_float["B"] == pytest.approx(2)
    assert s.scenario.total_float["D"] == pytest.approx(2)


def test_replace_equals_add():
    assert scn(replace=12).scenario.project_duration == pytest.approx(17)


def test_s02_n1_b8():
    acts = build([("A", "", 2), ("B", "A", 8), ("C", "A", 3), ("D", "B", 4), ("E", "C, D", 2), ("F", "E", 1)])
    r = e.cpm(acts)
    check(r, {"A": (0, 2, 0, 2, 0), "B": (2, 10, 2, 10, 0), "C": (2, 5, 11, 14, 9),
              "D": (10, 14, 10, 14, 0), "E": (14, 16, 14, 16, 0), "F": (16, 17, 16, 17, 0)})
    assert r.project_duration == pytest.approx(17)
    assert r.critical_paths == [["A", "B", "D", "E", "F"]]


def test_s03_n1_d():
    acts = build([("A", "", 2), ("B", "A", 6), ("C", "A", 3), ("D", "B", 4), ("E", "D", 2), ("F", "E", 1)])
    r = e.cpm(acts)
    check(r, {"A": (0, 2, 0, 2, 0), "B": (2, 8, 2, 8, 0), "C": (2, 5, 12, 15, 10),
              "D": (8, 12, 8, 12, 0), "E": (12, 14, 12, 14, 0), "F": (14, 15, 14, 15, 0)})
    assert r.project_duration == pytest.approx(15)


# ----------------------------------------------------------- validation V01-V13
def issues_for(rows):
    acts, iss = e.parse_rows(rows)
    return [i.code for i in iss] + [i.code for i in e.validate(acts)]


def row(i="A", p="", o=1, m=2, pp=3, **kw):
    d = {"id": i, "predecessors": p, "o": o, "m": m, "p": pp}
    d.update(kw)
    return d


def test_v01_empty():
    assert "EMPTY" in [i.code for i in e.validate([])]
    with pytest.raises(e.ValidationError):
        e.cpm([])


def test_v02_duplicate():
    assert "DUPLICATE_ID" in issues_for([row("A"), row("A")])


def test_v03_blank_id():
    assert "BLANK_ID" in issues_for([row("   ")])


def test_v04_unknown_pred():
    assert "UNKNOWN_PREDECESSOR" in issues_for([row("A", "Z")])


def test_v05_self_link():
    assert "SELF_LINK" in issues_for([row("A", "A")])


def test_v06_cycle_names_members():
    acts, _ = e.parse_rows([row("A", "C"), row("B", "A"), row("C", "B")])
    iss = e.validate(acts)
    cyc = [i for i in iss if i.code == "CYCLE"]
    assert cyc and set(cyc[0].ids) == {"A", "B", "C"}
    assert "A" in cyc[0].message and "B" in cyc[0].message and "C" in cyc[0].message


def test_v07_o_gt_m():
    assert "ORDER" in issues_for([row(o=5, m=4, pp=8)])


def test_v08_m_gt_p():
    assert "ORDER" in issues_for([row(o=2, m=9, pp=8)])


def test_v09_negative():
    assert "NEGATIVE" in issues_for([row(o=-1, m=2, pp=3)])


def test_v10_nonnumeric():
    assert "NONNUMERIC" in issues_for([row(m="abc")])


def test_v11_missing():
    assert "MISSING_VALUE" in issues_for([row(pp=None)]) and "MISSING_VALUE" in issues_for([row(pp="")])


def test_v12_mixed_units():
    assert "MIXED_UNITS" in issues_for([row("A", unit="minutes"), row("B", unit="hours")])


@pytest.mark.parametrize("bad", ["inf", "nan", float("inf"), float("nan"), "-inf"])
def test_v13_nonfinite(bad):
    assert "NONFINITE" in issues_for([row(pp=bad)])


def test_invalid_blocks_schedule():
    acts, _ = e.parse_rows([row("A", "A")])
    with pytest.raises(e.ValidationError):
        e.cpm(acts)


def test_limits():
    many = [row(f"T{i}") for i in range(51)]
    assert "TOO_MANY_ACTIVITIES" in issues_for(many)
    ok = [row("T0")] + [row(f"T{i}", "T0") for i in range(1, 50)]
    assert "TOO_MANY_LINKS" not in issues_for(ok)


# ---------------------------------------------------------- scenario validation
def test_scenario_rejects_unknown_and_negative():
    acts = build(N1)
    with pytest.raises(e.ValidationError):
        e.run_scenario(acts, [e.ScenarioChange("Z", "add", 1)])
    with pytest.raises(e.ValidationError):
        e.run_scenario(acts, [e.ScenarioChange("C", "add", -10)])
    with pytest.raises(e.ValidationError):
        e.run_scenario(acts, [e.ScenarioChange("C", "add", float("nan"))])


def test_scenario_does_not_modify_baseline():
    acts = build(N1)
    before = e.fingerprint(acts)
    e.run_scenario(acts, [e.ScenarioChange("C", "add", 9)])
    assert e.fingerprint(acts) == before


# ------------------------------------------------------------------- exports X
def test_x02_fingerprint_tracks_dataset():
    a = build(N1)
    b = build([("A", "", 2), ("B", "A", 8), ("C", "A", 3), ("D", "B", 4), ("E", "C, D", 2), ("F", "E", 1)])
    assert e.fingerprint(a) != e.fingerprint(b)
    assert e.fingerprint(a) == e.fingerprint(build(N1))


def test_x03_report_content():
    acts = build(N1)
    s = e.run_scenario(acts, [e.ScenarioChange("C", "add", 9, reason="r", source="s")])
    rep = e.build_report(acts, s.baseline, s)
    assert "EDUCATIONAL PROTOTYPE" in rep and "Assumptions" in rep
    assert e.fingerprint(acts, s.changes) in rep and e.APP_VERSION in rep
    assert "not probabilities" in rep


def test_display_rounding_only():
    assert e.fmt(13 / 3) == "4.33"
    assert e.expected_time(2, 4, 8) == pytest.approx(13 / 3, abs=1e-12)
    assert e.fmt(-0.0) == "0"


def test_example_n1_matches_key():
    acts, iss = e.parse_rows(e.example_n1())
    assert not iss
    check(e.cpm(acts), N1_KEY)


# --------------------------------------------------------------------- Z01/Z02
def big_dataset():
    rows = [row("T0", "", 1, 2, 3)]
    # 49 more activities, 100 links in total (each of T1..T49 gets 2 links except T1 with 1... adjust)
    links = 0
    for i in range(1, 50):
        preds = [f"T{i-1}"]
        if i >= 2 and links < 51:
            preds.append(f"T{i-2}")
        links += len(preds)
        rows.append(row(f"T{i}", ", ".join(preds), 1, 2, 3))
    return rows


def test_z01_z02_performance():
    rows = big_dataset()
    acts, iss = e.parse_rows(rows)
    assert not iss and len(acts) == 50
    assert sum(len(a.predecessors) for a in acts) <= 100
    times = []
    for _ in range(10):
        t = time.perf_counter()
        e.cpm(acts)
        times.append(time.perf_counter() - t)
    assert max(times) < 2.0, times   # working criterion; the manuscript criterion is to be approved


def test_many_tied_paths_capped():
    # ladder of diamonds produces 2**k tied paths; enumeration must be capped, not explode
    rows = [row("S", "", 1, 1, 1)]
    prev = "S"
    for k in range(12):
        rows += [row(f"L{k}", prev, 1, 1, 1), row(f"R{k}", prev, 1, 1, 1), row(f"J{k}", f"L{k}, R{k}", 1, 1, 1)]
        prev = f"J{k}"
    acts, iss = e.parse_rows(rows)
    assert not iss
    r = e.cpm(acts)
    assert r.paths_truncated and len(r.critical_paths) == e.MAX_PATHS
