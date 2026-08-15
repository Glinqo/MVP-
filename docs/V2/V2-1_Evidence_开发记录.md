# V2-1: Evidence Engine + Learner State Foundation

## 创建文件
- app/services/evidence/__init__.py
- app/services/evidence/event_schema.py (LearningEvent V2 Schema, xAPI-like Actor-Verb-Object)
- app/services/evidence/event_store.py (SQLite append-only, idempotent, indexed)
- app/services/evidence/event_bus.py (EventBus + Processor pipeline)
- app/services/evidence/event_query.py (structured event queries)
- app/services/evidence/event_processors.py (LegacyEventAdapter, EventClassifier)
- app/services/state/__init__.py
- app/services/state/learner_state.py (LearnerState, AbilityState, RuleBasedStateModel, BKT model interface)

## 编译状态
- event_schema.py: OK
- event_store.py: OK
- event_bus.py: OK
- event_query.py: OK
- event_processors.py: OK
- learner_state.py: OK
- ability_id_aliases.py: OK (Python wrapper for JSON)

## 待完成 (V2-1B/C/D)
- Event Bus连接到现有 Server API
- Legacy Adapter实际接入旧Event数据
- pyBKT Adapter (需pip install pybkt)
- Q-matrix / CDM实验接口
