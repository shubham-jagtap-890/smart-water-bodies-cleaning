# AI-Based Smart Water Bodies Cleaning Prediction, Action Tracking and Escalation System

Citizens report water-body pollution with a geotagged photo. AI rejects fake photos, the complaint is routed to the
responsible authority, every action is tracked with geotagged before/after evidence, overdue cases escalate
automatically, and an ML model predicts the next cleaning date for each water body.

## Workflow (matches the synopsis, section 7)
1. Citizen uploads a GEOTAGGED photo (the complaint location is read from the photo's EXIF GPS; the citizen's device must be within 200 m of it)
2. AI check (blank/duplicate/Gemini vision) rejects fakes
3. Location-based routing to the local authority  ->  4. Authority inspects with a geotagged photo (within 300 m of the site, device within 200 m of the photo)
5. "No action" (with reasons) or "Action" (team, start, end, deadline)  ->  6. Completion report + geotagged photo
7. No response / missed deadline -> auto-escalation to district, then state level  ->  8. Ratings by citizen and authority
Public dashboard shows status, escalations, resolution time, ratings and per-authority performance.

## Stack
| Part | Technology |
|---|---|
| Frontend | React (Vite), Leaflet + OpenStreetMap (free maps, no API key) |
| Backend | Python Flask, SQLAlchemy, JWT auth |
| Database | SQLite locally, PostgreSQL (Neon free) in production |
| AI / ML | Gemini vision (fake-photo check), scikit-learn RandomForest (cleaning prediction) |
| Optional | OpenWeather (weather on water-body page API) |

Note: Google Maps needs a billing account, so OpenStreetMap is used. Tailwind was replaced by plain CSS to keep the build simple.

## Run locally (Windows - two terminals)
**Terminal 1 - backend**
```bat
cd water-bodies\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
(Mac/Linux: `source venv/bin/activate`.) The API runs on http://localhost:5000 and creates the database + demo data.

**Terminal 2 - frontend**
```bat
cd water-bodies\frontend
npm install
npm run dev
```
Open http://localhost:5173

Test the whole workflow without a browser: `cd backend && python smoke_test.py` (last line must be `ALL OK`).

### Gemini (AI fake-photo check)
1. Get a free key at https://aistudio.google.com -> Get API key. Never share it or upload it to GitHub.
2. Create the file `backend/.env` (same folder as app.py) with:
```
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
SECRET_KEY=any-long-random-text
```
3. Check it: `cd backend && python test_gemini.py`, then restart `python app.py`.
Without a key, complaints are accepted as "UNVERIFIED".

### Geotag rules
* The photo must contain GPS (turn on "Location tag" in the camera app). WhatsApp-forwarded, screenshot or downloaded photos have none and are rejected.
* On Android choose the file from Files/Browse, not the Photos picker (it strips location).
* The uploader's device must be within `DEVICE_NEAR_M` (default 200 m) of the photo's location. On a laptop the browser location can be inaccurate:
  for demos set `DEVICE_NEAR_M=5000` in `backend/.env` and `NEAR_M` in `frontend/src/api.js`.
* `ALLOW_DEVICE_GPS_FALLBACK=true` uses the device GPS for photos without geotag (testing only).

Demo logins: citizen@demo.com/citizen123, vita@demo.com/vita123 (local authority), district@demo.com/district123,
state@demo.com/state123, admin@demo.com/admin123. **Change them / set SEED_DEMO=false for a real launch.**
The admin sees a "simulate delay" button on a complaint to show escalation live in the viva.

## Deploy for free (Render + Neon)  /  मोफत डिप्लॉय करा
1. **GitHub** - push this folder to a new GitHub repo.  / हा फोल्डर GitHub वर अपलोड करा.
2. **Neon database** - sign up at neon.com, create a project, copy the connection string
   (`postgresql://...?sslmode=require`).  / Neon वर free डेटाबेस बनवा आणि connection string कॉपी करा.
3. **Gemini key (optional)** - https://aistudio.google.com -> Get API key. Without it, photos are accepted as "UNVERIFIED".
   / AI फोटो-तपासणीसाठी free key घ्या.
4. **Render** - render.com -> New -> Blueprint (or Web Service -> Docker) -> select the repo, plan **Free**.
   Set `DATABASE_URL` (Neon string) and optionally `GEMINI_API_KEY`.  / Render वर repo निवडा, Free plan, आणि env variables टाका.
5. Open the `.onrender.com` URL. First load after idle takes ~1 minute (free tier sleeps after 15 min).
   / १५ मिनिटे वापर नसल्यास साइट झोपते; पहिला लोड ~१ मिनिट लागतो.

### Free-tier notes
* Render free web services sleep after 15 minutes idle and have an ephemeral disk - that is why photos and data live in the Neon database.
* Do NOT use Render's own free Postgres: it expires after 30 days. Neon's free plan has no expiry (0.5 GB, 100 compute-hours/month).
* Escalation runs whenever a dashboard is opened and via `GET /api/cron/escalate?key=<CRON_KEY>`. Add a free cron job
  (cron-job.org) calling it every 6 hours. For a viva/demo day, also ping `/api/health` every 10 min to keep the app awake
  (it does not touch the database, so Neon's compute hours are not used up).
* Photos are resized in the browser to ~1024 px; 0.5 GB holds thousands of complaints.
* Check your Gemini model name in AI Studio and set `GEMINI_MODEL` if needed; free-tier limits are low, so the app falls back gracefully.

## API overview
`POST /api/auth/register|login` - `POST /api/complaints` - `GET /api/complaints` - `POST /api/complaints/:id/inspect|complete|rate`
`GET /api/public/stats|complaints` - `GET /api/predictions` - `GET /api/predictions/metrics` - `GET /api/cron/escalate?key=`

## Project layout
```
backend/  app.py routes.py models.py geo.py ai_check.py predictor.py escalation.py seed.py smoke_test.py test_gemini.py
frontend/ src/App.jsx src/api.js src/pages/* src/components/MapView.jsx
Dockerfile  render.yaml  .env.example
```
## Honest limitations (good to mention in the viva)
* Prediction is bootstrapped with synthetic history (clearly labelled in `predictor.py`); it retrains on real cleanings as they accumulate.
  The reported accuracy is on that bootstrap data - re-measure once you have real records.
* Festival intensity is a month-level approximation; edit `FESTIVAL_BY_MONTH` for exact dates.
* The photo geotag is read in the browser and sent with the photo, so a technical user could fake it; the device-distance rule, duplicate checks and AI verification reduce (not remove) this risk.
* Demo authorities/water bodies are sample data - load real ones before real use.
