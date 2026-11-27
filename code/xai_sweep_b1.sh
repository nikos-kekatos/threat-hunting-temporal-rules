#!/bin/bash
# Add-on to xai_sweep.sh: PSIMiner with explanation bias +1 (explain the true target) on the same
# extracts and splits, into results_xai/<config>/mine_b1/; then compare_xai for L3 (and L8 on gap configs).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
PY=$HERE/.venv/bin/python
R=$HERE/../results_xai
for d in "$R"/*_s[0-9]; do
  name=$(basename "$d"); cfg=${name%_s*}
  case $cfg in noise*) pl=SYN_DOM,DPORT_MANY,2 ;; gap1-*) pl=SYN_DOM,DPORT_MANY,1-${cfg#gap1-} ;; esac
  for m in mine mine_b1; do
    if [ $m = mine_b1 ] && [ ! -e "$d/mine_b1/results/hunt_eval.json" ]; then
      $PY "$HERE/mine.py" "$d/extract" "$d/mine_b1" --psiminer "$PSI" --drop-constant --bias 1 2> "$d/mine_b1.log"
      $PY "$HERE/evaluate.py" "$d/mine_b1" > "$d/eval_b1.txt"
    fi
    $PY "$HERE/compare_xai.py" "$d/$m" --lags 3 --out xai_L3.json --planted $pl > "$d/xai_L3_$m.txt"
    case $cfg in gap1-*) $PY "$HERE/compare_xai.py" "$d/$m" --lags 8 --out xai_L8.json --planted $pl > "$d/xai_L8_$m.txt" ;; esac
  done
  echo "done $name"
done
echo ALL DONE
