"""Educational PERT/CPM prototype (Streamlit).

Run:  streamlit run app.py
All calculations live in engine.py (tested against the manuscript's answer keys).
State is kept in the browser session only; nothing is stored on a server.
"""
import io

import pandas as pd
import streamlit as st

import engine as e
import diagram

st.set_page_config(page_title="PERT/CPM Educational Prototype", page_icon="🛠", layout="wide")

COLS = ["id", "name", "predecessors", "o", "m", "p", "milestone"]
SCN_COLS = ["activity", "mode", "value", "reason", "source", "reviewer", "status"]
UNITS = ["hours", "minutes", "days"]


# ------------------------------------------------------------------ session state
def init_state():
    ss = st.session_state
    ss.setdefault("gen", 0)                       # bumps to reset the editors
    ss.setdefault("unit", e.DEFAULT_UNIT)
    ss.setdefault("base_df", pd.DataFrame({c: pd.Series(dtype="object") for c in COLS}))
    ss.setdefault("scn_df", pd.DataFrame({c: pd.Series(dtype="object") for c in SCN_COLS}))
    ss.setdefault("notice", None)
    pending = ss.pop("_pending_unit", None)   # applied before the selectbox is created
    if pending:
        ss.unit = pending


def rows_to_df(rows):
    df = pd.DataFrame(rows)
    for c in COLS:
        if c not in df:
            df[c] = "" if c != "milestone" else False
    df = df[COLS].copy()
    for c in ("id", "name", "predecessors", "o", "m", "p"):
        df[c] = df[c].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else (f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)))
    df["milestone"] = df["milestone"].map(e._truthy).astype(bool)
    return df


def load_rows(rows, unit=None):
    ss = st.session_state
    ss.base_df = rows_to_df(rows)
    ss.scn_df = pd.DataFrame({c: pd.Series(dtype="object") for c in SCN_COLS})
    if unit:
        ss["_pending_unit"] = unit
    ss.gen += 1


def load_example():
    load_rows(e.example_n1(), unit="hours")


def reset_all():
    ss = st.session_state
    ss.base_df = pd.DataFrame({c: pd.Series(dtype="object") for c in COLS})
    ss.scn_df = pd.DataFrame({c: pd.Series(dtype="object") for c in SCN_COLS})
    ss["_pending_unit"] = e.DEFAULT_UNIT
    ss.gen += 1
    ss.notice = "Inputs and results were cleared."


def show_issues(issues):
    for i in issues:
        st.error(i.message)


# ----------------------------------------------------------------------- sidebar
init_state()
with st.sidebar:
    st.header("PERT/CPM prototype")
    st.caption(f"Version {e.APP_VERSION}")
    st.warning(e.EDUCATIONAL_STATEMENT)
    st.selectbox("Time unit for this dataset", UNITS, key="unit",
                 help="One unit for every activity. Change it before entering durations.")
    st.button("Load example network N1", on_click=load_example, use_container_width=True)
    st.button("Reset (clear inputs and results)", on_click=reset_all, use_container_width=True)
    up = st.file_uploader("Import activities from CSV", type=["csv"],
                          help="Columns: id, name, predecessors, o, m, p, milestone, unit (optional).")
    if up is not None and st.session_state.get("last_upload") != (up.name, up.size):
        try:
            raw = pd.read_csv(up, dtype=str, keep_default_na=False)
            raw.columns = [c.strip().lower() for c in raw.columns]
            missing = [c for c in ("id", "o", "m", "p") if c not in raw.columns]
            if missing:
                st.error("The CSV is missing required column(s): " + ", ".join(missing))
            else:
                units = sorted({u.strip().lower() for u in raw.get("unit", pd.Series([], dtype=str)) if u.strip()})
                if len(units) > 1:
                    st.error("The CSV mixes time units (" + ", ".join(units) + "). Use one unit for the whole dataset.")
                else:
                    if len(raw) > e.MAX_ACTIVITIES:
                        st.warning(f"The file has {len(raw)} rows; the limit is {e.MAX_ACTIVITIES}. It was loaded so you can see the error.")
                    load_rows(raw.to_dict("records"), unit=units[0] if units and units[0] in UNITS else None)
                    st.session_state["last_upload"] = (up.name, up.size)
                    st.rerun()
        except Exception as exc:  # unreadable file
            st.error(f"Could not read the CSV: {exc}")
    st.download_button("Download CSV template", data="id,name,predecessors,o,m,p,milestone\nA,Open access panels,,2,2,2,\n",
                       file_name="pertcpm_template.csv", mime="text/csv", use_container_width=True)

st.title("Web-based PERT/CPM scheduling prototype")
st.info("Educational use only. Durations are in the unit you selected; links are finish-to-start with zero lag.")
if st.session_state.notice:
    st.success(st.session_state.notice)
    st.session_state.notice = None

