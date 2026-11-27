#!/bin/bash
# External review 2026-10-21 (reviews/review_2026-10-21.md). Serial, modest compute.
# (1) Anchors selected on training/validation hosts, frozen, scored on a separate test half
#     (anchor_frozen.py): delay sweep (results_xai_v2), stray-event configs (results_xai), MAWI five splits.
# (2) Event-level recall by delay (event_recall.py) on the delay sweep.
# (3) One-episode-per-host control: delay sweep regenerated with --episodes 1 -> results_review_1ep/,
#     same pipeline as redo_redteam.sh (PSI-Miner bias +1, drop-constant; compare_xai L3 and L8), plus
#     event_recall.py.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
PY=$HERE/.venv/bin/python
V2=$HERE/../results_xai_v2
E1=$HERE/../results_review_1ep
condense() { for f in $(find "$1" -path '*/logs/log_*.txt' ! -name '*.summary.txt'); do
  grep -E "Ignoring KP|\|=>|SUPPORT|CORRELATION|Completed" "$f" | sort | uniq -c > "${f%.txt}.summary.txt" && rm "$f"; done; }
for seed in 1 2 3; do for g in 2 4 6 8; do
  d=$V2/gap1-${g}_s$seed/mine_b1
  $PY "$HERE/event_recall.py" "$d" --lags 3,8 > "$d/../event_recall.txt"
  for L in 3 8; do $PY "$HERE/anchor_frozen.py" "$d" --lags $L --planted SYN_DOM,DPORT_MANY,1-$g > "$d/../anchor_frozen_L$L.txt"; done
  echo "v2 review gap1-${g}_s$seed $(date +%H:%M)"
done; done
for d in "$HERE"/../results_xai/noise*_s[0-9]; do
  $PY "$HERE/anchor_frozen.py" "$d/mine_b1" --lags 3 --planted SYN_DOM,DPORT_MANY,2 > "$d/anchor_frozen_L3.txt"
  echo "noise review $(basename $d) $(date +%H:%M)"
done
for seed in 1 2 3; do for g in 2 4 6 8; do
  d=$E1/gap1-${g}_s$seed; sp=$((2*g+3))
  $PY "$HERE/synth_control.py" "$d/extract" --gap 1 --gap-max $g --spacing $sp --seed $seed --episodes 1
  $PY "$HERE/mine.py" "$d/extract" "$d/mine_b1" --psiminer "$PSI" --drop-constant --bias 1 2> "$d/mine_b1.log"
  $PY "$HERE/evaluate.py" "$d/mine_b1" > "$d/eval_b1.txt"
  for L in 3 8; do $PY "$HERE/compare_xai.py" "$d/mine_b1" --lags $L --out xai_L$L.json --planted SYN_DOM,DPORT_MANY,1-$g > "$d/xai_L$L.txt"; done
  $PY "$HERE/event_recall.py" "$d/mine_b1" --lags 3,8 > "$d/event_recall.txt"
  condense "$d"; echo "1ep gap1-${g}_s$seed $(date +%H:%M)"
done; done
$PY "$HERE/xai_aggregate.py" "$E1" > /dev/null
R=$HERE/../results_dc
for s in s0 s1 s2 s3 s4; do
  $PY "$HERE/anchor_frozen.py" "$R/mine_$s" --lags 3 > "$R/anchor_frozen_$s.txt"; echo "mawi review $s $(date +%H:%M)"
done
echo ALL DONE
