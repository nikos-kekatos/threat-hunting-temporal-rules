#!/bin/bash
# Synthetic comparison sweeps: PSIMiner (--drop-constant, bias 0) vs the methods of compare_xai.py.
#   noise: stray A/B seconds at rate n, fixed gap 2;   gap: gap drawn from [1, G], no noise.
# Runs serially (one heavy job at a time). Output: results_xai/<config>/ with mine, eval, compare.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
PY=$HERE/.venv/bin/python
R=$HERE/../results_xai
mkdir -p "$R"
run() {  # name, compare args..., -- synth args...
  local name=$1; shift
  local cmp=(); while [ "$1" != "--" ]; do cmp+=("$1"); shift; done; shift
  local d=$R/$name
  [ -e "$d/mine/results/xai_L3.json" ] && { echo "skip $name"; return; }
  $PY "$HERE/synth_control.py" "$d/extract" "$@"
  $PY "$HERE/mine.py" "$d/extract" "$d/mine" --psiminer "$PSI" --drop-constant 2> "$d/mine.log"
  $PY "$HERE/evaluate.py" "$d/mine" > "$d/eval.txt"
  $PY "$HERE/compare_xai.py" "$d/mine" --lags 3 --out xai_L3.json "${cmp[@]}" > "$d/xai_L3.txt"
  echo "done $name"
}
for seed in 1 2 3; do
  for n in 0 0.01 0.02 0.05 0.1; do
    run noise${n}_s$seed --planted SYN_DOM,DPORT_MANY,2 -- --noise $n --seed $seed
  done
  for g in 2 4 6 8; do
    run gap1-${g}_s$seed --planted SYN_DOM,DPORT_MANY,1-$g -- --gap 1 --gap-max $g --seed $seed
    d=$R/gap1-${g}_s$seed
    [ -e "$d/mine/results/xai_L8.json" ] || \
      $PY "$HERE/compare_xai.py" "$d/mine" --lags 8 --out xai_L8.json --planted SYN_DOM,DPORT_MANY,1-$g > "$d/xai_L8.txt"
  done
done
echo ALL DONE
