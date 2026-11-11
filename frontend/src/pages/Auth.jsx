import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../App.jsx";

function AuthForm({ mode }) {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      const r = await api(`/auth/${mode}`, { method: "POST", body: f });
      signIn(r.token, r.user);
      nav(r.user.role === "citizen" ? "/report" : "/complaints");
    } catch (er) { setError(er.message); } finally { setBusy(false); }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>{mode === "login" ? "Login" : "Create citizen account"}</h2>
      {mode === "register" && <label>Name<input value={f.name} onChange={set("name")} required /></label>}
      <label>Email<input type="email" value={f.email} onChange={set("email")} required /></label>
      <label>Password<input type="password" value={f.password} onChange={set("password")} required minLength={6} /></label>
      {error && <p className="error">{error}</p>}
      <button disabled={busy}>{busy ? "Please wait..." : mode === "login" ? "Login" : "Register"}</button>
      <p className="muted">
        {mode === "login" ? <>New citizen? <Link to="/register">Register</Link></> : <>Have an account? <Link to="/login">Login</Link></>}
      </p>
      {mode === "login" && (
        <details className="muted"><summary>Demo accounts</summary>
          citizen@demo.com / citizen123<br />vita@demo.com / vita123 (local authority)<br />
          district@demo.com / district123<br />state@demo.com / state123<br />admin@demo.com / admin123
        </details>
      )}
    </form>
  );
}
export const Login = () => <AuthForm mode="login" />;
export const Register = () => <AuthForm mode="register" />;
