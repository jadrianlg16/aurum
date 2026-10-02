#!/bin/sh
set -e
# Bring the metadata db's schema/migrations up to date before anything else touches it. Fails the boot
# on a migration error rather than starting against a half-migrated database.
python -m aurum.core.db

# Seed the synthetic demo workspace on first boot (never real data), then run API + MCP (HTTP).
if [ "${AURUM_SEED_DEMO:-1}" = "1" ] && [ ! -f "${AURUM_DATA_DIR:-/data}/workspaces/demo-mx/workspace.json" ]; then
  python -m aurum.demo || echo "demo seed skipped (module not ready)"
fi

# Mi dinero demo data (recurring bank lines, commitments) is seeded at boot, not inside build_demo, so the
# tax/demo test baselines stay pristine. Idempotent via the marker file; high-confidence candidates are
# accepted so the hub is populated on first open while a few stay in the setup wizard.
ORG_MARKER="${AURUM_DATA_DIR:-/data}/workspaces/demo-mx/docs/demo-org.json"
if [ "${AURUM_SEED_DEMO:-1}" = "1" ] && [ ! -f "$ORG_MARKER" ]; then
  python -m aurum.demo --organizer || echo "organizer demo seed skipped"
fi

# demo-mx pf_accounts + profile.demo stamps + demo-personal — every boot, all idempotent
# (never a reseed: this only adds what is missing).
if [ "${AURUM_SEED_DEMO:-1}" = "1" ]; then
  python -m aurum.demo --refresh || echo "demo refresh skipped"
fi

if python -c "import aurum.mcp_server.server" 2>/dev/null; then
  aurum-mcp --http &
fi
exec aurum-api