tab_in, tab_pert, tab_cpm, tab_scn, tab_diag, tab_rep = st.tabs(
    ["1 · Input", "2 · PERT", "3 · CPM", "4 · Scenario", "5 · Diagram", "6 · Report"])

# ------------------------------------------------------------------------ input
with tab_in:
    st.subheader("Activities")
    st.caption("Enter predecessors as comma-separated IDs (leave blank for none). "
               "O, M, P are optimistic, most likely, pessimistic times; for a single estimate enter the same value in all three. "
               "Tick *milestone* only for a zero-duration event (O = M = P = 0).")
    edited = st.data_editor(
        st.session_state.base_df, key=f"editor_{st.session_state.gen}", num_rows="dynamic",
        use_container_width=True, hide_index=True,
        column_config={
            "id": st.column_config.TextColumn("ID", required=False),
            "name": st.column_config.TextColumn("Name / description"),
            "predecessors": st.column_config.TextColumn("Predecessors"),
            "o": st.column_config.TextColumn("O"),
            "m": st.column_config.TextColumn("M"),
            "p": st.column_config.TextColumn("P"),
            "milestone": st.column_config.CheckboxColumn("Milestone"),
        })

records = e.clean_rows(edited.to_dict("records")) if edited is not None else []
for r in records:
    r["unit"] = st.session_state.unit
acts, parse_issues = e.parse_rows(records, default_unit=st.session_state.unit)
# Report entry problems first; structural checks run once every row parses.
all_issues = list(parse_issues) if parse_issues else e.validate(acts)

base = None
if not records:
    all_issues = [e.Issue("EMPTY", "No activities were entered; no schedule was calculated. Load the example or add rows above.")]
if not all_issues:
    base = e.cpm(acts)

with tab_in:
    if all_issues:
        st.markdown("**Please fix the following before a schedule is calculated:**")
        show_issues(all_issues)
    else:
        st.success(f"Dataset is valid: {len(acts)} activities, {sum(len(a.predecessors) for a in acts)} links. "
                   f"Fingerprint {e.fingerprint(acts)}.")
        st.download_button("Download dataset (CSV)", data=pd.DataFrame(e.to_rows(acts)).to_csv(index=False),
                           file_name=f"pertcpm_{e.fingerprint(acts)}_dataset.csv", mime="text/csv")


def need_valid(tab):
    if base is None:
        tab.info("Enter a valid dataset on the Input tab first.")
        return False
    return True


# ------------------------------------------------------------------------- PERT
with tab_pert:
    if need_valid(st):
        st.subheader("PERT expected times")
        st.latex(r"TE = \frac{O + 4M + P}{6}")
        df = pd.DataFrame(e.pert_table(acts))
        show = df.copy()
        for c in ("O", "M", "P", "TE"):
            show[c] = show[c].map(e.fmt)
        show["milestone"] = show["milestone"].map({True: "Yes", False: ""})
        st.dataframe(show, hide_index=True, use_container_width=True)
        st.caption(f"Values are rounded to {e.DISPLAY_DECIMALS} decimals for display only; calculations use full precision.")

# -------------------------------------------------------------------------- CPM
with tab_cpm:
    if need_valid(st):
        st.subheader("Critical Path Method")
        c1, c2 = st.columns(2)
        c1.metric("Project duration", f"{e.fmt(base.project_duration)} {base.unit}")
        c2.metric("Critical activities", f"{len(base.critical)} of {len(acts)}")
        t = pd.DataFrame(base.table())
        t = t.rename(columns={"duration": "Duration", "float": "Total float", "critical": "Critical"})
        for c in ("Duration", "ES", "EF", "LS", "LF", "Total float"):
            t[c] = t[c].map(e.fmt)
        t["Critical"] = t["Critical"].map({True: "Yes", False: ""})
        st.dataframe(t, hide_index=True, use_container_width=True)
        st.markdown("**Critical path(s):** " + "; ".join(f"`{e.path_text(p)}`" for p in base.critical_paths)
                    + (" *(list truncated)*" if base.paths_truncated else ""))
        if len(base.critical_paths) > 1:
            st.caption("More than one critical path: several routes tie for the longest duration.")
        st.download_button("Download CPM table (CSV)", data=pd.DataFrame(base.table()).to_csv(index=False),
                           file_name=f"pertcpm_{e.fingerprint(acts)}_cpm.csv", mime="text/csv")

