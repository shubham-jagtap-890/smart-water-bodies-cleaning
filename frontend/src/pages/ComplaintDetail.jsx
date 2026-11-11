import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, distanceM, geoPayload, NEAR_M, preparePhoto, STATUS_COLOR, STATUS_LABEL, fmt } from "../api.js";
import { useAuth } from "../App.jsx";
import MapView from "../components/MapView.jsx";

// Geotagged photo (EXIF) + device location at upload time
function usePhoto() {
  const [data, setData] = useState({ image: null, photo: null, device: null, err: "" });
  const pick = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setData(await preparePhoto(f));
  };
  return [data, pick];
}

function GeoInfo({ photo, site }) {
  if (!photo.photo) return null;
  const fromSite = distanceM(photo.photo, site);
  const away = photo.device ? distanceM(photo.photo, photo.device) : null;
  return (
    <p className="muted">
      Photo geotag: <b>{photo.photo.lat.toFixed(5)}, {photo.photo.lng.toFixed(5)}</b><br />
      Distance from complaint site: <b>{Math.round(fromSite)} m</b><br />
      {away != null && <>You are <b>{Math.round(away)} m</b> from the photo location {away > NEAR_M ? `(must be within ${NEAR_M} m)` : "- OK"}</>}
    </p>
  );
}

function InspectForm({ c, done }) {
  const [photo, pick] = usePhoto();
  const [decision, setDecision] = useState("ACTION");
  const [f, setF] = useState({ team: "", start: "", end: "", deadline: "", reason: "" });
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function submit(e) {
    e.preventDefault(); setError("");
    try {
      await api(`/complaints/${c.id}/inspect`, { method: "POST", body: { decision, ...f, ...geoPayload(photo) } });
      done();
    } catch (er) { setError(er.message); }
  }
  return (
    <form className="card" onSubmit={submit}>
      <h3>Step 1 - Inspect the site</h3>
      <label>Geotagged photo from the site (must be near the complaint location)<input type="file" accept="image/*" onChange={pick} /></label>
      {photo.err && <p className="error">{photo.err}</p>}
      {photo.image && <img className="preview" src={photo.image} alt="inspection" />}
      <GeoInfo photo={photo} site={{ lat: c.lat, lng: c.lng }} />
      <label>Decision
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="ACTION">Action needed - plan cleaning</option>
          <option value="NO_ACTION">No action possible</option>
        </select></label>
      {decision === "ACTION" ? (<>
        <label>Team names<input value={f.team} onChange={set("team")} placeholder="Team A - R. Patil, S. More" required /></label>
        <div className="row">
          <label>Start<input type="date" value={f.start} onChange={set("start")} required /></label>
          <label>End<input type="date" value={f.end} onChange={set("end")} required /></label>
          <label>Deadline<input type="date" value={f.deadline} onChange={set("deadline")} required /></label>
        </div></>) : (
        <label>Reason<textarea rows="2" value={f.reason} onChange={set("reason")} required /></label>)}
      {error && <p className="error">{error}</p>}
      <button>Submit inspection</button>
    </form>
  );
}

function CompleteForm({ c, done }) {
  const [photo, pick] = usePhoto();
  const [report, setReport] = useState("");
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault(); setError("");
    try {
      await api(`/complaints/${c.id}/complete`, { method: "POST", body: { report, ...geoPayload(photo) } });
      done();
    } catch (er) { setError(er.message); }
  }
  return (
    <form className="card" onSubmit={submit}>
      <h3>Step 2 - Upload completion report</h3>
      <label>Geotagged "after" photo<input type="file" accept="image/*" onChange={pick} /></label>
      {photo.err && <p className="error">{photo.err}</p>}
      {photo.image && <img className="preview" src={photo.image} alt="completion" />}
      <GeoInfo photo={photo} site={{ lat: c.lat, lng: c.lng }} />
      <label>Work report<textarea rows="3" value={report} onChange={(e) => setReport(e.target.value)} required minLength={10} /></label>
      {error && <p className="error">{error}</p>}
      <button>Mark as completed</button>
    </form>
  );
}

