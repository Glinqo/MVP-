"""Ability ID Alias Resolver."""
import json, os

_aliases = None

def _load():
    global _aliases
    if _aliases is None:
        p = os.path.join(os.path.dirname(__file__), "ability_id_aliases.json")
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _aliases = {m["old_id"]: m["canonical_id"] for m in data.get("mappings", [])}

def resolve_ability_id(aid: str) -> str:
    _load()
    return _aliases.get(aid, aid)

def get_all_aliases() -> dict:
    _load()
    return dict(_aliases)
