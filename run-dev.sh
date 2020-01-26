#!/bin/bash
# create empty line distance from previous run
# for improved readibility of output
printf "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"
printf "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"

# Dir to this script, e.g. /home/user/bin/
SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
echo $SCRIPTPATH

# check if setup files have been touched recently
SETUP_PY_MOD=$(expr $(expr $(date +%s) - $(date -r "$SCRIPTPATH/src/setup.py" +"%s")) / 60)
SETUP_CFG_MOD=$(expr $(expr $(date +%s) - $(date -r "$SCRIPTPATH/src/setup.cfg" +"%s")) / 60)

# set quick exit and verbose shell output
# set -ex

if [ 2 -gt $SETUP_PY_MOD ] || [ 2 -gt $SETUP_CFG_MOD ]; then
  echo "Installing peerjs"
  pip3 install --editable src
fi

python3 $SCRIPTPATH/http-proxy.py
