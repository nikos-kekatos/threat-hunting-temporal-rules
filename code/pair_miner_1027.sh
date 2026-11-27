#!/bin/bash
# Driver for code/pair_miner_1027.py (review 2026-10-27). Synthetic first, then MAWI five splits.
cd "$(dirname "$0")/.."
PY=code/.venv/bin/python
for n in 0 0.01 0.02 0.05 0.1; do for s in 1 2 3; do
  d=results_xai/noise${n}_s$s/mine_b1; [ -d $d ] && $PY code/pair_miner_1027.py synth_noise${n}_s$s $d --planted 2-2; done; done
for G in 2 4 6 8; do for s in 1 2 3; do
  d=results_xai_v2/gap1-${G}_s$s/mine_b1; [ -d $d ] && $PY code/pair_miner_1027.py synth_gap1-${G}_s$s $d --planted 1-$G
  d=results_review_1ep/gap1-${G}_s$s/mine_b1; [ -d $d ] && $PY code/pair_miner_1027.py synth1ep_gap1-${G}_s$s $d --planted 1-$G; done; done
for k in 0 1 2 3 4; do $PY code/pair_miner_1027.py mawi_s$k results_dc/mine_s$k; done
echo DONE
