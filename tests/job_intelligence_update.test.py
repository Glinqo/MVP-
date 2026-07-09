import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_updater(*args):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "job_intelligence_update.py"), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main():
    summary = run_updater(
        "--sources",
        "tests/fixtures/job_intelligence_sources.test.json",
        "--dry-run",
    )
    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["collected_count"] == 1
    assert summary["proposal_count"] == 0

    ability_ids = {item["ability_id"] for item in summary["matched_abilities"]}
    assert "sensor_type_identification" in ability_ids
    assert "sensor_wiring_judgement" in ability_ids
    assert "plc_input_common_terminal" in ability_ids
    assert "plc_io_address_mapping" in ability_ids
    assert "plc_input_monitoring" in ability_ids
    assert "electrical_safety_check" in ability_ids

    print("job_intelligence_update.test.py passed")


if __name__ == "__main__":
    main()
