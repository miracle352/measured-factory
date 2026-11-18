#!/bin/bash
# usage: supplied.sh <label> [host|isolated]  : the supplied (harness) suites for stages 1-4 only, no examiner probes
set -e
L=$1; MODE=${2:-host}
REPO=/mnt/c/Users/IYANUOLUWA/band-work/result
SRC=$HOME/hack/$L
rm -rf $SRC; mkdir -p $SRC
(cd $REPO && git archive HEAD stage-3 stage-4) | tar -x -C $SRC
H=$HOME/hack/sf-buildathon-2026
cd $H && . .venv/bin/activate
rm -rf $HOME/hack/checks/$L
timeout 3400 python -m harness run --track dossier --build $SRC/stage-4 --previous-build $SRC/stage-3 \
  --implementation-stage 4 --stages 1 2 3 4 --mode $MODE --out $HOME/hack/checks/$L 2>&1 | tail -30
