#!/bin/bash
# Red team 2026-10-20: (1) delay sweep with episode spacing 2G+3 (no benign A-then-B within G+3 s),
# PSIMiner bias +1 + drop-constant, into results_xai_v2; (2) rescore noise configs with the fixed
# compare_xai (anchors from training hosts, per-rule planted check with flag-all margin, SHAP on train);
# (3) MAWI five splits rescored (s0 re-mined so rules.json records the crash). Serial.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
PY=$HERE/.venv/bin/python
V2=$HERE/../results_xai_v2
condense() { for f in $(find "$1" -path '*/logs/log_*.txt' ! -name '*.summary.txt'); do
  grep -E "Ignoring KP|\|=>|SUPPORT|CORRELATION|Completed" "$f" | sort | uniq -c > "${f%.txt}.summary.txt" && rm "$f"; done; }
for seed in 1 2 3; do for g in 2 4 6 8; do
  d=$V2/gap1-${g}_s$seed; sp=$((2*g+3))
  $PY "$HERE/synth_control.py" "$d/extract" --gap 1 --gap-max $g --spacing $sp --seed $seed
  $PY "$HERE/mine.py" "$d/extract" "$d/mine_b1" --psiminer "$PSI" --drop-constant --bias 1 2> "$d/mine_b1.log"
  $PY "$HERE/evaluate.py" "$d/mine_b1" > "$d/eval_b1.txt"
  for L in 3 8; do $PY "$HERE/compare_xai.py" "$d/mine_b1" --lags $L --out xai_L$L.json --planted SYN_DOM,DPORT_MANY,1-$g > "$d/xai_L$L.txt"; done
  condense "$d"; echo "v2 done gap1-${g}_s$seed $(date +%H:%M)"
done; done
$PY "$HERE/xai_aggregate.py" "$V2" > /dev/null
for d in "$HERE"/../results_xai/noise*_s[0-9]; do
  for m in mine mine_b1; do $PY "$HERE/compare_xai.py" "$d/$m" --lags 3 --out xai_L3.json --planted SYN_DOM,DPORT_MANY,2 > "$d/xai_L3_$m.txt"; done
  echo "rescored $(basename $d) $(date +%H:%M)"
done
$PY "$HERE/xai_aggregate.py" "$HERE/../results_xai" > /dev/null
R=$HERE/../results_dc
$PY "$HERE/mine.py" "$R/extract" "$R/mine_s0" --psiminer "$PSI" --split-salt s0 --drop-constant 2> "$R/mine_s0.log"
$PY "$HERE/evaluate.py" "$R/mine_s0" > "$R/eval_s0.txt"
for s in s0 s1 s2 s3 s4; do
  $PY "$HERE/compare_xai.py" "$R/mine_$s" --lags 3 --out xai_L3.json > "$R/xai_$s.txt"; condense "$R/mine_$s"; echo "mawi $s $(date +%H:%M)"
done
echo ALL DONE
