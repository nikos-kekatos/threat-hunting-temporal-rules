#!/bin/bash
# Re-mine the runs lost to a full disk (dc s4, dc_b1 s3, s4), then score every unscored split, two at a time.
cd "$(dirname "$0")/../.."
PY=code/.venv/bin/python; PSI=$(pwd)/code/psiminer_fixed/psiMiner; O=results_stats_2026-10-27/psiminer_mawi
mine() { $PY code/mine.py results_fix_$1/extract results_fix_$1/mine_$2 --psiminer "$PSI" --split-salt $2 --drop-constant --bias $3 2> results_fix_$1/mine_$2.log; echo "$1 $2 remine exit $? $(grep -c CRASHED results_fix_$1/mine_$2.log) crashed-lines"; }
mine dc s4 0 & mine dc_b1 s3 1 & mine dc_b1 s4 1 & wait
for cfg in dc dc_b1; do for s in s0 s1 s2 s3 s4; do
  [ -f $O/${cfg}_$s.json ] && continue
  while [ $(pgrep -f psiminer_mawi_1027.py | wc -l) -ge 2 ]; do sleep 10; done
  $PY code/psiminer_mawi_1027.py results_fix_$cfg/mine_$s $O/${cfg}_$s.json &
  sleep 2
done; done
wait; echo FDONE
