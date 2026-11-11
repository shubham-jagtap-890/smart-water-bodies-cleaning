import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, distanceM, geoPayload, NEAR_M, preparePhoto } from "../api.js";
import MapView from "../components/MapView.jsx";

export default function Report() {
  const nav = useNavigate();
  const [desc, setDesc] = useState("");
  const [p, setP] = useState(null);               // prepared photo: { image, photo, device, err }
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejected, setRejected] = useState(null);

  async function onFile(e) {
    const f = e.target.files[0]; if (!f) return;
    setError(""); setRejected(null); setReading(true);
    setP(await preparePhoto(f));
    setReading(false);
  }

  const away = p?.photo && p?.device ? distanceM(p.photo, p.device) : null;
  const tooFar = away != null && away > NEAR_M;
  const ready = p?.image && p?.photo && p?.device && !tooFar;

  async function submit(e) {
    e.preventDefault(); setError(""); setRejected(null);
    if (!ready) return setError("The photo needs a geotag and you must be near that location");
    setBusy(true);
    try {
      const r = await api("/complaints", { method: "POST", body: { description: desc, ...geoPayload(p) } });
      if (r.complaint.status === "REJECTED") setRejected(r.complaint);
      else nav(`/complaints/${r.complaint.id}`);
    } catch (er) { setError(er.message); } finally { setBusy(false); }
  }

  const markers = [];
  if (p?.photo) markers.push({ ...p.photo, color: "#dc2626", radius: 10, label: "Photo geotag (complaint location)" });
  if (p?.device) markers.push({ ...p.device, color: "#2563eb", radius: 7, label: "Your device now" });

  return (
    <form className="card" onSubmit={submit}>
      <h2>Report water pollution</h2>
      <p className="muted">Upload a <b>geotagged photo</b> taken at the site. The complaint location is read from the photo,
        and you must be within {NEAR_M} m of that location while uploading.</p>
      <label>What is wrong?
        <textarea rows="3" value={desc} onChange={(e) => setDesc(e.target.value)} required minLength={10}
          placeholder="e.g. Plastic and garbage dumped on the west bank of the lake" />
      </label>
      <label>Geotagged photo
        <input type="file" accept="image/jpeg,image/heic,image/heif,image/*" onChange={onFile} />
      </label>
      {reading && <p className="muted">Reading photo geotag and your location...</p>}
      {p?.image && <img className="preview" src={p.image} alt="preview" />}
      {p && !reading && (
        <div className="muted">
          Photo geotag: <b>{p.photo ? `${p.photo.lat.toFixed(5)}, ${p.photo.lng.toFixed(5)}` : "not found"}</b><br />
          Your device: <b>{p.device ? `${p.device.lat.toFixed(5)}, ${p.device.lng.toFixed(5)}` : "not available"}</b><br />
          {away != null && <>Distance between photo location and you: <b style={{ color: tooFar ? "#b91c1c" : "#15803d" }}>{Math.round(away)} m
            {tooFar ? ` (must be within ${NEAR_M} m)` : " - OK"}</b></>}
        </div>
      )}
      {(p?.photo || p?.device) && <MapView height={260} markers={markers} />}
      {p?.err && <p className="error">{p.err}</p>}
      {error && <p className="error">{error}</p>}
      {rejected && <p className="error"><b>AI rejected this complaint:</b> {rejected.ai_reason}. Please upload a genuine, new photo of the polluted water body.</p>}
      <button disabled={busy || !ready}>{busy ? "Verifying photo with AI..." : "Submit complaint"}</button>
    </form>
  );
}
