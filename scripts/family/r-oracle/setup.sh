#!/bin/bash
# Builds the R environment on the test machine (pixi in ~/.pixi/bin), in tmux:
# writes setup.log, then setup.done with the exit status.
cd "$(dirname "$0")" || exit 1
export PATH=$HOME/.pixi/bin:$PATH
{ pixi install && pixi run Rscript install.R; } > setup.log 2>&1
echo "exit $?" > setup.done
