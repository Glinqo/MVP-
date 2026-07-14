import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PYTHON = sys.executable
PORT = 8767
BASE_URL = f"http://127.0.0.1:{PORT}"


def request_json(path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(process):
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError("server exited early")
        try:
            if request_json("/api/health").get("status") == "ok":
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise TimeoutError("server did not become ready")


def test_sqlite_store(db_path):
    os.environ["MVP_EVIDENCE_DB_PATH"] = str(db_path)
    from scripts.pipeline.evidence_store import (
        add_proposal,
        add_job_post,
        add_raw_document,
        audit_log,
        confirm_proposal,
        create_event,
        create_snapshot,
        list_job_posts,
        list_raw_documents,
        get_pending_proposals,
        query_events,
        reject_proposal,
        version_diff,
    )
    from scripts.pipeline.sqlite_store import ability_evidence_summary, close

    raw_doc = add_raw_document(
        "自动化设备调试工程师\n职责：负责 PLC 调试。\n要求：熟悉传感器和电气安全。",
        source_type="teacher_material",
        source="unit_test",
        source_url="https://example.com/raw/1",
    )
    assert raw_doc["deduplicated"] is False
    same_doc = add_raw_document(
        "自动化设备调试工程师\n职责：负责 PLC 调试。\n要求：熟悉传感器和电气安全。",
        source_type="teacher_material",
        source="unit_test",
        source_url="https://example.com/raw/1",
    )
    assert same_doc["deduplicated"] is True
    job_post = add_job_post(
        raw_doc["document_id"],
        "测试岗位",
        {
            "title": "自动化设备调试工程师",
            "normalized_title": "自动化设备调试工程师",
            "company": "测试企业",
            "responsibilities": ["职责：负责 PLC 调试。"],
            "skills": ["熟悉传感器"],
            "requirements": ["要求：熟悉传感器和电气安全。"],
        },
        source_type="teacher_material",
        source_url="https://example.com/raw/1",
    )
    assert job_post["deduplicated"] is False
    assert list_raw_documents()[0]["document_id"] == raw_doc["document_id"]
    assert list_job_posts("测试岗位")[0]["job_post_id"] == job_post["job_post_id"]

    ev1 = create_event(
        "测试岗位",
        "plc_input_common_terminal",
        "负责 PLC 输入公共端接线与调试",
        source_url="https://example.com/job/1",
        source_type="enterprise_official",
        confidence=0.82,
    )
    ev2 = create_event(
        "测试岗位",
        "plc_input_common_terminal",
        "负责 PLC 输入公共端接线与调试",
        source_url="https://example.com/job/1",
        source_type="enterprise_official",
        confidence=0.82,
    )
    assert ev1["deduplicated"] is False
    assert ev2["deduplicated"] is True

    events = query_events(job_role="测试岗位", ability_id="plc_input_common_terminal")
    assert len(events) == 1
    summary = ability_evidence_summary("plc_input_common_terminal", "测试岗位")
    assert summary["evidence_count"] == 1
    assert summary["source_type_distribution"]["enterprise_official"] == 1

    proposal = add_proposal(
        "测试岗位",
        "plc_input_common_terminal",
        evidence="企业 JD 反复要求 PLC 公共端判断",
        source="unit_test",
        proposal_score=0.72,
    )
    pending = get_pending_proposals("测试岗位")
    assert pending and pending[0]["proposal_id"] == proposal["proposal_id"]
    confirmed = confirm_proposal(proposal["proposal_id"], "unit_teacher")
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_by"] == "unit_teacher"
    assert reject_proposal("missing-proposal")["error"] == "proposal not found"

    create_snapshot("测试岗位", [{"id": "a", "demand_weight": 1.0}], {"plc": 0.5}, "v-test-1")
    create_snapshot(
        "测试岗位",
        [{"id": "a", "demand_weight": 1.4}, {"id": "b", "demand_weight": 0.7}],
        {"plc": 0.7},
        "v-test-2",
    )
    diff = version_diff("v-test-1", "v-test-2")
    assert diff["has_changes"] is True
    assert diff["added"][0]["id"] == "b"
    assert diff["changed"][0]["changes"]["demand_weight"]["to"] == 1.4
    assert audit_log(limit=5)
    close()


def test_llm_extractor_fallback():
    import scripts.pipeline.llm_extractor as extractor

    parsed = extractor._parse_response(
        '```json\n[{"skill_name":"PLC 调试","matched_dimension_id":"plc_control_debug","confidence":0.9}]\n```'
    )
    assert parsed[0]["skill_name"] == "PLC 调试"

    nodes = [{
        "id": "plc_input_common_terminal",
        "name": "PLC 输入公共端判断",
        "radar_dimension_ids": ["plc_control_debug"],
    }]
    mapped = extractor._validate_and_map(parsed, nodes)
    assert mapped[0]["ability_id"] == "plc_input_common_terminal"

    semantic_nodes = [
        {
            "id": "plc_input_common_terminal",
            "name": "PLC 输入公共端判断",
            "level": "basic",
            "description": "识别 COM、S/S、源型输入、漏型输入和公共端接法。",
            "common_errors": ["公共端接错", "源型漏型混淆"],
            "radar_dimension_ids": ["plc_control_debug"],
        },
        {
            "id": "electrical_safety_check",
            "name": "电气安全检查",
            "level": "basic",
            "description": "断电、急停和 DC24V 安全确认。",
            "radar_dimension_ids": ["electrical_safety_diagram"],
        },
    ]
    semantic_mapped = extractor._validate_and_map(
        [{"skill_name": "源型漏型输入接法", "matched_dimension_id": "plc_control_debug", "confidence": 0.8}],
        semantic_nodes,
    )
    assert semantic_mapped[0]["ability_id"] == "plc_input_common_terminal"
    assert semantic_mapped[0]["match_method"] == "semantic_similarity"
    assert semantic_mapped[0]["similarity_score"] > 0.18

    original = extractor.is_configured
    extractor.is_configured = lambda: False
    try:
        assert extractor.llm_extract_skills("负责 PLC 调试和传感器故障处理", nodes) == []
    finally:
        extractor.is_configured = original

    with tempfile.TemporaryDirectory() as tmp:
        calls = {"count": 0}
        original_config = extractor.config
        original_is_configured = extractor.is_configured
        original_chat_completion = extractor.chat_completion
        original_cache_dir = os.environ.get("LLM_EXTRACT_CACHE_DIR")
        original_max_calls = os.environ.get("LLM_EXTRACT_MAX_CALLS")
        try:
            os.environ["LLM_EXTRACT_CACHE_DIR"] = tmp
            os.environ["LLM_EXTRACT_MAX_CALLS"] = "1"
            extractor._LLM_CALL_COUNT = 0
            extractor.config = lambda: {"api_key": "unit", "base_url": "https://example.com", "model": "unit-model"}
            extractor.is_configured = lambda: True

            def fake_chat_completion(*args, **kwargs):
                calls["count"] += 1
                return '[{"skill_name":"PLC 输入公共端判断","matched_dimension_id":"plc_control_debug","confidence":0.9}]'

            extractor.chat_completion = fake_chat_completion
            first = extractor.llm_extract_skills("负责 PLC 输入公共端判断和接线调试", nodes)
            second = extractor.llm_extract_skills("负责 PLC 输入公共端判断和接线调试", nodes)
            assert calls["count"] == 1
            assert first[0]["ability_id"] == "plc_input_common_terminal"
            assert second[0]["prompt_version"] == extractor.PROMPT_VERSION
        finally:
            extractor.config = original_config
            extractor.is_configured = original_is_configured
            extractor.chat_completion = original_chat_completion
            if original_cache_dir is None:
                os.environ.pop("LLM_EXTRACT_CACHE_DIR", None)
            else:
                os.environ["LLM_EXTRACT_CACHE_DIR"] = original_cache_dir
            if original_max_calls is None:
                os.environ.pop("LLM_EXTRACT_MAX_CALLS", None)
            else:
                os.environ["LLM_EXTRACT_MAX_CALLS"] = original_max_calls
            extractor._LLM_CALL_COUNT = 0


def test_batch_importer(db_path, tmp_dir):
    os.environ["MVP_EVIDENCE_DB_PATH"] = str(db_path)
    csv_path = Path(tmp_dir) / "job_posts.csv"
    csv_path.write_text(
        "\n".join([
            "title,company,responsibilities,requirements,skills",
            "自动化调试工程师,测试企业,负责 PLC 输入公共端接线和传感器故障排查,熟悉电气安全和在线监控,PLC;传感器;公共端",
        ]),
        encoding="utf-8",
    )

    from scripts.pipeline.evidence_store import list_job_posts, list_raw_documents
    from scripts.pipeline.job_data_importer import import_path

    try:
        result = import_path(
            csv_path,
            job_role="批量导入测试岗位",
            source_type="teacher_material",
            source="unit_csv",
            use_llm=False,
        )

        assert result["document_count"] == 1
        assert result["event_count"] > 0
        assert result["proposal_count"] > 0
        assert list_raw_documents("teacher_material")
        posts = list_job_posts("批量导入测试岗位")
        assert posts
        assert posts[0]["company"] == "测试企业"
    finally:
        from scripts.pipeline.sqlite_store import close
        close()


def test_ingest_api(db_path):
    env = os.environ.copy()
    env["MVP_EVIDENCE_DB_PATH"] = str(db_path)
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    env.pop("LLM_MODEL", None)

    collect_sources = db_path.parent / "job_collect_sources.json"
    collect_sources.write_text(
        json.dumps(
            {
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
                "target_job_role": "测试岗位",
                "global_keywords": ["PLC", "传感器", "公共端", "在线监控"],
                "sources": [
                    {
                        "id": "api_collect_fixture",
                        "enabled": True,
                        "type": "local_file",
                        "path": "tests/fixtures/job_postings_sample.html",
                        "source_type": "teacher_material",
                        "source": "tests/fixtures/job_postings_sample.html",
                        "job_role": "测试岗位",
                        "keywords": ["PLC 输入", "公共端", "I/O 地址", "在线监控"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    collect_run_log = db_path.parent / "job_collect_runs.json"

    process = subprocess.Popen(
        [PYTHON, str(ROOT / "app" / "server.py"), "--port", str(PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_server(process)
        result = request_json(
            "/api/graph/job/ingest",
            {
                "job_role": "测试岗位",
                "text": "负责 PLC 输入公共端接线、传感器故障排查、电气安全检查。",
                "source_type": "teacher_material",
                "source": "unit_test_material",
                "use_llm": False,
            },
        )
        assert result["method"] == "rule_lexicon"
        assert result["raw_document"]["document_id"].startswith("DOC-")
        assert result["job_post"]["job_post_id"].startswith("JOB-")
        assert result["normalized_fields"]["responsibilities"]
        assert result["events_created"]
        assert result["proposals_generated"]

        docs = request_json("/api/job-data/documents")
        assert docs["documents"]
        role_query = urllib.parse.urlencode({"job_role": "测试岗位"})
        posts = request_json("/api/job-data/posts?" + role_query)
        assert posts["posts"]

        pending = request_json("/api/graph/job/proposals/pending?" + role_query)
        assert pending["proposals"]

        first = pending["proposals"][0]["proposal_id"]
        confirmed = request_json(
            "/api/graph/job/proposals/confirm-sqlite",
            {"proposal_id": first, "action": "confirm", "confirmed_by": "unit_teacher"},
        )
        assert confirmed["proposal"]["status"] == "confirmed"
        assert confirmed["proposal"]["confirmed_by"] == "unit_teacher"
        assert confirmed["snapshot"]["version"].startswith("v")
        assert confirmed["snapshot_graph"]["created_from"] == "confirmed_sqlite_proposals"
        assert first in confirmed["snapshot_graph"]["confirmed_proposal_ids"]
        versions = request_json("/api/graph/job/versions?" + role_query)
        assert any(item["version"] == confirmed["snapshot"]["version"] for item in versions["versions"])
        active_graph = request_json("/api/graph/job?" + role_query)
        assert active_graph["job_role"] == "测试岗位"
        assert active_graph["active_snapshot"]["version"] == confirmed["snapshot"]["version"]
        assert active_graph["summary"]["active_snapshot_version"] == confirmed["snapshot"]["version"]
        assert any(node.get("confirmed_proposal_id") == first for node in active_graph["nodes"])

        collected = request_json(
            "/api/job-data/collect",
            {
                "sources": str(collect_sources),
                "run_log": str(collect_run_log),
                "max_sources": 1,
                "store": "sqlite",
                "use_llm": False,
            },
        )
        assert collected["ok"] is True
        assert collected["collected_count"] == 1
        assert collected["sqlite_ingest"]["document_count"] >= 1
        assert collected["sqlite_ingest"]["event_count"] > 0
        assert collected["sqlite_ingest"]["proposal_count"] > 0

        request_json(
            "/api/graph/job/ingest",
            {
                "job_role": "测试岗位",
                "text": "岗位要求掌握 NPN/PNP 传感器接线、PLC 输入公共端判断、在线监控和电气安全检查。",
                "source_type": "teacher_material",
                "source": "unit_test_material_batch",
                "source_url": "https://example.com/batch-job/1",
                "use_llm": False,
            },
        )
        pending_after = request_json("/api/graph/job/proposals/pending?" + role_query)
        batch = request_json(
            "/api/graph/job/proposals/confirm-sqlite-batch",
            {"confirm_all": True, "job_role": "测试岗位", "confirmed_by": "unit_teacher_batch"},
        )
        assert batch["confirmed_count"] >= len(pending_after["proposals"])
        assert batch["snapshots"]
        assert batch["snapshots"][0]["snapshot_graph"]["created_from"] == "confirmed_sqlite_proposals"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "evidence.db"
        test_sqlite_store(db_path)
        test_llm_extractor_fallback()
        test_batch_importer(db_path, tmp)
        test_ingest_api(db_path)
    print("job_graph_backend_upgrade.test.py passed")


if __name__ == "__main__":
    main()
