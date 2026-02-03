#!/bin/bash
# Wait until X is ready (up to 30 seconds)
for i in $(seq 1 30); do
  DISPLAY=:0 XAUTHORITY=/home/admin/.Xauthority xset -q >/dev/null 2>&1 && exit 0
  sleep 1
done
exit 1

