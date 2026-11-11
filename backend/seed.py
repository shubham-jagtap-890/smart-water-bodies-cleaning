"""Demo data. Names/coordinates are SAMPLE data around Vita & Sangli - replace with real ones
(or add them through the DB / an admin script) before real use."""
import os
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
from models import db, Authority, User, WaterBody, Cleaning
from predictor import festival_window, _true_interval


def seed_if_empty():
    if Authority.query.first():
        return False
    rng = random.Random(11)
    state = Authority(name="Regional Pollution Control Office (State) - DEMO", level=3, lat=18.52, lng=73.85)
    dist = Authority(name="Sangli District Water Committee - DEMO", level=2, parent=state, lat=16.85, lng=74.58)
    vita = Authority(name="Vita Municipal Council - DEMO", level=1, parent=dist, lat=17.27, lng=74.54)
    sangli = Authority(name="Sangli City Corporation - DEMO", level=1, parent=dist, lat=16.85, lng=74.58)
    db.session.add_all([state, dist, vita, sangli]); db.session.flush()

    pw = lambda p: generate_password_hash(os.getenv("DEMO_PASSWORD", p))
    db.session.add_all([
        User(name="Admin", email="admin@demo.com", password_hash=pw("admin123"), role="admin"),
        User(name="Vita Officer", email="vita@demo.com", password_hash=pw("vita123"), role="authority", authority=vita),
        User(name="Sangli Officer", email="sangli@demo.com", password_hash=pw("sangli123"), role="authority", authority=sangli),
        User(name="District Officer", email="district@demo.com", password_hash=pw("district123"), role="authority", authority=dist),
        User(name="State Officer", email="state@demo.com", password_hash=pw("state123"), role="authority", authority=state),
        User(name="Demo Citizen", email="citizen@demo.com", password_hash=pw("citizen123"), role="citizen"),
    ])
    bodies = [
        ("Demo Lake A (Vita)", "lake", 17.2712, 74.5391, vita, 3, 0.8),
        ("Demo Pond B (Vita)", "pond", 17.2590, 74.5520, vita, 2, 0.5),
        ("Demo River Ghat C (Sangli)", "river", 16.8530, 74.5700, sangli, 3, 0.9),
        ("Demo Reservoir D (Sangli)", "reservoir", 16.8700, 74.6000, sangli, 1, 0.3),
        ("Demo Pond E (Sangli)", "pond", 16.8400, 74.5900, sangli, 2, 0.6),
    ]
    for name, kind, lat, lng, auth, pr, load in bodies:
        wb = WaterBody(name=name, kind=kind, lat=lat, lng=lng, authority=auth, priority=pr, pollution_load=load)
        db.session.add(wb); db.session.flush()
        d = date.today() - timedelta(days=rng.randint(120, 200))
        while d < date.today() - timedelta(days=3):          # synthetic cleaning history
            db.session.add(Cleaning(water_body_id=wb.id, cleaned_on=d, source="history"))
            fest = festival_window(d)
            d += timedelta(days=int(_true_interval(pr, load, fest, 1, None) + rng.randint(-8, 8)))
    db.session.commit()
    return True
