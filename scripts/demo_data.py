# -*- coding: utf-8 -*-
"""演示数据生成器 - 阶段八"""

import json, sqlite3, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ASSESS_DB = ROOT / "data" / "assessments.db"
JOB = "automation_line_commissioning_maintenance_newcomer"

STUDENTS = [
    {"u":"001","n":"张三","s":63,"w":[("PLC\u8f93\u5165\u4fe1\u53f7\u8bca\u65ad","plc_control_input_diag",42),("NPN/PNP\u63a5\u7ebf\u5224\u65ad","sensor_signal_npn_pnp",51)],"t":[("PLC\u8f93\u5165\u68c0\u6d4b","plc_control_input_diag",78)]},
    {"u":"002","n":"\u674e\u56db","s":81,"w":[("\u4f3a\u670d\u53c2\u6570\u8bbe\u7f6e","plc_control_servo_param",65)],"t":[("\u7535\u6c14\u5b89\u5168\u7a0b\u5e8f\u9a8c\u8bc1","electrical_safety_verify",92)]},
    {"u":"003","n":"\u738b\u4e94","s":45,"w":[("PLC\u8f93\u5165\u4fe1\u53f7\u8bca\u65ad","plc_control_input_diag",30),("NPN/PNP\u63a5\u7ebf\u5224\u65ad","sensor_signal_npn_pnp",35),("\u7535\u6c14\u5b89\u5168\u53cc\u4eba\u786e\u8ba4","electrical_safety_doublecheck",40)],"t":[],"sg":["\u7535\u6c14\u5b89\u5168\u53cc\u4eba\u786e\u8ba4"]},
    {"u":"004","n":"\u8d75\u516d","s":72,"w":[("PLC\u8f93\u5165\u4fe1\u53f7\u8bca\u65ad","plc_control_input_diag",55)],"t":[("\u4f20\u611f\u5668\u8f93\u51fa\u68c0\u6d4b","sensor_signal_output",82)]},
    {"u":"005","n":"\u94b1\u4e03","s":58,"w":[("NPN/PNP\u63a5\u7ebf\u5224\u65ad","sensor_signal_npn_pnp",48),("PLC\u8f93\u5165\u4fe1\u53f7\u8bca\u65ad","plc_control_input_diag",52)],"t":[("\u7535\u6c14\u5b89\u5168\u65ad\u7535\u786e\u8ba4","electrical_safety_poweroff",78)]},
]

EVENTS = {
    "001": [
        ("self_test","quiz","plc_control_input_diag","wrong","\u81ea\u6d4b: PLC\u8f93\u5165\u68c0\u6d4b\u6b65\u9aa4\u9519\u8bef"),
        ("scenario_training","training","plc_control_input_diag","error","\u6392\u6545\u8bad\u7ec3: \u7701\u7565\u516c\u5171\u7aef\u68c0\u67e5"),
        ("ai_question","chat","sensor_signal_npn_pnp","asked","AI\u95ee\u7b54: \u8be2\u95eePNP\u516c\u5171\u7aef\u8fde\u63a5\u65b9\u5f0f"),
        ("self_test","quiz","electrical_safety_poweroff","correct","\u81ea\u6d4b: \u5b89\u5168\u65ad\u7535\u6b65\u9aa4\u6b63\u786e"),
        ("scenario_training","training","plc_control_input_diag","error","\u6392\u6545\u8bad\u7ec3: \u518d\u6b21\u9057\u6f0f\u516c\u5171\u7aef\u68c0\u67e5"),
        ("feedback","feedback","plc_control_input_diag","still_weak","\u53cd\u9988: \u4ecd\u4e0d\u4f1a PLC\u8f93\u5165\u8bca\u65ad"),
    ],
    "002": [
        ("self_test","quiz","electrical_safety_verify","correct","\u81ea\u6d4b: \u5b89\u5168\u7a0b\u5e8f\u9a8c\u8bc1\u901a\u8fc7"),
        ("scenario_training","training","plc_control_servo_param","warning","\u6392\u6545\u8bad\u7ec3: \u4f3a\u670d\u53c2\u6570\u8bbe\u7f6e\u504f\u6162"),
        ("scenario_training","training","plc_control_servo_param","pass","\u6392\u6545\u8bad\u7ec3: \u4f3a\u670d\u53c2\u6570\u8c03\u6574\u540e\u901a\u8fc7"),
    ],
    "003": [
        ("self_test","quiz","plc_control_input_diag","wrong","\u81ea\u6d4b: PLC\u8f93\u5165\u4fe1\u53f7\u5224\u65ad\u5b8c\u5168\u9519\u8bef"),
        ("scenario_training","training","plc_control_input_diag","error","\u6392\u6545\u8bad\u7ec3: \u65e0\u6cd5\u5b9a\u4f4d\u8f93\u5165\u6545\u969c\u70b9"),
        ("self_test","quiz","sensor_signal_npn_pnp","wrong","\u81ea\u6d4b: NPN/PNP\u63a5\u7ebf\u6df7\u6dc6"),
        ("scenario_training","training","electrical_safety_doublecheck","error","\u6392\u6545\u8bad\u7ec3: \u6f0f\u4e86\u53cc\u4eba\u786e\u8ba4\u6b65\u9aa4"),
        ("feedback","feedback","plc_control_input_diag","still_weak","\u53cd\u9988: \u4ecd\u4e0d\u4f1a PLC\u8f93\u5165\u8bca\u65ad"),
        ("self_test","quiz","electrical_safety_doublecheck","wrong","\u81ea\u6d4b: \u5b89\u5168\u786e\u8ba4\u6d41\u7a0b\u9519\u8bef"),
    ],
    "004": [
        ("self_test","quiz","plc_control_input_diag","wrong","\u81ea\u6d4b: PLC\u8f93\u5165\u68c0\u6d4b\u5224\u65ad\u504f\u5dee"),
        ("scenario_training","training","plc_control_input_diag","pass","\u6392\u6545\u8bad\u7ec3: \u8f93\u5165\u68c0\u6d4b\u6b65\u9aa4\u6539\u5584"),
        ("scenario_training","training","plc_control_input_diag","error","\u6392\u6545\u8bad\u7ec3: \u590d\u6742\u573a\u666f\u4ecd\u9057\u6f0f\u68c0\u67e5"),
    ],
    "005": [
        ("self_test","quiz","sensor_signal_npn_pnp","wrong","\u81ea\u6d4b: NPN/PNP\u516c\u5171\u7aef\u5173\u7cfb\u5224\u65ad\u9519\u8bef"),
        ("scenario_training","training","plc_control_input_diag","error","\u6392\u6545\u8bad\u7ec3: \u7aef\u5b50\u7535\u538b\u68c0\u67e5\u9057\u6f0f"),
        ("feedback","feedback","sensor_signal_npn_pnp","still_weak","\u53cd\u9988: \u4ecd\u4e0d\u4f1a NPN/PNP\u63a5\u7ebf"),
    ],
}

