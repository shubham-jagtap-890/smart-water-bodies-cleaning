import { useEffect, useState } from "react";
import { api, fmtDate } from "../api.js";
import MapView from "../components/MapView.jsx";

const COLOR = { HIGH: "#dc2626", MEDIUM: "#d97706", LOW: "#16a34a" };

export default function Predictions() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api("/predictions").then(setD).catch((e) => setError(e.message)); }, []);
  if (error) return <p className="error">{error}</p>;
  if (!d) return <div className="center">Training model...</div>;
  const m = d.metrics;

  return (
    <>
      <h1>AI cleaning prediction</h1>
      <p className="muted">Predicts the next cleaning date per water body from cleaning history, priority, pollution load,
        recent complaints and festival-season activity.</p>
      <div className="stats">
        <div className="stat"><b>{m.algorithm.replace("Regressor", "")}</b><span>Model</span></div>
        <div className="stat"><b>{m.mae_days} days</b><span>Mean abs. error</span></div>
        <div className="stat"><b>{m.r2}</b><span>R&sup2; score</span></div>
        <div className="stat"><b>{Math.round(m.high_risk_accuracy * 100)}%</b><span>High-risk accuracy</span></div>
      </div>
      <MapView height={300} markers={d.predictions.map((p) => ({ lat: p.lat, lng: p.lng, color: COLOR[p.risk], radius: 11,
        label: `<b>${p.name}</b><br>Next cleaning: ${p.next_cleaning}<br>Risk: ${p.risk}` }))} />
      <div className="scroll"><table>
        <thead><tr><th>Water body</th><th>Authority</th><th>Priority</th><th>Last cleaned</th><th>Predicted interval</th><th>Next cleaning</th><th>Days left</th><th>Open complaints</th><th>Risk</th></tr></thead>
        <tbody>{d.predictions.map((p) => (
          <tr key={p.water_body_id}><td>{p.name}</td><td>{p.authority}</td><td>{p.priority}</td><td>{fmtDate(p.last_cleaned)}</td>
            <td>{p.predicted_interval_days} d</td><td><b>{fmtDate(p.next_cleaning)}</b></td>
            <td>{p.days_left < 0 ? `${-p.days_left} overdue` : p.days_left}</td><td>{p.open_complaints}</td>
            <td><span className="badge" style={{ background: COLOR[p.risk] }}>{p.risk}</span></td></tr>
        ))}</tbody>
      </table></div>
    </>
  );
}
