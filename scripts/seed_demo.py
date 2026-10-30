"""Seed the ControlIQ synthetic demonstration environment.

Usage (from the repository root, with the backend virtualenv active):

    python scripts/seed_demo.py                  # reset + seed baseline environment
    python scripts/seed_demo.py --with-mfa-failure   # also inject Scenario 1 and run an assessment

The seed is deterministic: entity definitions, scenario timelines and evidence are fixed; timestamps are
anchored to the current hour so evidence freshness behaves realistically on the day of the demo.
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so backend/.env is picked up


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-mfa-failure", action="store_true", help="Inject Scenario 1 evidence and reassess")
    args = parser.parse_args()

    from app.core.database import SessionLocal
    from app.seed.seeder import seed_environment
    from app.services import demo_service

    with SessionLocal() as db:
        result = seed_environment(db)
        print(f"Seed complete (anchor {result['anchor']}, {result['runs']} historical assessment runs).")
        if args.with_mfa_failure:
            ev = demo_service.trigger_mfa_failure(db, user=None)
            run = demo_service.run_full_assessment(db, user=None)
            print(f"Scenario 1 injected via {ev.ref}; assessment {run.ref} created {run.summary['findings_created']}.")
        stats = demo_service.environment_stats(db)
        for key, value in stats.items():
            print(f"  {key:<28} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
