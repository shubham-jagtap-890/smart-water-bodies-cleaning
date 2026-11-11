import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, STATUS_COLOR, STATUS_LABEL, fmtDate, fmt } from "../api.js";
import { useAuth } from "../App.jsx";

export default function Complaints() {
  const { user } = useAuth();
  const [rows, setRows] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api("/complaints" + (status ? `?status=${status}` : "")).then((r) => setRows(r.complaints)).catch((e) => setError(e.message));
  }, [status]);

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <div className="center">Loading...</div>;
  const isAuth = user.role !== "citizen";

  return (
    <>
      <h1>{isAuth ? "Complaints for your jurisdiction" : "My complaints"}</h1>
      <label className="inline">Filter:
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <div className="scroll"><table>
        <thead><tr><th>#</th><th>Water body</th><th>Status</th>{isAuth && <th>Current authority</th>}<th>Reported</th><th>Deadline</th><th></th></tr></thead>
        <tbody>{rows.map((c) => (
          <tr key={c.id} className={c.actionable ? "hl" : ""}>
            <td><Link to={`/complaints/${c.id}`}>#{c.id}</Link></td><td>{c.water_body || "-"}</td>
            <td><span className="badge" style={{ background: STATUS_COLOR[c.status] }}>{STATUS_LABEL[c.status]}</span>
              {c.escalation_count > 0 && <span className="badge warn">escalated x{c.escalation_count}</span>}
              {c.top_level_overdue && <span className="badge bad">overdue</span>}</td>
            {isAuth && <td>{c.authority}</td>}
            <td>{fmtDate(c.created_at)}</td><td>{fmt(c.deadline)}</td>
            <td>{c.actionable ? <Link to={`/complaints/${c.id}`}>Take action</Link> : ""}</td>
          </tr>
        ))}{!rows.length && <tr><td colSpan="7">Nothing here yet.</td></tr>}</tbody>
      </table></div>
    </>
  );
}
