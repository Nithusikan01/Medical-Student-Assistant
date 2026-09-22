import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { AuthPanel } from "../components/AuthPanel";
import { ArrowRight } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";

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
      <AuthPanel
        quote="“Dream is not that which you see while sleeping, it is something that does not let you sleep.”"
        author="A. P. J. Abdul Kalam"
        credit="Aerospace scientist, 11th President of India"
      />

      <div className="auth-form-side">
        <div className="auth-bar">
          <ThemeToggle />
        </div>

        <div className="auth-body">
          <form className="auth-card" onSubmit={submit}>
            <h1>Sign in</h1>
            <p className="tagline">Ask questions against your class library.</p>

            <div className="field">
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                autoComplete="email"
                required
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                value={password}
                autoComplete="current-password"
                required
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            {error && <p className="form-error">{error}</p>}

            <button type="submit" className="btn btn-block" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
              {!busy && <ArrowRight />}
            </button>

            <div className="rule">New here?</div>

            <p className="auth-switch">
              <Link to="/register">Create an account</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
