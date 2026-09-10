import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

export function LoginPage() {
  const { user, ready, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (ready && user) {
    return <Navigate to="/" replace />;
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);

    try {
      await login(email.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? "/", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>Medical Student Assistant</h1>
        <p className="tagline">Sign in to continue</p>

        <label>
          Email
          <input
            type="email"
            value={email}
            autoComplete="email"
            required
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            autoComplete="current-password"
            required
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="auth-switch">
          No account? <Link to="/register">Create one</Link>
        </p>
      </form>
    </div>
  );
}
