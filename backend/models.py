"""Database models (SQLAlchemy). Works on SQLite (local) and PostgreSQL (Neon)."""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    """Naive UTC datetime (keeps SQLite and Postgres behaviour identical)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


class Authority(db.Model):
    __tablename__ = "authorities"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    level = db.Column(db.Integer, nullable=False)          # 1 = local, 2 = district, 3 = state
    parent_id = db.Column(db.Integer, db.ForeignKey("authorities.id"))
    lat = db.Column(db.Float)                              # centre of jurisdiction (fallback routing)
    lng = db.Column(db.Float)
    parent = db.relationship("Authority", remote_side=[id])

    def to_dict(self):
        return {"id": self.id, "name": self.name, "level": self.level, "parent_id": self.parent_id}


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="citizen")  # citizen | authority | admin
    authority_id = db.Column(db.Integer, db.ForeignKey("authorities.id"))
    created_at = db.Column(db.DateTime, default=utcnow)
    authority = db.relationship("Authority")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role,
                "authority": self.authority.to_dict() if self.authority else None}


class WaterBody(db.Model):
    __tablename__ = "water_bodies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(40), default="lake")        # river | lake | pond | reservoir
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    radius_m = db.Column(db.Float, default=1500)           # catchment used for routing
    priority = db.Column(db.Integer, default=2)            # 1 low .. 3 high
    pollution_load = db.Column(db.Float, default=0.5)      # 0..1 baseline (used by the ML model)
    authority_id = db.Column(db.Integer, db.ForeignKey("authorities.id"), nullable=False)
    authority = db.relationship("Authority")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "kind": self.kind, "lat": self.lat, "lng": self.lng,
                "priority": self.priority, "authority": self.authority.name}


class Image(db.Model):
    """Photos are stored in the DB so the app works on hosts with ephemeral disks."""
    __tablename__ = "images"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.LargeBinary, nullable=False)
    mime = db.Column(db.String(30), nullable=False)
    sha256 = db.Column(db.String(64), index=True)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    kind = db.Column(db.String(20))                        # complaint | inspection | completion
    created_at = db.Column(db.DateTime, default=utcnow)


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    water_body_id = db.Column(db.Integer, db.ForeignKey("water_bodies.id"))
    authority_id = db.Column(db.Integer, db.ForeignKey("authorities.id"))   # CURRENT owner
    description = db.Column(db.Text, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    image_id = db.Column(db.Integer, db.ForeignKey("images.id"))
    # REJECTED | ASSIGNED | ACTION_PLANNED | NO_ACTION | COMPLETED
    status = db.Column(db.String(20), nullable=False, default="ASSIGNED", index=True)
    ai_verdict = db.Column(db.String(12))                  # GENUINE | FAKE | UNVERIFIED
    ai_confidence = db.Column(db.Float)
    ai_reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=utcnow)
    assigned_at = db.Column(db.DateTime, default=utcnow)
    escalation_count = db.Column(db.Integer, default=0)
    reminded = db.Column(db.Boolean, default=False)
    top_level_overdue = db.Column(db.Boolean, default=False)
    # inspection / action plan
    inspected_at = db.Column(db.DateTime)
    inspection_image_id = db.Column(db.Integer, db.ForeignKey("images.id"))
    no_action_reason = db.Column(db.Text)
    plan_team = db.Column(db.String(200))
    plan_start = db.Column(db.DateTime)
    plan_end = db.Column(db.DateTime)
    deadline = db.Column(db.DateTime)
    # completion
    completed_at = db.Column(db.DateTime)
    completion_image_id = db.Column(db.Integer, db.ForeignKey("images.id"))
    completion_report = db.Column(db.Text)

    water_body = db.relationship("WaterBody")
    authority = db.relationship("Authority")
    user = db.relationship("User")


class Event(db.Model):
    """Action history / audit trail shown as a timeline."""
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), index=True)
    actor = db.Column(db.String(120))
    action = db.Column(db.String(40))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)


class Rating(db.Model):
    __tablename__ = "ratings"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), index=True)
    rater_role = db.Column(db.String(12))                  # citizen | authority
    stars = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=utcnow)
    __table_args__ = (db.UniqueConstraint("complaint_id", "rater_role"),)


class Cleaning(db.Model):
    """Historical cleaning record: training data for the prediction module."""
    __tablename__ = "cleanings"
    id = db.Column(db.Integer, primary_key=True)
    water_body_id = db.Column(db.Integer, db.ForeignKey("water_bodies.id"), index=True)
    cleaned_on = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(20), default="history")   # history | complaint
