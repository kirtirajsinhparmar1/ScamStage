"""Run from the repository root: make contracts."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from app.schemas.contracts import HealthResponse, ParticipantTurn, TurnResult  # noqa: E402

MODELS = {"health": HealthResponse, "participant-turn": ParticipantTurn, "turn-result": TurnResult}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, model in MODELS.items():
        path = ROOT / "packages/contracts" / f"{name}.schema.json"
        content = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Contract drift: {path.name}; run make contracts")
        else:
            path.write_text(content)


if __name__ == "__main__":
    main()
