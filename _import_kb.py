import json, re

md_path = r'C:\Users\17578\Desktop\各相关专业知识库.md'
js_path = r'C:\Users\17578\Desktop\MVP-\knowledge\knowledge_50.json'
res_path = r'C:\Users\17578\Desktop\MVP-\knowledge\resources.json'

with open(md_path, 'r', encoding='utf-8') as f:
    md = f.read()

job_map = {
    '一': 'automation_line_commissioning_maintenance_newcomer',
    '二': 'mechanical_electrical_maintenance_worker',
    '三': 'automation_equipment_debugger',
    '四': 'industrial_robot_maintenance',
    '五': 'plc_electrical_control_technician',
    '六': 'sensor_industrial_network_debugger',
    '七': 'servo_step_drive_debugger',
    '八': 'cnc_maintenance_worker',
}
job_names = {
    '一': '自动化生产线装调与运维技术员',
    '二': '机电设备维修工',
    '三': '自动化设备调试员',
    '四': '工业机器人系统运维员',
    '五': 'PLC电气控制技术员',
    '六': '传感器与工业网络调试员',
    '七': '伺服/步进驱动调试员',
    '八': '数控设备维护员',
}

sections = re.split(r'\n### (?=[一二三四五六七八])', md)
sections = [s for s in sections if re.match(r'[一二三四五六七八]', s.strip()[:1])]

new_entries = []
counter = {}
for sec in sections:
    m = re.match(r'([一二三四五六七八])、(.+)', sec.strip().split('\n')[0])
    if not m: continue
    num, name_part = m.group(1), m.group(2)
    job_id = job_map[num]
    job_name = job_names[num]
    if job_id not in counter: counter[job_id] = 0

    subs = re.split(r'\n#### ', sec)
    for sub in subs[1:]:
        lines = sub.strip().split('\n')
        if not lines: continue
        heading = lines[0].strip()
        content = '\n'.join(lines[1:]).strip()
        if len(content) < 20: continue
        counter[job_id] += 1
        kid = f'{job_id[:8].upper()}{counter[job_id]:03d}'
        new_entries.append({
            'id': kid,
            'topic': heading,
            'ability_node_id': '',
            'job_task': '',
            'content': content,
            'common_errors': [],
            'related_questions': [],
            'related_tasks': [],
            'source': '各相关专业知识库',
            'job_role': job_id,
            'job_name': job_name,
        })

with open(js_path, 'r', encoding='utf-8') as f:
    old_data = json.load(f)
old_items = old_data.get('items', [])

for item in old_items:
    if not item.get('job_role'):
        item['job_role'] = 'automation_line_commissioning_maintenance_newcomer'
        item['job_name'] = '自动化生产线装调与运维技术员'

existing_ids = {item['id'] for item in old_items}
for entry in new_entries:
    if entry['id'] not in existing_ids:
        old_items.append(entry)

old_data['items'] = old_items
old_data['total'] = len(old_items)

with open(js_path, 'w', encoding='utf-8') as f:
    json.dump(old_data, f, ensure_ascii=False, indent=2)
print(f'Knowledge entries: {len(old_items)} total')

try:
    with open(res_path, 'r', encoding='utf-8') as f:
        resources = json.load(f)
except:
    resources = []

for job_id_str, jid in job_map.items():
    res_id = f'kb_{jid}'
    if not any(r.get('id') == res_id for r in resources):
        count = counter.get(jid, 0)
        resources.append({
            'id': res_id,
            'title': f'{job_names[job_id_str]}专业知识库',
            'description': f'包含{job_names[job_id_str]}岗位相关的{count}个专业知识条目',
            'type': 'knowledge_base',
            'job_role': jid,
            'source': '各相关专业知识库',
            'entry_count': count,
        })

with open(res_path, 'w', encoding='utf-8') as f:
    json.dump(resources, f, ensure_ascii=False, indent=2)
print(f'Resources: {len(resources)} entries')
for k in sorted(counter.keys()): print(f'  {k}: {counter[k]}')
