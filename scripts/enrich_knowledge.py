"""
知识库批量补全脚本：补全 source、新增 equipment/fault_symptom/safety_requirement/keywords/difficulty 字段。
用法: python scripts/enrich_knowledge.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "knowledge" / "knowledge_50.json"

# ── 完整标签映射（按 25 个实际 ability_node_id 定义）────────────────

TAG_MAP = {
    "role_task_understanding": {
        "source_primary": "教育部《机电一体化技术专业教学标准（高等职业教育专科）》；榆林职业技术学院 2024 人才培养方案",
        "equipment": [],
        "fault_symptom": "不清楚岗位工作边界和排故职责范围",
        "safety_requirement": "任何岗位操作都必须在教师确认安全后进行",
        "keywords": ["岗位", "能力图谱", "工作任务", "排故", "运维"],
        "difficulty": "basic",
    },
    "electrical_safety_check": {
        "source_primary": "GB/T 5226.1-2019 机械电气安全通用技术条件；PLC 实训指导书（安全操作规范）",
        "equipment": ["PLC控制柜", "急停按钮", "电源开关", "气源阀门"],
        "fault_symptom": "设备带电操作风险；急停未复位或误启动",
        "safety_requirement": "接线拆线前必须切断控制电源；急停复位后需确认输出状态和气缸位置才能启动；通电前由教师检查现场安全",
        "keywords": ["安全", "断电", "急停", "电源", "气源", "确认", "安全操作"],
        "difficulty": "basic",
    },
    "power_isolation_confirmation": {
        "source_primary": "GB/T 5226.1-2019 机械电气安全通用技术条件；PLC 实训指导书（安全操作规范）",
        "equipment": ["电源开关", "万用表", "验电器"],
        "fault_symptom": "误以为设备已断电；带电操作导致触电风险",
        "safety_requirement": "切断电源后需用万用表确认端子确实无电；多路供电的设备需逐一确认所有电源已断开",
        "keywords": ["断电", "隔离", "验电", "电源确认", "安全"],
        "difficulty": "basic",
    },
    "dc24v_power_check": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第3章 传感器与PLC接线",
        "equipment": ["24V开关电源", "万用表", "PLC电源模块"],
        "fault_symptom": "传感器不工作；输出不稳定；PLC输入模块无供电",
        "safety_requirement": "万用表选择直流电压档；表笔不能跨接相邻端子；确认端子后再测量",
        "keywords": ["DC24V", "0V", "供电", "电源", "正负极", "万用表"],
        "difficulty": "basic",
    },
    "multimeter_voltage_measurement": {
        "source_primary": "PLC 实训指导书（万用表操作规范）；GB/T 5226.1-2019 电气安全要求",
        "equipment": ["数字万用表", "PLC端子排", "DC24V电源"],
        "fault_symptom": "测量结果异常；表笔误触导致短路或读数错误",
        "safety_requirement": "选择直流电压档（DCV）；红表笔接正、黑表笔接负；不能电流档测电压；表笔不能跨接相邻端子",
        "keywords": ["万用表", "电压", "直流", "测量", "档位", "表笔"],
        "difficulty": "basic",
    },
    "sensor_type_identification": {
        "source_primary": "西门子工业支持中心技术论坛「西门子PLC与NPN（源型）和PNP（漏型）传感器的接线说明」(2015)；PLC 实训指导书",
        "equipment": ["NPN传感器", "PNP传感器", "传感器型号标签"],
        "fault_symptom": "NPN/PNP混淆导致输入信号逻辑相反；PLC无法正确读取传感器状态",
        "safety_requirement": "识别传感器类型后确认与PLC输入模式匹配；更换传感器时必须先断电",
        "keywords": ["NPN", "PNP", "类型识别", "源型", "漏型", "传感器型号"],
        "difficulty": "basic",
    },
    "sensor_nameplate_reading": {
        "source_primary": "PLC 实训指导书；传感器产品手册（电感式/光电式传感器说明书）",
        "equipment": ["传感器铭牌", "传感器说明书", "型号查询工具"],
        "fault_symptom": "无法从铭牌确认传感器类型、供电电压和输出方式",
        "safety_requirement": "读取铭牌时注意不要触碰带电端子；不确定时查说明书或问教师",
        "keywords": ["铭牌", "型号", "规格", "传感器参数", "说明书"],
        "difficulty": "basic",
    },
    "sensor_output_logic": {
        "source_primary": "西门子工业支持中心技术论坛「西门子PLC与NPN（源型）和PNP（漏型）传感器的接线说明」(2015)；AutomationDirect Sinking and Sourcing Sensor Wiring Basics",
        "equipment": ["NPN传感器", "PNP传感器", "万用表", "PLC输入模块"],
        "fault_symptom": "NPN导通输出低电平(0V)，PNP导通输出高电平(24V)；逻辑判断错误导致排故方向错误",
        "safety_requirement": "用万用表验证输出电平前先确认供电正常；表笔不要短路",
        "keywords": ["NPN", "PNP", "输出逻辑", "高电平", "低电平", "导通", "截止"],
        "difficulty": "medium",
    },
    "sensor_led_observation": {
        "source_primary": "PLC 实训指导书；传感器产品手册",
        "equipment": ["传感器(电感式/光电式/磁性)", "PLC输入模块"],
        "fault_symptom": "传感器LED指示灯不亮或异常闪烁；有遮挡但灯不亮",
        "safety_requirement": "观察指示灯时注意手部不要触及运动部件；传感器安装位置需保证安全距离",
        "keywords": ["动作灯", "指示灯", "传感器", "LED", "检测状态"],
        "difficulty": "basic",
    },
    "sensor_wiring_color_code": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第3章 传感器选型与接线",
        "equipment": ["三线制传感器", "万用表", "剥线钳", "端子起"],
        "fault_symptom": "棕蓝黑三线接错导致传感器不工作或输出异常",
        "safety_requirement": "接线前断电；棕线=DC24V、蓝线=0V、黑线=信号输出；以端子图和传感器说明为准",
        "keywords": ["棕线", "蓝线", "黑线", "三线制", "接线", "颜色"],
        "difficulty": "basic",
    },
    "sensor_wiring_judgement": {
        "source_primary": "PLC 实训指导书；AutomationDirect Sinking and Sourcing Sensor Wiring Basics",
        "equipment": ["传感器", "PLC输入模块", "万用表", "端子起"],
        "fault_symptom": "传感器动作灯亮但PLC输入灯不亮；输入信号异常",
        "safety_requirement": "先断电检查接线和端子压接；通电测量时注意表笔不要短接",
        "keywords": ["输入灯", "动作灯", "接线判断", "信号链路", "排查"],
        "difficulty": "medium",
    },
    "plc_input_common_terminal": {
        "source_primary": "西门子工业支持中心技术论坛「PLC输入类型源型/漏型与传感器选型匹配」(2010)；PLC 实训指导书",
        "equipment": ["PLC(S7-200 SMART/S7-1200)", "传感器", "端子排"],
        "fault_symptom": "传感器有动作但PLC输入点无信号；COM接错导致输入回路不完整",
        "safety_requirement": "接线前断电；确认公共端组划分和接线方式（源型/漏型）",
        "keywords": ["公共端", "COM", "输入回路", "源型", "漏型", "接线"],
        "difficulty": "medium",
    },
    "plc_input_grouping": {
        "source_primary": "PLC 实训指导书；西门子 S7-200 SMART 系统手册",
        "equipment": ["PLC(S7-200 SMART/S7-1200)", "传感器组", "端子排"],
        "fault_symptom": "不同公共端组混接导致部分输入点异常；同一组内传感器互相影响",
        "safety_requirement": "接线前确认各组公共端的独立性和接线规范",
        "keywords": ["分组", "公共端组", "COM", "独立组", "混接"],
        "difficulty": "medium",
    },
    "plc_io_address_mapping": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第4章 PLC I/O 地址分配",
        "equipment": ["PLC(S7-200 SMART)", "传感器", "电气图纸"],
        "fault_symptom": "程序中的地址与实际硬件地址不一致；输入信号无法被程序读取",
        "safety_requirement": "核对地址时对照电气图纸和PLC系统块配置；改地址后重新下载程序需确认安全",
        "keywords": ["I/O地址", "映射", "通道", "地址对应", "系统块"],
        "difficulty": "medium",
    },
    "io_mapping_table_build": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第4章",
        "equipment": ["电气图纸", "PLC系统块配置", "I/O地址表"],
        "fault_symptom": "I/O映射表与实际接线不符；地址记录错误导致后续排查困难",
        "safety_requirement": "填写映射表时对照实物和图纸双重确认",
        "keywords": ["I/O表", "映射表", "地址记录", "图纸", "对照"],
        "difficulty": "basic",
    },
    "program_variable_lookup": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第5章 PLC程序调试与监控",
        "equipment": ["PLC", "编程电脑", "编程软件(TIA Portal/STEP 7)"],
        "fault_symptom": "输入灯亮但程序变量不变化；程序中找不到对应输入点",
        "safety_requirement": "查找变量时参考程序符号表和交叉引用；不要随意修改变量映射",
        "keywords": ["变量", "符号表", "交叉引用", "地址", "程序查找"],
        "difficulty": "medium",
    },
    "plc_input_monitoring": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第5章",
        "equipment": ["PLC(S7-200 SMART/S7-1200)", "编程电脑", "编程电缆"],
        "fault_symptom": "程序运行状态与预期不符；输入信号状态不确定",
        "safety_requirement": "在线监控不影响设备安全，但强制输出功能需确认设备安全状态后再操作",
        "keywords": ["在线监控", "状态表", "变量表", "输入点", "强制"],
        "difficulty": "medium",
    },
    "input_led_compare": {
        "source_primary": "《机电设备故障诊断与维修》李万军主编，高等教育出版社，2025，项目五 PLC故障诊断与维修",
        "equipment": ["传感器", "PLC输入模块"],
        "fault_symptom": "无法区分故障在传感器侧、接线侧还是PLC侧",
        "safety_requirement": "观察指示灯时保持安全距离；不要在设备运行时伸手探入运动区域",
        "keywords": ["三联状态", "传感器灯", "PLC灯", "交叉检查", "故障定位"],
        "difficulty": "medium",
    },
    "input_no_response_fault_scope": {
        "source_primary": "PLC 实训指导书；《机电设备故障诊断与维修》李万军主编，高等教育出版社，2025，项目五 PLC故障诊断",
        "equipment": ["传感器", "PLC", "万用表", "24V电源", "端子排"],
        "fault_symptom": "输入无响应；传感器动作但PLC不识别；多个输入同时失效",
        "safety_requirement": "先查供电和公共端；不要盲目更换传感器；从电气层→输入层→程序层逐层排查",
        "keywords": ["无响应", "输入失效", "故障范围", "分层排查", "故障定位"],
        "difficulty": "advanced",
    },
    "no_response_power_path_check": {
        "source_primary": "PLC 实训指导书；《机电设备故障诊断与维修》李万军主编，高等教育出版社，2025，项目五",
        "equipment": ["万用表", "24V电源", "PLC电源模块", "传感器供电端子"],
        "fault_symptom": "传感器供电异常导致无响应；电源链路中断",
        "safety_requirement": "逐级测量供电电压：电源输出→端子排→传感器端；断电后再接触端子",
        "keywords": ["电源链路", "供电检查", "逐级测量", "无响应", "电源"],
        "difficulty": "medium",
    },
    "no_response_sensor_side_check": {
        "source_primary": "PLC 实训指导书；传感器产品手册",
        "equipment": ["传感器", "万用表", "传感器接线端"],
        "fault_symptom": "传感器本身故障或接线问题导致PLC输入无响应",
        "safety_requirement": "先确认供电正常再查传感器；更换传感器前断电",
        "keywords": ["传感器侧", "传感器故障", "接线", "信号输出", "无响应"],
        "difficulty": "medium",
    },
    "no_response_common_terminal_check": {
        "source_primary": "西门子工业支持中心技术论坛；PLC 实训指导书",
        "equipment": ["PLC输入模块", "公共端端子", "万用表"],
        "fault_symptom": "公共端断开或接错导致整组输入无响应",
        "safety_requirement": "断电检查公共端接线；确认公共端组划分正确；不同组公共端不能混接",
        "keywords": ["公共端", "COM", "无响应", "整组失效", "接线检查"],
        "difficulty": "medium",
    },
    "no_response_address_mapping_check": {
        "source_primary": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第4-5章",
        "equipment": ["PLC", "编程电脑", "电气图纸", "I/O地址表"],
        "fault_symptom": "传感器和接线正常但程序不响应；地址映射错误",
        "safety_requirement": "对照图纸和系统块配置核对地址；修改地址后下载需教师确认",
        "keywords": ["地址映射", "无响应", "地址核对", "系统块", "I/O表"],
        "difficulty": "medium",
    },
    "diagnosis_record_feedback": {
        "source_primary": "教育部《机电一体化技术专业教学标准（高等职业教育专科）》；项目反馈闭环设计",
        "equipment": ["实训记录表", "排查工具"],
        "fault_symptom": "排故完成后无记录或记录不完整；后续无法复盘",
        "safety_requirement": "记录应包括未确认风险和下一步安全建议",
        "keywords": ["排故记录", "交付物", "反馈", "复盘", "证据"],
        "difficulty": "basic",
    },
    "personalized_training_task_recommendation": {
        "source_primary": "项目图谱更新机制；教育部专业教学标准",
        "equipment": [],
        "fault_symptom": "训练任务与学生薄弱点不匹配；培养方案不变",
        "safety_requirement": "推荐训练任务时应包含安全操作步骤说明",
        "keywords": ["训练推荐", "个性化", "薄弱点", "培养方案", "学习路径"],
        "difficulty": "basic",
    },
}

# ── 特定条目的个性化 source 覆盖（条目ID → 精确来源）────────────
ITEM_OVERRIDES = {
    "K059": {"source": "全国标准信息公共服务平台 GB/T 5226.1-2019 机械电气安全通用技术条件"},
    "K060": {"source": "项目安全规则；GB/T 5226.1-2019 机械电气安全通用技术条件"},
    "K061": {"source": "PLC 实训指导书；《自动化生产线安装与调试》吕景泉主编，中国铁道出版社，2017，第5章 PLC程序调试与监控"},
    "K062": {"source": "AutomationDirect Sinking and Sourcing Sensor Wiring Basics；PLC 实训指导书"},
    "K063": {"source": "教育部《机电一体化技术专业教学标准（高等职业教育专科）》；项目反馈闭环设计"},
    "K064": {"source": "项目图谱更新机制；教育部《机电一体化技术专业教学标准（高等职业教育专科）》"},
    "K065": {"source": "《自动化生产线的安装与调试》课程标准 晏华成，模块4「自动化生产线维护与故障排除」(8学时)；PLC 实训指导书"},
    "K066": {"source": "项目产品方案设计；Inno Agent learner context pack 设计思路"},
}


def main():
    with open(KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    skipped = 0

    for item in data["items"]:
        kid = item.get("id", "")
        aid = item.get("ability_node_id", "")

        tags = TAG_MAP.get(aid)
        if not tags:
            print(f"  ⚠ {kid}: ability_node_id={aid} 无标签映射，跳过")
            skipped += 1
            continue

        # ── 补全 source（条目级覆盖优先）──
        if kid in ITEM_OVERRIDES:
            item["source"] = ITEM_OVERRIDES[kid]["source"]
        elif "待补充" in item.get("source", "") or not item.get("source"):
            item["source"] = tags.get("source_primary", item.get("source", ""))

        # ── 补全标签 ──
        item["equipment"] = tags.get("equipment", [])
        item["fault_symptom"] = tags.get("fault_symptom", "")
        item["safety_requirement"] = tags.get("safety_requirement", "")
        item["keywords"] = tags.get("keywords", [])
        item["difficulty"] = tags.get("difficulty", "basic")
        updated += 1

    # 写回
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ 完成：更新 {updated} 条，跳过 {skipped} 条（共 {len(data['items'])} 条）")


if __name__ == "__main__":
    main()
