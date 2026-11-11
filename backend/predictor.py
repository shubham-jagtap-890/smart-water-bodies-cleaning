"""AI prediction module: next cleaning date per water body.

Model : RandomForestRegressor (scikit-learn)
Target: days until the next cleaning is needed
Inputs: priority, baseline pollution load, month of last cleaning,
        festival activity in the following ~90 days, complaints in last 90 days.
Data  : a synthetic bootstrap set (so the demo works on day one) + the real cleaning
        history stored in the database. The model retrains whenever a cleaning is recorded.
"""
from datetime import date, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

# Approximate festival crowd/immersion intensity per month (0..1) for Maharashtra/India.
# Edit freely - e.g. Ganesh Chaturthi (Aug/Sep), Navratri/Diwali (Oct/Nov), Ashadhi Wari (Jul).
FESTIVAL_BY_MONTH = {1: 0.3, 2: 0.2, 3: 0.4, 4: 0.3, 5: 0.1, 6: 0.1,
                     7: 0.5, 8: 0.6, 9: 1.0, 10: 0.7, 11: 0.6, 12: 0.2}
HIGH_RISK_INTERVAL = 60   # bodies needing cleaning at least every 60 days are "high risk"

_state = {"model": None, "metrics": None}


def festival_window(start: date, days=90):
    pts = [start + timedelta(days=d) for d in range(10, days, 10)]
    return float(np.mean([FESTIVAL_BY_MONTH[p.month] for p in pts]))


def features(priority, load, last_clean: date, complaints_90d):
    return [priority, load, last_clean.month, festival_window(last_clean), complaints_90d]


def _true_interval(priority, load, fest, complaints, rng=None):
    v = 240 - 40 * priority - 50 * load - 40 * fest - 2.0 * complaints
    if rng is not None:
        v += rng.normal(0, 6)
    return max(14.0, v)


def _synthetic(n=900, seed=7):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for _ in range(n):
        pr = int(rng.integers(1, 4))
        load = float(rng.uniform(0.1, 1.0))
        d = date(2024, 1, 1) + timedelta(days=int(rng.integers(0, 900)))
        comp = int(rng.poisson(load * 3))
        f = features(pr, load, d, comp)
        X.append(f)
        y.append(_true_interval(pr, load, f[3], comp, rng))
    return X, y


def _real_rows():
    from models import WaterBody, Cleaning
    X, y = [], []
    for wb in WaterBody.query.all():
        rows = Cleaning.query.filter_by(water_body_id=wb.id).order_by(Cleaning.cleaned_on).all()
        for a, b in zip(rows, rows[1:]):
            X.append(features(wb.priority, wb.pollution_load, a.cleaned_on, 0))
            y.append(float((b.cleaned_on - a.cleaned_on).days))
    return X, y


def train():
    X, y = _synthetic()
    rx, ry = _real_rows()
    X, y = X + rx * 3, y + ry * 3          # real history weighted x3
    Xtr, Xte, ytr, yte = train_test_split(np.array(X), np.array(y), test_size=0.2, random_state=42)
    model = RandomForestRegressor(n_estimators=120, max_depth=10, random_state=42, n_jobs=1)
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    acc = float(np.mean((pred <= HIGH_RISK_INTERVAL) == (yte <= HIGH_RISK_INTERVAL)))
    _state["model"] = model
    _state["metrics"] = {
        "algorithm": "RandomForestRegressor", "train_rows": int(len(ytr)), "test_rows": int(len(yte)),
        "mae_days": round(float(mean_absolute_error(yte, pred)), 2),
        "r2": round(float(r2_score(yte, pred)), 3),
        "high_risk_accuracy": round(acc, 3),
        "real_cleaning_pairs": len(ry),
    }
    return _state["metrics"]


def invalidate():
    _state["model"] = None


def metrics():
    if _state["model"] is None:
        train()
    return _state["metrics"]


def predict_all():
    from models import WaterBody, Cleaning, Complaint, utcnow
    if _state["model"] is None:
        train()
    today = date.today()
    out = []
    for wb in WaterBody.query.all():
        last = Cleaning.query.filter_by(water_body_id=wb.id).order_by(Cleaning.cleaned_on.desc()).first()
        last_date = last.cleaned_on if last else today - timedelta(days=60)
        since = utcnow() - timedelta(days=90)
        open_c = Complaint.query.filter(Complaint.water_body_id == wb.id,
                                        Complaint.status.in_(["ASSIGNED", "ACTION_PLANNED"])).count()
        recent = Complaint.query.filter(Complaint.water_body_id == wb.id, Complaint.created_at >= since,
                                        Complaint.status != "REJECTED").count()
        interval = float(_state["model"].predict(np.array([features(wb.priority, wb.pollution_load, last_date, recent)]))[0])
        nxt = last_date + timedelta(days=int(round(interval)))
        left = (nxt - today).days
        if open_c >= 3 or left < 0 or left <= 14:
            risk = "HIGH"
        elif left <= 45:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        out.append({"water_body_id": wb.id, "name": wb.name, "kind": wb.kind, "lat": wb.lat, "lng": wb.lng,
                    "priority": wb.priority, "authority": wb.authority.name,
                    "last_cleaned": last_date.isoformat(), "predicted_interval_days": round(interval),
                    "next_cleaning": nxt.isoformat(), "days_left": left, "open_complaints": open_c, "risk": risk})
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda r: (order[r["risk"]], r["days_left"]))
    return out
