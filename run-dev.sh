# Dir to this script, e.g. /home/user/bin/
SCRIPTPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
echo $SCRIPTPATH

# set quick exit and verbose shell output
# set -ex

# check if setup files have been touched recently
SETUP_PY_MOD=$(expr $(expr $(date +%s) - $(date -r "$SCRIPTPATH/src/setup.py" +"%s")) / 60)
SETUP_CFG_MOD=$(expr $(expr $(date +%s) - $(date -r "$SCRIPTPATH/src/setup.cfg" +"%s")) / 60)

if [ 2 -gt $SETUP_PY_MOD ] || [ 2 -gt $SETUP_CFG_MOD ]; then
  echo "Installing peerjs"
  pip3 install --editable src
fi

python3 $SCRIPTPATH/cli.py
