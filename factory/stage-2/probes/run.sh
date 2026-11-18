#!/bin/bash
# usage: run.sh <label> [host|isolated] [extra pytest args]
# Exports HEAD of the repo into ~/hack/<label>/, runs the shipped stage-1+2 suites and these probes.
set -e
L=$1; MODE=${2:-host}; shift 2 || true
REPO=/mnt/c/Users/IYANUOLUWA/band-work/result
SRC=$HOME/hack/$L
rm -rf $SRC; mkdir -p $SRC
(cd $REPO && git archive HEAD stage-1 stage-2) | tar -x -C $SRC
H=$HOME/hack/sf-buildathon-2026
T=$H/challenges/dossier/test
mkdir -p $T/exam_s2 && cp $REPO/factory/stage-2/probes/{conftest.py,probe_api.py,probe_ui.py} $T/exam_s2/
cd $H && . .venv/bin/activate
export SHOTS=$REPO/factory/stage-2/screens
rm -rf $HOME/hack/checks/$L
timeout 3000 python -m harness run --track dossier --build $SRC/stage-2 --previous-build $SRC/stage-1 \
  --implementation-stage 2 --stages 2 --mode $MODE --out $HOME/hack/checks/$L \
  $T/exam_s2/probe_api.py $T/exam_s2/probe_ui.py "$@" 2>&1 | tail -15
