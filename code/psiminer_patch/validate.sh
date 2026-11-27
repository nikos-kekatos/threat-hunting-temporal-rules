#!/bin/bash
# Fixed PSI-Miner must reproduce the original binary's rule file on every run the original completed.
# For each mining dir: copy traces + hunt.conf to a temp dir, run code/psiminer_fixed/psiMiner with the run's bias,
# compare hunt-assertions.txt byte for byte with the stored one.   usage: validate.sh DIR...
FIX=$(cd "$(dirname "$0")" && pwd)/psiMiner
T=${TMPDIR:-/tmp}/psi_validate.$$; mkdir -p "$T"
for d in "$@"; do
  grep -q "Completed PSI-Mining" "$d/hunt.conf.log" 2>/dev/null || { echo "SKIP (original did not complete) $d"; continue; }
  b=0; case "$d" in *_b1*) b=1;; esac
  w="$T/$(echo "$d" | tr '/' '_')"; mkdir -p "$w/logs"
  cp "$d"/*.csv "$d/hunt.conf" "$d/translate.py" "$w/" 2>/dev/null
  ( cd "$w" && if [ $b = 1 ]; then "$FIX" hunt.conf 1; else "$FIX" hunt.conf; fi > run.log 2>&1 ); rc=$?
  if [ ! -f "$w/hunt.conf" ] || ! ls "$w"/*.csv >/dev/null 2>&1; then echo "NOINPUT $d";
  elif cmp -s "$w/hunt-assertions.txt" "$d/hunt-assertions.txt"; then echo "SAME rc=$rc bias=$b $d"; else echo "DIFF rc=$rc bias=$b $d"; fi
  rm -r "$w"
done
rmdir "$T" 2>/dev/null
