#!/bin/sh
# Runs as root exactly long enough to make /data usable by the unprivileged `aurum` user, then
# drops to it with every capability cleared and execs /entrypoint.sh.
#
#   AURUM_DATA_DIR    (default /data)  the bind-mounted data volume
#   AURUM_CHOWN_DATA  (default 0)      1 = recursive chown of the whole volume (slow on big data dirs;
#                                       normally only the top level + secrets/vault need it)
#   AURUM_RUN_AS_ROOT (default 0)      1 = skip the drop (debugging only)
#
# Docker Desktop on Windows/macOS bind mounts ignore chown/chmod: those calls are best effort and
# the observed modes are reported, never assumed.
set -e
DATA_DIR="${AURUM_DATA_DIR:-/data}"
USER_NAME="${AURUM_USER:-aurum}"

if [ "$(id -u)" != "0" ] || [ "${AURUM_RUN_AS_ROOT:-0}" = "1" ]; then
  exec /entrypoint.sh
fi

mkdir -p "$DATA_DIR" "$DATA_DIR/secrets" "$DATA_DIR/vault"
if [ "${AURUM_CHOWN_DATA:-0}" = "1" ]; then
  chown -R "$USER_NAME:$USER_NAME" "$DATA_DIR" 2>/dev/null || echo "drop-privileges: recursive chown of $DATA_DIR not permitted (bind mount?)"
else
  chown "$USER_NAME:$USER_NAME" "$DATA_DIR" 2>/dev/null || echo "drop-privileges: chown $DATA_DIR not permitted (bind mount?)"
  for d in "$DATA_DIR"/*; do
    [ -e "$d" ] && chown "$USER_NAME:$USER_NAME" "$d" 2>/dev/null || true
  done
  # Workspaces are the ledger write targets and are small: a tree created by an older image that ran
  # as root would otherwise stay root-owned and every write (a movement in `personal`) would
  # fail once the API runs as $USER_NAME. Recursive here, always; the rest of /data stays opt-in.
  for w in "$DATA_DIR"/workspaces/*; do
    [ -d "$w" ] && chown -R "$USER_NAME:$USER_NAME" "$w" 2>/dev/null || true
  done
fi
chmod 700 "$DATA_DIR/secrets" "$DATA_DIR/vault" 2>/dev/null || echo "drop-privileges: chmod 700 secrets/vault not permitted (bind mount?)"
echo "drop-privileges: $(ls -ld "$DATA_DIR" "$DATA_DIR/secrets" "$DATA_DIR/vault" | tr '\n' ';')"

# setpriv clears the bounding set and every ambient/inheritable cap: the app's CapEff is 0.
exec setpriv --reuid="$USER_NAME" --regid="$USER_NAME" --init-groups --inh-caps=-all --bounding-set=-all /entrypoint.sh
