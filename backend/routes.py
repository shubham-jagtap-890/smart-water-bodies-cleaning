"""REST API. Roles: citizen | authority (levels 1-3) | admin."""
import base64
import os
import re
from datetime import datetime, timedelta
from functools import wraps

import jwt
import requests
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

import ai_check
import predictor
from escalation import run_escalation
from geo import exif_gps, haversine_m, route_complaint
from models import (Authority, Cleaning, Complaint, Event, Image, Rating, User, WaterBody,
                    db, iso, utcnow)

api = Blueprint("api", __name__, url_prefix="/api")
OPEN = ["ASSIGNED", "ACTION_PLANNED"]


# ----------------------------------------------------------------- helpers
def err(msg, code=400):
    return jsonify(error=msg), code


def auth(roles=None, optional=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            user, h = None, request.headers.get("Authorization", "")
            if h.startswith("Bearer "):
                try:
                    p = jwt.decode(h[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
                    user = db.session.get(User, int(p["sub"]))
                except Exception:
                    user = None
            if user is None and not optional:
                return err("Please log in", 401)
            if roles and (user is None or user.role not in roles):
                return err("You are not allowed to do this", 403)
            g.user = user
            return fn(*a, **k)
        return wrapper
    return deco


def token_for(u):
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": datetime.utcnow() + timedelta(days=7)},
                      current_app.config["SECRET_KEY"], algorithm="HS256")


def descendants(authority_id):
    ids, frontier = {authority_id}, [authority_id]
    while frontier:
        kids = [a.id for a in Authority.query.filter(Authority.parent_id.in_(frontier)).all()]
        frontier = [k for k in kids if k not in ids]
        ids.update(frontier)
    return ids


def num(v, lo, hi, name):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is required")
    if not lo <= f <= hi:
        raise ValueError(f"{name} is out of range")
    return f


def read_image(data_url):
    m = re.match(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("A photo is required (JPEG/PNG/WebP)")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 2_500_000:
        raise ValueError("Photo is too large (max 2.5 MB)")
    return m.group(1), raw


def geotagged_image(body, kind, near=None, tolerance=None):
    """The PHOTO must carry a geotag (EXIF GPS) and the uploader's DEVICE must be close to that spot.

    * photo location : EXIF read on the server if present, else the EXIF the browser read before resizing
    * device location: browser GPS at upload time (must be within DEVICE_NEAR_M of the photo location)
    * near/tolerance : optional extra check that the photo is close to the complaint site
    """
    mime, raw = read_image(body.get("image"))
    bad = ai_check.basic_checks(raw)
    if bad:
        raise ValueError(bad)

    lat, lng = exif_gps(raw)
    source = "photo geotag"
    if lat is None:
        try:
            lat, lng = num(body.get("photo_lat"), -90, 90, "Photo latitude"), num(body.get("photo_lng"), -180, 180, "Photo longitude")
        except ValueError:
            lat = lng = None
    try:
        dlat, dlng = num(body.get("device_lat"), -90, 90, "Device latitude"), num(body.get("device_lng"), -180, 180, "Device longitude")
    except ValueError:
        dlat = dlng = None

    if lat is None:
        if os.getenv("ALLOW_DEVICE_GPS_FALLBACK", "false").lower() == "true" and dlat is not None:
            lat, lng, source = dlat, dlng, "device GPS (photo had no geotag)"
        else:
            raise ValueError("This photo has no geotag. Turn on 'Location tag' in your camera app, take the photo again and upload that file")
    if dlat is None:
        raise ValueError("Allow location access so we can confirm you are at the photo location")

    near_m = float(os.getenv("DEVICE_NEAR_M", "200"))
    away = haversine_m(lat, lng, dlat, dlng)
    if source == "photo geotag" and away > near_m:
        raise ValueError(f"You are {away:.0f} m away from where this photo was taken (allowed: {near_m:.0f} m). Upload it from the site")
    if near is not None:
        d = haversine_m(lat, lng, near[0], near[1])
        if d > tolerance:
            raise ValueError(f"Photo location is {d:.0f} m from the complaint site (allowed: {tolerance:.0f} m)")
    img = Image(data=raw, mime=mime, sha256=ai_check.sha256(raw), lat=lat, lng=lng, kind=kind)
    img.geo_source = f"{source}; uploader {away:.0f} m from photo location"
    db.session.add(img)
    db.session.flush()
    return img


def log(c, actor, action, note=""):
    db.session.add(Event(complaint_id=c.id, actor=actor, action=action, note=note))


def img_url(i):
    return f"/api/images/{i}" if i else None


def complaint_dict(c, detail=False):
    d = {
        "id": c.id, "status": c.status, "description": c.description, "lat": c.lat, "lng": c.lng,
        "water_body": c.water_body.name if c.water_body else None,
        "authority": c.authority.name if c.authority else None,
        "authority_level": c.authority.level if c.authority else None,
        "created_at": iso(c.created_at), "assigned_at": iso(c.assigned_at),
        "escalation_count": c.escalation_count or 0, "top_level_overdue": bool(c.top_level_overdue),
        "ai_verdict": c.ai_verdict, "ai_confidence": c.ai_confidence, "ai_reason": c.ai_reason,
        "image": img_url(c.image_id), "deadline": iso(c.deadline), "completed_at": iso(c.completed_at),
        "on_time": (c.completed_at <= c.deadline) if (c.completed_at and c.deadline) else None,
    }
    if detail:
        evs = Event.query.filter_by(complaint_id=c.id).order_by(Event.created_at, Event.id).all()
        d.update({
            "inspection_image": img_url(c.inspection_image_id), "inspected_at": iso(c.inspected_at),
            "no_action_reason": c.no_action_reason, "plan_team": c.plan_team,
            "plan_start": iso(c.plan_start), "plan_end": iso(c.plan_end),
            "completion_image": img_url(c.completion_image_id), "completion_report": c.completion_report,
            "events": [{"actor": e.actor, "action": e.action, "note": e.note, "at": iso(e.created_at)} for e in evs],
            "ratings": [{"by": r.rater_role, "stars": r.stars, "comment": r.comment}
                        for r in Rating.query.filter_by(complaint_id=c.id).all()],
        })
    return d


def parse_day(s, name, end_of_day=False):
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a date (YYYY-MM-DD)")
    return d.replace(hour=23, minute=59) if end_of_day else d


# ----------------------------------------------------------------- auth
@api.post("/auth/register")
def register():
    b = request.get_json(force=True, silent=True) or {}
    name, email, pw = (b.get("name") or "").strip(), (b.get("email") or "").strip().lower(), b.get("password") or ""
    if len(name) < 2 or "@" not in email or len(pw) < 6:
        return err("Enter a name, a valid email and a password of at least 6 characters")
    if User.query.filter_by(email=email).first():
        return err("This email is already registered", 409)
    u = User(name=name, email=email, password_hash=generate_password_hash(pw), role="citizen")
    db.session.add(u)
    db.session.commit()
    return jsonify(token=token_for(u), user=u.to_dict()), 201


@api.post("/auth/login")
def login():
    b = request.get_json(force=True, silent=True) or {}
    u = User.query.filter_by(email=(b.get("email") or "").strip().lower()).first()
    if not u or not check_password_hash(u.password_hash, b.get("password") or ""):
        return err("Wrong email or password", 401)
    return jsonify(token=token_for(u), user=u.to_dict())


@api.get("/auth/me")
@auth()
def me():
    return jsonify(user=g.user.to_dict())


# ----------------------------------------------------------------- complaints
@api.post("/complaints")
@auth(["citizen"])
def create_complaint():
    b = request.get_json(force=True, silent=True) or {}
    try:
        desc = (b.get("description") or "").strip()
        if len(desc) < 10:
            raise ValueError("Please describe the problem (at least 10 characters)")
        img = geotagged_image(b, "complaint")
        lat, lng = img.lat, img.lng            # complaint location = the photo's geotag
    except ValueError as e:
        db.session.rollback()
        return err(str(e))

    day_ago = utcnow() - timedelta(hours=24)
    if Complaint.query.filter(Complaint.user_id == g.user.id, Complaint.created_at >= day_ago).count() >= 5:
        return err("Daily limit reached (5 complaints per 24 hours)", 429)
    for o in Complaint.query.filter(Complaint.user_id == g.user.id, Complaint.status.in_(OPEN)).all():
        if haversine_m(lat, lng, o.lat, o.lng) < 100:
            return err(f"You already have an open complaint (#{o.id}) at this location", 409)

    known = {h for (h,) in db.session.query(Image.sha256).filter(Image.kind == "complaint", Image.id != img.id)}
    res = ai_check.verify_complaint_image(img.data, img.mime, known)
    c = Complaint(user_id=g.user.id, description=desc, lat=lat, lng=lng, image_id=img.id,
                  ai_verdict=res["verdict"], ai_confidence=res["confidence"], ai_reason=res["reason"])
    db.session.add(c)
    db.session.flush()
    log(c, g.user.name, "SUBMITTED", f"{desc[:200]} | location: {lat:.5f}, {lng:.5f} ({img.geo_source})")
    if res["verdict"] == "FAKE":
        c.status = "REJECTED"
        log(c, "AI", "REJECTED", res["reason"])
    else:
        wb, authority, note = route_complaint(lat, lng)
        if authority is None:
            db.session.rollback()
            return err("No authority is configured for this location yet", 422)
        c.water_body_id, c.authority_id, c.status = (wb.id if wb else None), authority.id, "ASSIGNED"
        c.assigned_at = utcnow()
        log(
    c,
    "AI",
    res["verdict"],
    f"Confidence: {res['confidence']:.2f} - {res['reason']}"
)
        log(c, "System", "ASSIGNED", f"{note}. Assigned to {authority.name}")
    db.session.commit()
    return jsonify(complaint=complaint_dict(c, True)), 201


@api.get("/complaints")
@auth()
def list_complaints():
    run_escalation()
    u, q = g.user, Complaint.query
    if u.role == "citizen":
        q = q.filter(Complaint.user_id == u.id)
    elif u.role == "authority":
        q = q.filter(Complaint.authority_id.in_(descendants(u.authority_id)))
    if request.args.get("status"):
        q = q.filter(Complaint.status == request.args["status"])
    out = []
    for c in q.order_by(Complaint.created_at.desc()).limit(300).all():
        d = complaint_dict(c)
        d["actionable"] = bool(u.role == "authority" and c.authority_id == u.authority_id and c.status in OPEN)
        out.append(d)
    return jsonify(complaints=out)


@api.get("/complaints/<int:cid>")
@auth(optional=True)
def get_complaint(cid):
    c = db.session.get(Complaint, cid)
    if not c:
        return err("Complaint not found", 404)
    d = complaint_dict(c, True)
    u = g.user
    d["can_act"] = bool(u and u.role == "authority" and c.authority_id == u.authority_id and c.status in OPEN)
    d["can_rate"] = False
    if u and c.status == "COMPLETED":
        role = "citizen" if (u.role == "citizen" and c.user_id == u.id) else \
               "authority" if (u.role == "authority" and u.authority_id in descendants(c.authority_id) | {c.authority_id}) else None
        if role and not Rating.query.filter_by(complaint_id=c.id, rater_role=role).first():
            d["can_rate"] = True
    return jsonify(complaint=d)


def _owned_open(cid, status):
    c = db.session.get(Complaint, cid)
    if not c:
        return None, err("Complaint not found", 404)
    if c.authority_id != g.user.authority_id:
        return None, err("This complaint is not assigned to your authority", 403)
    if c.status != status:
        return None, err(f"Complaint is {c.status}, expected {status}", 409)
    return c, None


@api.post("/complaints/<int:cid>/inspect")
@auth(["authority"])
def inspect(cid):
    c, e = _owned_open(cid, "ASSIGNED")
    if e:
        return e
    b = request.get_json(force=True, silent=True) or {}
    try:
        img = geotagged_image(b, "inspection", near=(c.lat, c.lng), tolerance=current_app.config["GEO_TOLERANCE_M"])
        decision = b.get("decision")
        if decision == "NO_ACTION":
            reason = (b.get("reason") or "").strip()
            if len(reason) < 5:
                raise ValueError("Give the reason why no action is possible")
            c.status, c.no_action_reason = "NO_ACTION", reason
            note = f"No action possible: {reason}"
        elif decision == "ACTION":
            team = (b.get("team") or "").strip()
            if not team:
                raise ValueError("Enter the names of the cleaning team")
            start = parse_day(b.get("start"), "Start date")
            end = parse_day(b.get("end"), "End date", True)
            dl = parse_day(b.get("deadline"), "Deadline", True)
            if end < start or dl < end.replace(hour=0, minute=0):
                raise ValueError("Dates must satisfy start <= end <= deadline")
            c.status, c.plan_team, c.plan_start, c.plan_end, c.deadline = "ACTION_PLANNED", team, start, end, dl
            note = f"Team: {team}; {b['start']} to {b['end']}; deadline {b['deadline']}"
        else:
            raise ValueError("Choose ACTION or NO_ACTION")
    except ValueError as ex:
        db.session.rollback()
        return err(str(ex))
    c.inspection_image_id, c.inspected_at = img.id, utcnow()
    log(c, g.user.name, "INSPECTED", note)
    db.session.commit()
    return jsonify(complaint=complaint_dict(c, True))


@api.post("/complaints/<int:cid>/complete")
@auth(["authority"])
def complete(cid):
    c, e = _owned_open(cid, "ACTION_PLANNED")
    if e:
        return e
    b = request.get_json(force=True, silent=True) or {}
    try:
        report = (b.get("report") or "").strip()
        if len(report) < 10:
            raise ValueError("Write a short completion report (at least 10 characters)")
        img = geotagged_image(b, "completion", near=(c.lat, c.lng), tolerance=current_app.config["GEO_TOLERANCE_M"])
    except ValueError as ex:
        db.session.rollback()
        return err(str(ex))
    c.status, c.completed_at, c.completion_image_id, c.completion_report = "COMPLETED", utcnow(), img.id, report
    if c.water_body_id:
        db.session.add(Cleaning(water_body_id=c.water_body_id, cleaned_on=utcnow().date(), source="complaint"))
    late = c.deadline and c.completed_at > c.deadline
    log(c, g.user.name, "COMPLETED", ("(after the deadline) " if late else "") + report[:200])
    db.session.commit()
    predictor.invalidate()
    return jsonify(complaint=complaint_dict(c, True))


@api.post("/complaints/<int:cid>/rate")
@auth(["citizen", "authority"])
def rate(cid):
    c = db.session.get(Complaint, cid)
    if not c or c.status != "COMPLETED":
        return err("Ratings are possible only for completed complaints", 409)
    u = g.user
    if u.role == "citizen" and c.user_id != u.id:
        return err("Only the reporter can rate", 403)
    if u.role == "authority" and u.authority_id not in descendants(c.authority_id) | {c.authority_id}:
        return err("Not your complaint", 403)
    b = request.get_json(force=True, silent=True) or {}
    try:
        stars = int(b.get("stars"))
    except (TypeError, ValueError):
        return err("Stars must be 1 to 5")
    if not 1 <= stars <= 5:
        return err("Stars must be 1 to 5")
    if Rating.query.filter_by(complaint_id=cid, rater_role=u.role).first():
        return err("Already rated", 409)
    db.session.add(Rating(complaint_id=cid, rater_role=u.role, stars=stars, comment=(b.get("comment") or "")[:400]))
    log(c, u.name, "RATED", f"{u.role}: {stars}/5")
    db.session.commit()
    return jsonify(ok=True)


@api.post("/admin/complaints/<int:cid>/age")
@auth(["admin"])
def age(cid):
    """Demo helper: pretend time has passed so escalation can be shown live in the viva."""
    c = db.session.get(Complaint, cid)
    if not c or c.status not in OPEN:
        return err("Only open complaints can be aged", 409)
    shift = timedelta(hours=current_app.config["RESPONSE_HOURS"] + 1)
    c.assigned_at -= shift
    if c.deadline:
        c.deadline -= timedelta(days=30)
    log(c, g.user.name, "DEMO_AGE", "Admin moved the clock forward to demonstrate escalation")
    db.session.commit()
    run_escalation()
    return jsonify(complaint=complaint_dict(c, True))


# ----------------------------------------------------------------- public data
@api.get("/images/<int:iid>")
def image(iid):
    i = db.session.get(Image, iid)
    if not i:
        return err("Not found", 404)
    r = current_app.response_class(i.data, mimetype=i.mime)
    r.headers["Cache-Control"] = "public, max-age=86400"
    return r


@api.get("/waterbodies")
def waterbodies():
    return jsonify(water_bodies=[w.to_dict() for w in WaterBody.query.all()])


@api.get("/waterbodies/<int:wid>/weather")
def weather(wid):
    key, w = current_app.config["OPENWEATHER_KEY"], db.session.get(WaterBody, wid)
    if not w or not key:
        return jsonify(weather=None)
    try:
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"lat": w.lat, "lon": w.lng, "appid": key, "units": "metric"}, timeout=8).json()
        return jsonify(weather={"temp": r["main"]["temp"], "humidity": r["main"]["humidity"],
                                "desc": r["weather"][0]["description"], "rain_1h": r.get("rain", {}).get("1h", 0)})
    except Exception:
        return jsonify(weather=None)


@api.get("/public/complaints")
def public_complaints():
    run_escalation()
    rows = Complaint.query.filter(Complaint.status != "REJECTED").order_by(Complaint.created_at.desc()).limit(200).all()
    return jsonify(complaints=[complaint_dict(c) for c in rows])


@api.get("/public/stats")
def stats():
    run_escalation()
    by = dict(db.session.query(Complaint.status, func.count()).group_by(Complaint.status).all())
    done = Complaint.query.filter_by(status="COMPLETED").all()
    days = [(c.completed_at - c.created_at).total_seconds() / 86400 for c in done]
    on_time = [c.completed_at <= c.deadline for c in done if c.deadline]
    avg = lambda role: (lambda v: round(float(v), 2) if v else None)(
        db.session.query(func.avg(Rating.stars)).filter(Rating.rater_role == role).scalar())
    perf = []
    for a in Authority.query.order_by(Authority.level, Authority.name).all():
        ids = [c.id for c in Complaint.query.filter_by(authority_id=a.id, status="COMPLETED").all()]
        rt = db.session.query(func.avg(Rating.stars)).filter(Rating.complaint_id.in_(ids), Rating.rater_role == "citizen").scalar() if ids else None
        perf.append({"authority": a.name, "level": a.level,
                     "open": Complaint.query.filter(Complaint.authority_id == a.id, Complaint.status.in_(OPEN)).count(),
                     "completed": len(ids), "citizen_rating": round(float(rt), 2) if rt else None})
    return jsonify(
        total=sum(v for k, v in by.items() if k != "REJECTED"), by_status=by, rejected_fake=by.get("REJECTED", 0),
        escalated=Complaint.query.filter(Complaint.escalation_count > 0).count(),
        avg_resolution_days=round(sum(days) / len(days), 1) if days else None,
        on_time_pct=round(100 * sum(on_time) / len(on_time)) if on_time else None,
        avg_citizen_rating=avg("citizen"), avg_authority_rating=avg("authority"), authorities=perf)


# ----------------------------------------------------------------- AI prediction
@api.get("/predictions")
@auth(["authority", "admin"])
def predictions():
    return jsonify(predictions=predictor.predict_all(), metrics=predictor.metrics())


@api.get("/predictions/metrics")
def prediction_metrics():
    return jsonify(metrics=predictor.metrics())


# ----------------------------------------------------------------- ops
@api.get("/health")
def health():
    return jsonify(status="ok")


@api.route("/cron/escalate", methods=["GET", "POST"])
def cron():
    if request.args.get("key") != current_app.config["CRON_KEY"]:
        return err("Forbidden", 403)
    return jsonify(escalated=run_escalation())
