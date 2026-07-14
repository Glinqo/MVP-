import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_updater(*args, env_overrides=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_overrides:
        env.update(env_overrides)
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


def write_sqlite_sources_config(tmp_dir):
    config = {
        "version": "0.1.0-test",
        "policy": {
            "enabled": True,
            "respect_robots_txt": True,
            "max_sources_per_run": 1,
            "request_interval_seconds": 0,
            "timeout_seconds": 5,
            "max_bytes_per_source": 200000,
            "user_agent": "mechatronics-agent-mvp-test",
        },
        "target_job_role": "自动化生产线装调与运维技术员",
        "global_keywords": ["PLC", "传感器", "NPN", "PNP", "公共端", "在线监控"],
        "sources": [
            {
                "id": "fixture_job_posting_sqlite",
                "enabled": True,
                "type": "local_file",
                "path": "tests/fixtures/job_postings_sample.html",
                "source_type": "teacher_material",
                "source": "tests/fixtures/job_postings_sample.html",
                "job_role": "自动化生产线装调与运维技术员",
                "keywords": ["PLC 输入", "公共端", "I/O 地址", "在线监控"],
            }
        ],
    }
    path = Path(tmp_dir) / "job_intelligence_sources.sqlite.test.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "evidence.db"
        run_log = Path(tmp) / "runs.json"
        sources = write_sqlite_sources_config(tmp)
        applied = run_updater(
            "--sources",
            str(sources),
            "--run-log",
            str(run_log),
            env_overrides={"MVP_EVIDENCE_DB_PATH": str(db_path)},
        )
        assert applied["ok"] is True
        assert applied["dry_run"] is False
        assert applied["collected_count"] == 1
        assert applied["sqlite_ingest"]["document_count"] >= 1
        assert applied["sqlite_ingest"]["event_count"] > 0
        assert applied["sqlite_ingest"]["proposal_count"] > 0
        assert run_log.exists()

    print("job_intelligence_update.test.py passed")


if __name__ == "__main__":
    main()
