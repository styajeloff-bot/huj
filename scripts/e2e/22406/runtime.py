"""Isolated task 22406 runtime using the existing monetization fixture."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/e2e")
import runtime as fixture

fixture.HOST_ROOT = Path("/tmp/carcraft-22406-e2e")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["keys", "migrate", "check", "seed"])
    action = parser.parse_args().action
    if action == "keys":
        fixture.keys()
    elif action in {"migrate", "check"}:
        fixture.migrate(action == "check")
    else:
        from seed import seed
        asyncio.run(seed())