# ---------------------------------------------------------------------- scenario
scn_result = None
with tab_scn:
    if need_valid(st):
        st.subheader("What-if scenario")
        st.caption("Add or replace an activity's expected time to see how the finish and critical path respond. "
                   "These are illustrative assumptions, not predictions, and survey scores never set the values. "
                   "Results are conditional completion times, not probabilities.")
        ids = [a.id for a in acts]
        sedit = st.data_editor(
            st.session_state.scn_df, key=f"scn_{st.session_state.gen}", num_rows="dynamic",
            use_container_width=True, hide_index=True,
            column_config={
                "activity": st.column_config.SelectboxColumn("Activity", options=ids),
                "mode": st.column_config.SelectboxColumn("Mode", options=["add", "replace"],
                                                         help="add: add this many units to the expected time; replace: set the duration."),
                "value": st.column_config.TextColumn(f"Value ({base.unit})"),
                "reason": st.column_config.TextColumn("Reason / assumption"),
                "source": st.column_config.TextColumn("Source of assumption"),
                "reviewer": st.column_config.TextColumn("Reviewed by"),
                "status": st.column_config.SelectboxColumn("Status", options=["Illustrative", "Reviewed (basis stated)"]),
            })
        recs = e.clean_rows(sedit.to_dict("records"))
        changes, scn_issues = [], []
        for r in recs:
            val, err = e._to_number(r.get("value"))
            if not r.get("activity") or not r.get("mode") or err:
                scn_issues.append(e.Issue("INCOMPLETE", f"Scenario row for '{r.get('activity') or '?'}' needs an activity, a mode and a numeric value."))
                continue
            changes.append(e.ScenarioChange(
                str(r["activity"]), str(r["mode"]), val, reason=str(r.get("reason") or ""),
                source=str(r.get("source") or ""), reviewer=str(r.get("reviewer") or ""),
                status=str(r.get("status") or "Illustrative")))
        show_issues(scn_issues)
        if changes and not scn_issues:
            try:
                scn_result = e.run_scenario(acts, changes)
            except e.ValidationError as exc:
                show_issues(exc.issues)
        if scn_result:
            b, s = scn_result.baseline, scn_result.scenario
            m1, m2, m3 = st.columns(3)
            m1.metric("Baseline finish", f"{e.fmt(b.project_duration)} {b.unit}")
            m2.metric("Scenario finish", f"{e.fmt(s.project_duration)} {b.unit}", delta=f"{e.fmt(scn_result.finish_delta)} {b.unit}",
                      delta_color="inverse")
            m3.metric("Critical path changed", "Yes" if scn_result.path_changed else "No")
            st.markdown("**Baseline critical path(s):** " + "; ".join(f"`{e.path_text(p)}`" for p in b.critical_paths))
            st.markdown("**Scenario critical path(s):** " + "; ".join(f"`{e.path_text(p)}`" for p in s.critical_paths))
            cmp = pd.DataFrame(scn_result.comparison())
            for c in cmp.columns:
                if c.startswith(("duration", "ES", "EF", "float")):
                    cmp[c] = cmp[c].map(e.fmt)
            for c in ("critical_base", "critical_scn"):
                cmp[c] = cmp[c].map({True: "Yes", False: ""})
            st.dataframe(cmp, hide_index=True, use_container_width=True)
            st.caption(f"Scenario fingerprint {e.fingerprint(acts, changes)} (dataset + scenario).")
            st.download_button("Download scenario comparison (CSV)", data=pd.DataFrame(scn_result.comparison()).to_csv(index=False),
                               file_name=f"pertcpm_{e.fingerprint(acts, changes)}_scenario.csv", mime="text/csv")
        elif not changes:
            st.info("Add a row above to run a scenario.")

# ----------------------------------------------------------------------- diagram
with tab_diag:
    if need_valid(st):
        st.subheader("Network diagram")
        choices = ["Baseline"] + (["Scenario"] if scn_result else [])
        which = st.radio("Show", choices, horizontal=True)
        res = scn_result.scenario if (which == "Scenario" and scn_result) else base
        fig = diagram.draw(res, which, {a.id: a.name for a in acts})
        st.pyplot(fig, clear_figure=True)
        buf = io.BytesIO()
        fig2 = diagram.draw(res, which, {a.id: a.name for a in acts})
        fig2.savefig(buf, format="png", dpi=200)
        st.download_button("Download diagram (PNG)", data=buf.getvalue(),
                           file_name=f"pertcpm_{e.fingerprint(acts, scn_result.changes if (which == 'Scenario' and scn_result) else None)}_diagram.png",
                           mime="image/png")

# ------------------------------------------------------------------------ report
with tab_rep:
    if need_valid(st):
        st.subheader("Report")
        report = e.build_report(acts, base, scn_result)
        st.markdown(report)
        st.download_button("Download report (Markdown)", data=report,
                           file_name=f"pertcpm_{e.fingerprint(acts, scn_result.changes if scn_result else None)}_report.md",
                           mime="text/markdown")
