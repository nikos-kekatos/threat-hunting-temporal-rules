#!/bin/bash
# Score each fixed-binary MAWI split as soon as its mining finishes (one scorer at a time, on-disk SQLite).
cd "$(dirname "$0")/../.."
PY=code/.venv/bin/python; O=results_stats_2026-10-27/psiminer_mawi
mkdir -p $O
for cfg in dc dc_b1; do for s in s0 s1 s2 s3 s4; do
  while ! grep -q "^$cfg $s exit" results_stats_2026-10-27/psiminer_fixed_mawi.out; do sleep 20; done
  $PY code/psiminer_mawi_1027.py results_fix_$cfg/mine_$s $O/${cfg}_$s.json
done; done
echo SDONE