function RateForm({ c, done }) {
  const [stars, setStars] = useState(5);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    try { await api(`/complaints/${c.id}/rate`, { method: "POST", body: { stars, comment } }); done(); }
    catch (er) { setError(er.message); }
  }
  return (
    <form className="card" onSubmit={submit}>
      <h3>Rate this resolution</h3>
      <label>Stars<select value={stars} onChange={(e) => setStars(+e.target.value)}>{[5, 4, 3, 2, 1].map((n) => <option key={n}>{n}</option>)}</select></label>
      <label>Comment<input value={comment} onChange={(e) => setComment(e.target.value)} /></label>
      {error && <p className="error">{error}</p>}
      <button>Submit rating</button>
    </form>
  );
}

export default function ComplaintDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [c, setC] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api(`/complaints/${id}`).then((r) => setC(r.complaint)).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  if (error) return <p className="error">{error}</p>;
  if (!c) return <div className="center">Loading...</div>;
  const age = async () => { await api(`/admin/complaints/${c.id}/age`, { method: "POST" }); load(); };

  return (
    <>
      <h1>Complaint #{c.id} <span className="badge" style={{ background: STATUS_COLOR[c.status] }}>{STATUS_LABEL[c.status]}</span></h1>
      <div className="grid2">
        <div className="card">
          <p>{c.description}</p>
          <p className="muted">Water body: <b>{c.water_body || "unregistered"}</b><br />
            Current authority: <b>{c.authority || "-"}</b>{c.escalation_count > 0 && <> (escalated {c.escalation_count}x)</>}<br />
            Reported: {fmt(c.created_at)}<br />
            AI check: <b>{c.ai_verdict}</b>{c.ai_confidence ? ` (${Math.round(c.ai_confidence * 100)}%)` : ""} - {c.ai_reason}</p>
          {c.deadline && <p>Deadline: <b>{fmt(c.deadline)}</b>{c.on_time != null && (c.on_time ? " - finished on time" : " - finished late")}</p>}
          {c.plan_team && <p>Team: {c.plan_team}<br />Planned: {fmt(c.plan_start)} to {fmt(c.plan_end)}</p>}
          {c.no_action_reason && <p>No action reason: {c.no_action_reason}</p>}
          {c.completion_report && <p>Completion report: {c.completion_report}</p>}
          {c.top_level_overdue && <p className="error">Overdue at the highest authority.</p>}
        </div>
        <MapView height={260} center={[c.lat, c.lng]} zoom={16} markers={[{ lat: c.lat, lng: c.lng, color: STATUS_COLOR[c.status] }]} />
      </div>

      <h2>Evidence</h2>
      <div className="photos">
        {c.image && <figure><img src={c.image} alt="reported" /><figcaption>Reported</figcaption></figure>}
        {c.inspection_image && <figure><img src={c.inspection_image} alt="inspection" /><figcaption>Inspection (geotagged)</figcaption></figure>}
        {c.completion_image && <figure><img src={c.completion_image} alt="after" /><figcaption>After cleaning (geotagged)</figcaption></figure>}
      </div>

      {c.can_act && c.status === "ASSIGNED" && <InspectForm c={c} done={load} />}
      {c.can_act && c.status === "ACTION_PLANNED" && <CompleteForm c={c} done={load} />}
      {c.can_rate && <RateForm c={c} done={load} />}
      {c.ratings.length > 0 && <p>Ratings: {c.ratings.map((r) => `${r.by} ${r.stars}/5${r.comment ? ` ("${r.comment}")` : ""}`).join("  |  ")}</p>}
      {user?.role === "admin" && ["ASSIGNED", "ACTION_PLANNED"].includes(c.status) &&
        <button className="secondary" onClick={age}>Demo: simulate delay (trigger escalation)</button>}

      <h2>Action history</h2>
      <ul className="timeline">
        {c.events.map((e, i) => (
          <li key={i}><b>{e.action}</b> <span className="muted">{fmt(e.at)} - {e.actor}</span><div>{e.note}</div></li>
        ))}
      </ul>
    </>
  );
}
