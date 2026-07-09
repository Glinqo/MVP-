SAFETY_NOTICE = (
    "安全提醒：接线和拆线前先断电；调试前确认急停、气源、电源和设备状态；"
    "不确定设备状态时请教师或实训指导人员确认；禁止绕过安全回路、短接保护或带电冒险操作。"
)

SAFETY_KEYWORDS = [
    "接线",
    "拆线",
    "通电",
    "测量",
    "电源",
    "端子",
    "公共端",
    "传感器",
    "plc",
    "PLC",
    "输入",
    "监控",
    "气缸",
    "气源",
    "电磁阀",
    "动作",
    "设备",
    "调试",
    "故障",
]


def requires_safety_notice(text="", weak_abilities=None, recommended_path=None):
    weak_abilities = weak_abilities or []
    recommended_path = recommended_path or []

    if any(keyword in str(text or "") for keyword in SAFETY_KEYWORDS):
        return True

    if any(item.get("ability_id") == "A01" for item in weak_abilities):
        return True

    return any("安全" in str(item) or "断电" in str(item) for item in recommended_path)


def safety_notice(text="", weak_abilities=None, recommended_path=None):
    return SAFETY_NOTICE if requires_safety_notice(text, weak_abilities, recommended_path) else ""
