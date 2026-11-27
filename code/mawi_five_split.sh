#!/bin/bash
# Five-split MAWI comparison (2026-10-20): for splits s1-s4 (s0 done), regenerate the traces with mine.py
# (--drop-constant, bias 0; PSIMiner may crash, which rules.json now records), then evaluate.py and
# compare_xai.py, one split at a time; PSIMiner debug logs condensed after each split.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
PY=$HERE/.venv/bin/python
R=$HERE/../results_dc
for s in s1 s2 s3 s4; do
  echo "== $s $(date +%H:%M)"
  $PY "$HERE/mine.py" "$R/extract" "$R/mine_$s" --psiminer "$PSI" --split-salt $s --drop-constant 2> "$R/mine_$s.log"
  tail -2 "$R/mine_$s.log"
  $PY "$HERE/evaluate.py" "$R/mine_$s" > "$R/eval_$s.txt" || echo "evaluate failed $s"
  $PY "$HERE/compare_xai.py" "$R/mine_$s" --lags 3 --out xai_L3.json > "$R/xai_$s.txt" || echo "compare failed $s"
  for f in $(find "$R/mine_$s" -path '*/logs/log_*.txt' ! -name '*.summary.txt'); do
    grep -E "Ignoring KP|\|=>|SUPPORT|CORRELATION|Completed" "$f" | sort | uniq -c > "${f%.txt}.summary.txt" && rm "$f"
  done
  df -h /System/Volumes/Data | tail -1
done
echo ALL DONE
