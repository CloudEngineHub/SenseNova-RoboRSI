#!/bin/bash
set -euo pipefail
# cv2 is loaded before Kit. Preload Kit's ABI-compatible GLib so system cv2
# cannot select an older GLib that cannot satisfy GPU Foundation's symbols.
glib=(/isaac-sim/extscache/omni.gpu_foundation-*/bin/deps/libglib-2.0.so.0)
[[ ${#glib[@]} == 1 && -f "${glib[0]}" ]]
export LD_PRELOAD="${glib[0]}${LD_PRELOAD:+:$LD_PRELOAD}"
export PYTHONPATH="/isaac-sim/extsDeprecated/omni.isaac.ml_archive/pip_prebundle${PYTHONPATH:+:$PYTHONPATH}"
exec /isaac-sim/python.sh "$@"
