#!/bin/bash
# Corrections guide 2026-10-22, item 4.1: Anchors selected inside the training partition
# (fit half / selection half of the training hosts; anchor_trainsel.py), frozen, scored on all held-out hosts.
# Serial, modest compute (~30 s per run). Log: ../results_corrections_2026-10-22.out
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$HERE/.venv/bin/python
for seed in 1 2 3; do for g in 2 4 6 8; do
  d=$HERE/../results_xai_v2/gap1-${g}_s$seed/mine_b1
  for L in 3 8; do $PY "$HERE/anchor_trainsel.py" "$d" --lags $L --planted SYN_DOM,DPORT_MANY,1-$g > "$d/../anchor_trainsel_L$L.txt" 2>/dev/null; done
  echo "v2 trainsel gap1-${g}_s$seed $(date +%H:%M)"
done; done
for d in "$HERE"/../results_xai/noise*_s[0-9]; do
  $PY "$HERE/anchor_trainsel.py" "$d/mine_b1" --lags 3 --planted SYN_DOM,DPORT_MANY,2 > "$d/anchor_trainsel_L3.txt" 2>/dev/null
  echo "noise trainsel $(basename $d) $(date +%H:%M)"
done
R=$HERE/../results_dc
for s in s0 s1 s2 s3 s4; do
  $PY "$HERE/anchor_trainsel.py" "$R/mine_$s" --lags 3 > "$R/anchor_trainsel_$s.txt" 2>/dev/null; echo "mawi trainsel $s $(date +%H:%M)"
done
echo ALL DONE