def ensure_tables():
    conn = sqlite3.connect(str(ASSESS_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, job_role TEXT NOT NULL DEFAULT 'default',
        assessment_id TEXT NOT NULL DEFAULT '', assessment_version TEXT NOT NULL DEFAULT '1.0.0',
        state TEXT NOT NULL DEFAULT 'not_started', answers_json TEXT NOT NULL DEFAULT '[]',
        result_json TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, completed_at REAL,
        UNIQUE(session_id, job_role, assessment_version))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS assessment_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        event_type TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
        ability_id TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '', timestamp REAL, created_at REAL NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assess_session ON assessments(session_id, job_role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aevent_session ON assessment_events(session_id)")
    conn.commit()
    conn.close()

def insert_demo_data():
    ensure_tables()
    now = time.time()
    conn = sqlite3.connect(str(ASSESS_DB))
    conn.execute("PRAGMA journal_mode=WAL")

    for i, s in enumerate(STUDENTS):
        sid = f"{JOB}-{s['u']}"
        created_at = now - (5-i)*86400
        dims = {"electrical_safety": s["s"] + (i%3)*5, "sensor_signal": s["s"] - (i%4)*3, "plc_control": s["s"] - 10 - i*3, "troubleshooting": s["s"] + (i%2)*8}
        weak = [{"name": w[0], "id": w[1], "score": w[2]} for w in s["w"]]
        strong = [{"name": t[0], "id": t[1], "score": t[2]} for t in s.get("t",[])]
        result = {"total_score": s["s"], "dimension_scores": dims, "weak_abilities": weak, "strong_abilities": strong, "safety_critical_gaps": s.get("sg",[])}
        conn.execute("""INSERT OR REPLACE INTO assessments
            (id,session_id,job_role,assessment_id,assessment_version,state,answers_json,result_json,created_at,updated_at,completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (f"demo-{sid}",sid,JOB,"demo","1.0.0","completed","[]",
             json.dumps(result,ensure_ascii=False),created_at,now,created_at+300))
        print(f"  [{s['u']}] {s['n']} score={s['s']} weak={len(weak)}")

        evs = EVENTS.get(s["u"], [])
        for j, ev in enumerate(evs):
            ts = created_at + j*3600 - 86400 + j*600
            conn.execute("""INSERT OR IGNORE INTO assessment_events
                (session_id,event_type,category,ability_id,result,description,timestamp,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (sid, ev[0], ev[1], ev[2], ev[3], ev[4], ts, ts))
        print(f"         {len(evs)} events")

    conn.commit()
    conn.close()
    print(f"\nDone: {len(STUDENTS)} students with assessments + events")

if __name__ == "__main__":
    insert_demo_data()
