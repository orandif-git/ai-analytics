from sqlalchemy import text
from sqlalchemy.orm import Session


def rule_matches(rule, kind: str, label: str | None, data: dict) -> bool:
    if rule["event_kind"] != kind:
        return False
    if rule["label"] and rule["label"] != label:
        return False
    for key in ("direction", "line_id", "zone_id"):
        wanted = (rule["params"] or {}).get(key)
        if wanted and data.get(key) != wanted:
            return False
    return True


def fire_rule(s: Session, rule, camera_id, tenant_id) -> bool:
    """Atomically claim the cooldown slot for (rule, camera). True when this event may notify."""
    return s.execute(
        text(
            "INSERT INTO rule_fires (rule_id, camera_id, tenant_id, last_fired_at) VALUES (:r, :c, :t, now()) "
            "ON CONFLICT (rule_id, camera_id) DO UPDATE SET last_fired_at = now() "
            "WHERE rule_fires.last_fired_at <= now() - make_interval(secs => :cd) RETURNING 1"
        ),
        {"r": rule["id"], "c": camera_id, "t": tenant_id, "cd": rule["cooldown_s"]},
    ).first() is not None
