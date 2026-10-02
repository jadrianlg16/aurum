"""``python -m aurum.demo`` — seed synthetic demo workspaces into AURUM_DATA_DIR.

No flag: build the tax-flavoured ``demo-mx`` workspace (the default).
``--personal``: seed the from-scratch ``demo-personal`` workspace. ``--stamp-demos``: retrofit
``profile.demo=true`` onto any ``demo-*`` workspace missing it. ``--organizer``: the demo-mx organizer
half (recurring bank lines + commitments + auto-accept), moved out of the Docker entrypoint's inline
Python. ``--refresh``: demo-mx pf_accounts + stamps + demo-personal, all idempotent — the one the
entrypoint runs on every boot.
"""

from __future__ import annotations

import argparse
import json
import os

from ..core.config import settings
from .generate import WS_ID, build_demo


def main() -> int:
    parser = argparse.ArgumentParser(prog="aurum.demo", description="Seed synthetic demo workspaces.")
    parser.add_argument("--data-dir", default=None, help="override AURUM_DATA_DIR")
    parser.add_argument("--force", action="store_true", help="rebuild demo-mx even if it exists")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--personal", action="store_true", help="seed demo-personal only")
    parser.add_argument("--stamp-demos", action="store_true", help="set profile.demo=true on demo-* workspaces")
    parser.add_argument("--organizer", action="store_true", help="seed demo-mx's organizer data")
    parser.add_argument("--refresh", action="store_true", help="demo-mx pf_accounts + stamps + demo-personal")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["AURUM_DATA_DIR"] = args.data_dir

    if args.personal:
        from .personal import seed_demo_personal

        data = seed_demo_personal()
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str) if args.json else f"demo-personal: {data}")
        return 0

    if args.stamp_demos:
        from .personal import stamp_demos

        stamped = stamp_demos()
        print(json.dumps(stamped) if args.json else f"stamped: {stamped}")
        return 0

    if args.organizer:
        from .personal import seed_demo_organizer

        report = seed_demo_organizer()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str) if args.json else f"organizer demo: {report}")
        return 0

    if args.refresh:
        from .extras import register_pf_accounts
        from .personal import reanchor_demo_trials, seed_demo_personal, stamp_demos

        result = {
            "pf_accounts": register_pf_accounts("demo-mx"),
            "stamped": stamp_demos(),
            "trials_reanchored": reanchor_demo_trials(),
            "personal": seed_demo_personal(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str) if args.json else f"refresh: {result}")
        return 0

    data = build_demo(args.data_dir, force=args.force)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"workspace {WS_ID} ready in {settings().workspace_dir(WS_ID)}")
        print(f"  {data['documents']} CFDI · {data.get('transactions_posted', 0)} transacciones · {len(data['expected_diffs'])} diferencias esperadas")
        for diff in data["expected_diffs"]:
            print(f"  - {diff['kind']}: {diff['amount']} {data['currency']} {diff['documents']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
