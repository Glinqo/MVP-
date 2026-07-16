"""
合并导入的64条知识条目到主知识库。
用法: python scripts/merge_imports.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTS_PATH = ROOT / "knowledge" / "imports" / "机电一体化智能体_知识库导入版_V1.json"
KB_PATH = ROOT / "knowledge" / "knowledge_50.json"

# 能力模块名 → ability_node_id 映射（基于现有25个节点）
MODULE_TO_ABILITY = {
    "岗位基础与能力图谱": "role_task_understanding",
    "电气安全与操作规范": "electrical_safety_check",
    "电气安全": "electrical_safety_check",
    "电气元件与安全": "electrical_safety_check",
    "传感器类型与原理": "sensor_type_identification",
    "传感器接线": "sensor_wiring_color_code",
    "传感器接线与信号判断": "sensor_wiring_judgement",
    "PLC 输入信号接线": "plc_input_common_terminal",
    "PLC 输入信号排查": "input_no_response_fault_scope",
    "PLC 程序与诊断": "plc_input_monitoring",
    "I/O 地址对应": "plc_io_address_mapping",
    "传感器与 I/O 地址排查": "plc_io_address_mapping",
    "气动执行机构": "pneumatic_valve_basic",  # 扩展内容，挂到输入无响应
    "气动执行及气缸排查": "input_no_response_fault_scope",
    "电机驱动与运动控制": "input_no_response_fault_scope",  # 扩展，挂到排故范围
    "设备点检与综合故障排查": "input_no_response_fault_scope",
    "知识库与智能体规则": "role_task_understanding",
}


def main():
    # 读取导入条目
    with open(IMPORTS_PATH, "r", encoding="utf-8") as f:
        imports = json.load(f)

    # 读取主知识库
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    existing_topics = {item["topic"] for item in kb["items"]}
    new_items = []
    skipped = 0
    merged = 0

    for i, entry in enumerate(imports):
        old_id = entry.get("编号", f"IMPORT-{i}")
        topic = entry.get("知识点", entry.get("技能点", ""))

        # 去重：检查 topic 是否已存在
        if topic in existing_topics:
            skipped += 1
            continue

        # 映射 ability_node_id
        module = entry.get("能力模块", "")
        ability_id = MODULE_TO_ABILITY.get(module, "role_task_understanding")

        # 提取 common_errors
        error_str = entry.get("常见错误/问题", "")
        common_errors = [e.strip() for e in error_str.replace("；", ";").split(";") if e.strip()]

        # 安全要求
        safety = entry.get("安全提示", "")

        # 关键字
        keyword_str = entry.get("检索关键词", "")
        keywords = [k.strip() for k in keyword_str.replace("，", ",").split(",") if k.strip()]
        if not keywords:
            keywords = []

        # 提取设备（从知识点和安全提示中）
        equipment = _extract_equipment(entry)

        new_id = f"K{len(kb['items']) + len(new_items) + 1:03d}"

        new_item = {
            "id": new_id,
            "topic": topic[:80],
            "ability_node_id": ability_id,
            "job_task": entry.get("典型实训任务", ""),
            "content": entry.get("知识点", ""),
            "common_errors": common_errors[:3],
            "related_questions": [],
            "related_tasks": [],
            "source": entry.get("来源依据", ""),
            "equipment": equipment,
            "fault_symptom": entry.get("诊断题", ""),
            "safety_requirement": safety,
            "keywords": keywords[:8],
            "difficulty": _map_difficulty(entry.get("适用阶段", "")),
            "_imported_from": old_id,
        }
        new_items.append(new_item)
        existing_topics.add(topic)
        merged += 1

    kb["items"].extend(new_items)

    # 更新元信息
    kb["version"] = "0.3.0"
    kb["source"] = "主知识库(66条) + 导入条目合并"

    # 写回
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

    print(f"✅ 合并完成：新增 {merged} 条，去重跳过 {skipped} 条（原 {len(imports)} 条导入）")
    print(f"   主知识库总条目: {len(kb['items'])} 条 (K001-K{len(kb['items']):03d})")


def _extract_equipment(entry):
    """从知识条目中提取涉及设备。"""
    text = entry.get("知识点", "") + " " + entry.get("典型实训任务", "")
    equipment = set()
    eq_map = {
        "PLC": "PLC(S7-200 SMART)",
        "plc": "PLC(S7-200 SMART)",
        "传感器": "传感器",
        "万用表": "万用表",
        "气缸": "气缸",
        "电磁阀": "电磁阀",
        "电机": "电机",
        "气源": "气源",
        "电源": "开关电源",
        "端子": "端子排",
        "限位": "限位开关",
        "断路器": "断路器",
        "熔断器": "熔断器",
        "接触器": "接触器",
        "继电器": "继电器",
        "变频器": "变频器",
        "伺服": "伺服驱动器",
        "驱动器": "驱动器",
        "接线图": "电气图纸",
        "监控": "编程电脑",
        "在线监控": "编程电脑",
    }
    for keyword, eq_name in eq_map.items():
        if keyword in text:
            equipment.add(eq_name)
    return sorted(equipment)[:6]


def _map_difficulty(stage):
    """适用阶段 → 难度映射。"""
    stage_lower = stage.lower()
    if "入门" in stage_lower or "基础" in stage_lower:
        return "basic"
    if "扩展" in stage_lower or "后续" in stage_lower:
        return "advanced"
    return "medium"


if __name__ == "__main__":
    main()
