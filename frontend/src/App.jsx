import { createContext, useContext, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken } from "./api.js";
import Dashboard from "./pages/Dashboard.jsx";
import { Login, Register } from "./pages/Auth.jsx";
import Report from "./pages/Report.jsx";
import Complaints from "./pages/Complaints.jsx";
import ComplaintDetail from "./pages/ComplaintDetail.jsx";
import Predictions from "./pages/Predictions.jsx";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    if (!getToken()) return setReady(true);
    api("/auth/me").then((r) => setUser(r.user)).catch(() => localStorage.removeItem("token")).finally(() => setReady(true));
  }, []);

  const signIn = (token, u) => { localStorage.setItem("token", token); setUser(u); };
  const signOut = () => { localStorage.removeItem("token"); setUser(null); nav("/"); };
  if (!ready) return <div className="center">Loading...</div>;

  const need = (el, roles) => (!user ? <Navigate to="/login" /> : roles && !roles.includes(user.role) ? <Navigate to="/" /> : el);

  return (
    <AuthCtx.Provider value={{ user, signIn, signOut }}>
      <header className="nav">
        <Link to="/" className="brand">Water Bodies Watch</Link>
        <nav>
          <NavLink to="/" end>Public dashboard</NavLink>
          {user?.role === "citizen" && <NavLink to="/report">Report pollution</NavLink>}
          {user && <NavLink to="/complaints">{user.role === "citizen" ? "My complaints" : "Complaints"}</NavLink>}
          {(user?.role === "authority" || user?.role === "admin") && <NavLink to="/predictions">AI predictions</NavLink>}
          {user ? (
            <button className="link" onClick={signOut}>Logout ({user.name})</button>
          ) : (<><NavLink to="/login">Login</NavLink><NavLink to="/register">Register</NavLink></>)}
        </nav>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/report" element={need(<Report />, ["citizen"])} />
          <Route path="/complaints" element={need(<Complaints />)} />
          <Route path="/complaints/:id" element={<ComplaintDetail />} />
          <Route path="/predictions" element={need(<Predictions />, ["authority", "admin"])} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <footer className="foot">AI-Based Smart Water Bodies Cleaning Prediction, Action Tracking and Escalation System</footer>
    </AuthCtx.Provider>
  );
}
