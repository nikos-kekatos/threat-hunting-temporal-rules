#!/bin/bash
# Score fixed-binary MAWI splits in parallel (up to 3), each as soon as its mining has finished; skip splits done.
cd "$(dirname "$0")/../.."
PY=code/.venv/bin/python; O=results_stats_2026-10-27/psiminer_mawi
for cfg in dc dc_b1; do for s in s0 s1 s2 s3 s4; do
  [ -f $O/${cfg}_$s.json ] && continue
  while ! grep -q "^$cfg $s exit" results_stats_2026-10-27/psiminer_fixed_mawi.out; do sleep 15; done
  while [ $(pgrep -f psiminer_mawi_1027.py | wc -l) -ge 3 ]; do sleep 10; done
  $PY code/psiminer_mawi_1027.py results_fix_$cfg/mine_$s $O/${cfg}_$s.json &
  sleep 2
done; done
wait; echo SDONE
