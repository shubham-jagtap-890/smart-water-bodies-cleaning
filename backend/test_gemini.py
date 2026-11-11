"""Checks that your Gemini key works:  python test_gemini.py
Prints the key length only (never the key), the usable flash models, and a real test call."""
import base64, io, os, random
import requests
from pathlib import Path
from PIL import Image

env = Path(__file__).parent / ".env"
print(".env found:", env.exists())
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.split(" #", 1)[0].strip().strip('"').strip("'"))

key = os.getenv("GEMINI_API_KEY", "")
print("key length:", len(key))
if not key:
    raise SystemExit("KEY NOT FOUND - check backend/.env (GEMINI_API_KEY=...)")

r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key}, timeout=20)
print("list status:", r.status_code)
if r.status_code != 200:
    raise SystemExit(r.text[:300])
names = [m["name"].replace("models/", "") for m in r.json().get("models", [])
         if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
         and not any(x in m["name"] for x in ("tts", "image", "live", "audio"))]
print("Usable flash models:", ", ".join(names))

model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
print("Testing model:", model)
im = Image.new("RGB", (300, 300))
im.putdata([(random.randint(0, 255),) * 3 for _ in range(300 * 300)])
buf = io.BytesIO(); im.save(buf, "JPEG")
body = {"contents": [{"parts": [{"text": 'Reply only with JSON: {"ok": true}'},
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}]}],
        "generationConfig": {"response_mime_type": "application/json"}}
r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  json=body, headers={"x-goog-api-key": key}, timeout=30)
print("test call status:", r.status_code, "(200 = working)")
if r.status_code != 200:
    print(r.text[:400])
