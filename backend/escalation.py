"""Overdue detection + automatic escalation to the higher authority.

Rules (configurable through env):
  * ASSIGNED complaint with no inspection within RESPONSE_HOURS     -> escalate one level
  * ACTION_PLANNED complaint still open after its deadline          -> escalate one level
  * A reminder event is logged once at 50% of the response window.
Free hosts sleep, so this runs lazily on dashboard requests AND via /api/cron/escalate.
"""
from datetime import timedelta
from flask import current_app
from models import db, Complaint, Event, Authority, utcnow


def _log(c, action, note):
    db.session.add(Event(complaint_id=c.id, actor="System", action=action, note=note))


def escalate(c, reason):
    cur = db.session.get(Authority, c.authority_id)
    parent = cur.parent if cur else None
    now = utcnow()
    if parent:
        _log(c, "ESCALATED", f"{reason}. Moved from {cur.name} to {parent.name}.")
        c.authority_id = parent.id
        c.escalation_count = (c.escalation_count or 0) + 1
        c.assigned_at = now
        c.status = "ASSIGNED"
        c.reminded = False
        return True
    if not c.top_level_overdue:
        c.top_level_overdue = True
        _log(c, "OVERDUE", f"{reason}. Already at the highest authority - flagged for attention.")
        return True
    return False


def run_escalation():
    window = timedelta(hours=current_app.config["RESPONSE_HOURS"])
    now = utcnow()
    changed = []
    for c in Complaint.query.filter(Complaint.status.in_(["ASSIGNED", "ACTION_PLANNED"])).all():
        if c.status == "ASSIGNED":
            waited = now - c.assigned_at
            if waited > window:
                if escalate(c, f"No response within {current_app.config['RESPONSE_HOURS']:g} h"):
                    changed.append(c.id)
            elif waited > window / 2 and not c.reminded:
                c.reminded = True
                _log(c, "REMINDER", "Reminder: complaint awaiting inspection, half of the response time is used.")
        elif c.status == "ACTION_PLANNED" and c.deadline and now > c.deadline:
            if escalate(c, "Cleaning deadline missed"):
                changed.append(c.id)
    db.session.commit()
    return changed
