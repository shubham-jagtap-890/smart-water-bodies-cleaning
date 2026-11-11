"""Image verification: basic checks + duplicate detection + Gemini vision (free tier).

If GEMINI_API_KEY is missing or the API is unreachable the complaint is accepted as
UNVERIFIED instead of failing, so the system keeps working.
"""
import base64
import hashlib
import io
import json
import os
import requests
from PIL import Image as PILImage, ImageStat

PROMPT = (
    "You verify citizen complaints about pollution at water bodies (river, lake, pond, reservoir). "
    "Look at the photo and answer ONLY with JSON: "
    '{"is_water_body": bool, "pollution_visible": bool, "looks_like_screenshot_or_stock": bool, '
    '"confidence": number between 0 and 1, "reason": "max 20 words"}. '
    "pollution_visible is true for visible garbage, plastic, sewage, oil, foam, discoloured water, "
    "dead fish, algae bloom or dumped waste at or near the water."
)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def basic_checks(raw: bytes):
    """Return a reason string if the image is obviously unusable, else None."""
    try:
        img = PILImage.open(io.BytesIO(raw))
        img.load()
    except Exception:
        return "File is not a valid image"
    if min(img.size) < 200:
        return "Image resolution is too low"
    stat = ImageStat.Stat(img.convert("L"))
    if stat.stddev[0] < 8:
        return "Image looks blank or uniform"
    return None


def _gemini(raw: bytes, mime: str):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Gemini error: GEMINI_API_KEY is missing")
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    body = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(raw).decode()
                    }
                }
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0
        }
    }

    try:
        r = requests.post(
            url,
            json=body,
            headers={"x-goog-api-key": key},
            timeout=25
        )

        r.raise_for_status()

        response_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(response_text)

        if not isinstance(result, dict):
            raise ValueError("Gemini returned invalid JSON structure")

        required = [
            "is_water_body",
            "pollution_visible",
            "looks_like_screenshot_or_stock",
            "confidence",
            "reason"
        ]

        if not all(field in result for field in required):
            raise ValueError("Gemini response is missing required fields")

        if not all(
            isinstance(result[field], bool)
            for field in required[:3]
        ):
            raise ValueError("Gemini returned invalid boolean fields")

        confidence = float(result["confidence"])

        if not 0 <= confidence <= 1:
            raise ValueError("Invalid confidence value")

        result["confidence"] = confidence

        return result

    except requests.exceptions.HTTPError as e:
        print("Gemini HTTP error:", e)
        if e.response is not None:
            print("Gemini response:", e.response.text[:1000])
        return None

    except requests.exceptions.RequestException as e:
        print("Gemini network error:", repr(e))
        return None

    except (KeyError, IndexError, TypeError, ValueError) as e:
        print("Gemini response parsing error:", repr(e))
        return None

    except Exception as e:
        print("Unexpected Gemini error:", repr(e))
        return None



def verify_complaint_image(raw: bytes, mime: str, known_hashes: set):
    h = sha256(raw)
    problem = basic_checks(raw)
    if problem:
        return {"verdict": "FAKE", "confidence": 1.0, "reason": problem, "sha256": h}
    if h in known_hashes:
        return {"verdict": "FAKE", "confidence": 1.0,
                "reason": "This exact photo was already submitted in another complaint", "sha256": h}
    res = _gemini(raw, mime)
    if res is None:
        return {"verdict": "UNVERIFIED", "confidence": 0.0,
                "reason": "AI check unavailable - flagged for manual review", "sha256": h}
    conf = float(res.get("confidence", 0.5))
    genuine = bool(res.get("is_water_body")) and bool(res.get("pollution_visible")) \
        and not bool(res.get("looks_like_screenshot_or_stock"))
    reason = str(res.get("reason", ""))[:280]
    if genuine:
        return {"verdict": "GENUINE", "confidence": conf, "reason": reason, "sha256": h}
    if conf >= 0.6:
        return {"verdict": "FAKE", "confidence": conf, "reason": reason or "No water-body pollution visible", "sha256": h}
    return {"verdict": "UNVERIFIED", "confidence": conf, "reason": "Low-confidence AI result: " + reason, "sha256": h}
