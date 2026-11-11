import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, STATUS_COLOR, STATUS_LABEL, fmtDate } from "../api.js";
import MapView from "../components/MapView.jsx";

const Stat = ({ label, value }) => (<div className="stat"><b>{value ?? "-"}</b><span>{label}</span></div>);

export default function Dashboard() {
  const [s, setS] = useState(null);
  const [list, setList] = useState([]);
  const [bodies, setBodies] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/public/stats"), api("/public/complaints"), api("/waterbodies")])
      .then(([a, b, c]) => { setS(a); setList(b.complaints); setBodies(c.water_bodies); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!s) return <div className="center">Loading dashboard...</div>;

  const markers = [
    ...bodies.map((b) => ({ lat: b.lat, lng: b.lng, color: "#0891b2", radius: 12, label: `<b>${b.name}</b><br>${b.authority}` })),
    ...list.map((c) => ({ lat: c.lat, lng: c.lng, color: STATUS_COLOR[c.status], radius: 6,
      label: `#${c.id} - ${STATUS_LABEL[c.status]}<br><a href="/complaints/${c.id}">Open</a>` })),
  ];
  const st = s.by_status;

  return (
    <>
      <h1>Public transparency dashboard</h1>
      <p className="muted">Every complaint is tracked from submission to resolution. Cyan = water bodies, other colours = complaints.</p>
      <div className="stats">
        <Stat label="Complaints" value={s.total} />
        <Stat label="Awaiting inspection" value={st.ASSIGNED || 0} />
        <Stat label="Cleaning planned" value={st.ACTION_PLANNED || 0} />
        <Stat label="Completed" value={st.COMPLETED || 0} />
        <Stat label="Escalated" value={s.escalated} />
        <Stat label="Fake rejected by AI" value={s.rejected_fake} />
        <Stat label="Avg days to resolve" value={s.avg_resolution_days} />
        <Stat label="Done on time" value={s.on_time_pct != null ? s.on_time_pct + "%" : null} />
        <Stat label="Citizen rating" value={s.avg_citizen_rating} />
        <Stat label="Authority rating" value={s.avg_authority_rating} />
      </div>
      <MapView markers={markers} height={360} />

      <h2>Authority performance</h2>
      <div className="scroll"><table>
        <thead><tr><th>Authority</th><th>Level</th><th>Open</th><th>Completed</th><th>Citizen rating</th></tr></thead>
        <tbody>{s.authorities.map((a) => (
          <tr key={a.authority}><td>{a.authority}</td><td>{a.level}</td><td>{a.open}</td><td>{a.completed}</td><td>{a.citizen_rating ?? "-"}</td></tr>
        ))}</tbody>
      </table></div>

      <h2>Recent complaints</h2>
      <div className="scroll"><table>
        <thead><tr><th>#</th><th>Water body</th><th>Status</th><th>Authority</th><th>Reported</th><th>Escalations</th></tr></thead>
        <tbody>{list.slice(0, 15).map((c) => (
          <tr key={c.id}>
            <td><Link to={`/complaints/${c.id}`}>#{c.id}</Link></td><td>{c.water_body || "-"}</td>
            <td><span className="badge" style={{ background: STATUS_COLOR[c.status] }}>{STATUS_LABEL[c.status]}</span></td>
            <td>{c.authority}</td><td>{fmtDate(c.created_at)}</td><td>{c.escalation_count || 0}</td>
          </tr>
        ))}{!list.length && <tr><td colSpan="6">No complaints yet.</td></tr>}</tbody>
      </table></div>
    </>
  );
}
