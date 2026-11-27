#!/bin/bash
# Driver for code/compile_rules_1027.py (review 2026-10-27): synthetic checks, then MAWI split 0 (timing).
cd "$(dirname "$0")/.."
PY=code/.venv/bin/python
for d in noise0 noise0.05; do $PY code/compile_rules_1027.py synth_${d}_s1 results_xai/${d}_s1/mine_b1; done
for G in 4 8; do $PY code/compile_rules_1027.py synth_gap1-${G}_s1 results_xai_v2/gap1-${G}_s1/mine_b1; done
$PY code/compile_rules_1027.py mawi_s0 results_dc/mine_s0
echo DONE
