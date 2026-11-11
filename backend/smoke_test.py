"""End-to-end check of the whole workflow:  python smoke_test.py"""
import base64, io, os, random
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["RESPONSE_HOURS"] = "48"
from PIL import Image
from app import app


def photo(seed):
    random.seed(seed)
    im = Image.new("RGB", (400, 300))
    im.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(400 * 300)])
    b = io.BytesIO(); im.save(b, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


c = app.test_client()
def login(e, p):
    r = c.post("/api/auth/login", json={"email": e, "password": p}); assert r.status_code == 200, r.json
    return {"Authorization": "Bearer " + r.json["token"]}

cit, vita, dist, adm = login("citizen@demo.com", "citizen123"), login("vita@demo.com", "vita123"), login("district@demo.com", "district123"), login("admin@demo.com", "admin123")
LAT, LNG = 17.2713, 74.5392

# 1 submit
r = c.post("/api/complaints", headers=cit, json={"description": "Plastic waste floating near the ghat", "lat": LAT, "lng": LNG,
           "image": photo(1), "photo_lat": LAT, "photo_lng": LNG, "device_lat": LAT, "device_lng": LNG})
assert r.status_code == 201, r.json
cid = r.json["complaint"]["id"]; print("created", cid, r.json["complaint"]["status"], r.json["complaint"]["ai_verdict"], r.json["complaint"]["authority"])
assert r.json["complaint"]["status"] == "ASSIGNED"
# duplicate photo / nearby duplicate
assert c.post("/api/complaints", headers=cit, json={"description": "again again again", "lat": LAT, "lng": LNG, "image": photo(1), "photo_lat": LAT, "photo_lng": LNG, "device_lat": LAT, "device_lng": LNG}).status_code == 409
# blank image rejected as fake by basic check (client error)
blank = Image.new("RGB", (400, 300), (10, 10, 10)); b = io.BytesIO(); blank.save(b, "JPEG")
assert c.post("/api/complaints", headers=cit, json={"description": "blank photo test", "lat": 16.9, "lng": 74.7, "image": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode(), "photo_lat": 16.9, "photo_lng": 74.7, "device_lat": 16.9, "device_lng": 74.7}).status_code == 400
# 2 wrong authority cannot act; far photo rejected
assert c.post(f"/api/complaints/{cid}/inspect", headers=dist, json={}).status_code == 403
far = c.post(f"/api/complaints/{cid}/inspect", headers=vita, json={"decision": "ACTION", "image": photo(2), "photo_lat": 18.0, "photo_lng": 75.0, "device_lat": 18.0, "device_lng": 75.0})
assert far.status_code == 400 and "m from" in far.json["error"], far.json
# 3 inspect w/ plan
r = c.post(f"/api/complaints/{cid}/inspect", headers=vita, json={"decision": "ACTION", "team": "Team A, Team B", "start": "2026-11-01", "end": "2026-11-03", "deadline": "2026-11-05", "image": photo(2), "photo_lat": LAT, "photo_lng": LNG, "device_lat": LAT, "device_lng": LNG})
assert r.status_code == 200 and r.json["complaint"]["status"] == "ACTION_PLANNED", r.json
# 4 complete
r = c.post(f"/api/complaints/{cid}/complete", headers=vita, json={"report": "Waste removed and disposed.", "image": photo(3), "photo_lat": LAT, "photo_lng": LNG, "device_lat": LAT, "device_lng": LNG})
assert r.json["complaint"]["status"] == "COMPLETED", r.json
# 5 ratings
assert c.post(f"/api/complaints/{cid}/rate", headers=cit, json={"stars": 5}).status_code == 200
assert c.post(f"/api/complaints/{cid}/rate", headers=vita, json={"stars": 4}).status_code == 200
assert c.post(f"/api/complaints/{cid}/rate", headers=cit, json={"stars": 5}).status_code == 409
# 6 escalation: new complaint, age it
r = c.post("/api/complaints", headers=cit, json={"description": "Sewage entering pond at north side", "lat": 17.2591, "lng": 74.5521, "image": photo(4), "photo_lat": 17.2591, "photo_lng": 74.5521, "device_lat": 17.2591, "device_lng": 74.5521})
c2 = r.json["complaint"]["id"]
r = c.post(f"/api/admin/complaints/{c2}/age", headers=adm)
assert r.json["complaint"]["authority_level"] == 2 and r.json["complaint"]["escalation_count"] == 1, r.json
r = c.get(f"/api/complaints/{c2}"); print([e["action"] for e in r.json["complaint"]["events"]])
# 7 stats + predictions
s = c.get("/api/public/stats").json; print({k: s[k] for k in ("total", "escalated", "avg_citizen_rating", "avg_resolution_days")})
p = c.get("/api/predictions", headers=vita).json; print(p["metrics"]); print(p["predictions"][0])
assert c.get("/api/predictions").status_code == 401
assert c.get("/api/cron/escalate?key=bad").status_code == 403

# 8 geotag rules (new): device must be near the photo location; photo must have a geotag
base = {"description": "Garbage dumped along the bank", "image": photo(9)}
r = c.post("/api/complaints", headers=cit, json={**base, "photo_lat": 17.30, "photo_lng": 74.60, "device_lat": 17.35, "device_lng": 74.65})
assert r.status_code == 400 and "away from where this photo was taken" in r.json["error"], r.json
r = c.post("/api/complaints", headers=cit, json={**base, "device_lat": 17.30, "device_lng": 74.60})
assert r.status_code == 400 and "no geotag" in r.json["error"], r.json
r = c.post("/api/complaints", headers=cit, json={**base, "photo_lat": 17.30, "photo_lng": 74.60})
assert r.status_code == 400 and "location access" in r.json["error"], r.json

# real EXIF GPS inside the JPEG (no photo_lat in the request): complaint location must come from the photo
def exif_photo(seed, lat, lng):
    random.seed(seed)
    im = Image.new("RGB", (400, 300))
    im.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(400 * 300)])
    ex = Image.Exif()
    ex[0x8825] = {1: "N", 2: (int(lat), int((lat % 1) * 60), ((lat % 1) * 60 % 1) * 60), 3: "E",
                  4: (int(lng), int((lng % 1) * 60), ((lng % 1) * 60 % 1) * 60)}
    b = io.BytesIO(); im.save(b, "JPEG", exif=ex)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

r = c.post("/api/complaints", headers=cit, json={"description": "Foam on the water surface", "image": exif_photo(10, 16.8525, 74.5816),
           "device_lat": 16.8526, "device_lng": 74.5817})
assert r.status_code == 201, r.json
cc = r.json["complaint"]
assert abs(cc["lat"] - 16.8525) < 0.001 and abs(cc["lng"] - 74.5816) < 0.001, cc
print("EXIF location used:", round(cc["lat"], 4), round(cc["lng"], 4), "->", cc["authority"])
print("ALL OK")
