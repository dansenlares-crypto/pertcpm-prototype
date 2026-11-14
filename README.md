# PERT/CPM Educational Prototype (v0.1.0-prototype)

Companion tool for "Human Factor Perceptions and Maintenance Scheduling Scenarios Using a Web-Based PERT/CPM Prototype".
**Educational use only.** Not for planning, releasing, or certifying real maintenance work. Survey scores never set durations.

## Run
```
pip install -r requirements.txt
streamlit run app.py
```
## Test (verifies the Appendix C answer keys and Appendix D cases)
```
python -m pytest -q
```
## Files
- `engine.py` validation, PERT, CPM, tie-aware critical paths, scenarios, fingerprint, report (no Streamlit dependency)
- `diagram.py` static network diagram; `app.py` Streamlit interface (Input, PERT, CPM, Scenario, Diagram, Report)
- `tests/test_engine.py` pytest; `sample_data/` example CSVs

## Declared scope
Activity-on-node, finish-to-start, zero lag, one time unit per dataset (hours default), start at zero, no resources or calendars,
max 50 activities / 100 links, session-only (no server storage). TE = (O+4M+P)/6 at full precision; display rounded to 2 decimals.
Scenario mode `add` adds units to the expected time; `replace` sets it. Results are conditional completion times, not probabilities.
Critical-path listing is capped at 1000 paths (flagged when truncated). Tolerance for criticality 1e-9; test tolerance 1e-6.

## To record at build freeze (manuscript Appendix B)
Python, Streamlit, NetworkX, Pandas, NumPy, Matplotlib versions; OS; browser; deployment route; the approved performance criterion for Z01/Z02
(tests currently use a working limit of 2 s per run).
