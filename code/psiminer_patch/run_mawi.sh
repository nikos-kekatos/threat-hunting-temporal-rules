#!/bin/bash
# MAWI mining with the fixed PSI-Miner (2026-10-27): same settings as results_dc (bias 0) and dc_b1 (bias +1),
# constant predicates dropped, five split salts. Mining only (evaluation by psiminer_mawi_1027.py, on-disk SQL).
cd "$(dirname "$0")/../.."
PY=code/.venv/bin/python; PSI=$(pwd)/code/psiminer_fixed/psiMiner
run() { R=results_fix_$1; mkdir -p $R; [ -e $R/extract ] || ln -s ../results/extract $R/extract
  for s in s0 s1 s2 s3 s4; do
    $PY code/mine.py $R/extract $R/mine_$s --psiminer "$PSI" --split-salt $s --drop-constant --bias $2 2> $R/mine_$s.log
    echo "$1 $s exit $? $(grep -c CRASHED $R/mine_$s.log) crashed-lines"; done; }
run dc 0 &
run dc_b1 1 &
wait; echo ALLDONE
