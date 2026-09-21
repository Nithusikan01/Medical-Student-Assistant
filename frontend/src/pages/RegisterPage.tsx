import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ArrowRight, BookMark } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";

const MIN_PASSWORD_LENGTH = 12;

export function RegisterPage() {
  const { user, ready, register } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
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
      await register({
        email: email.trim(),
        password,
        fullName: fullName.trim(),
        inviteCode: inviteCode.trim(),
      });
      navigate("/", { replace: true });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not create account.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-bar">
        <span className="wordmark">
          <BookMark size={22} />
          Anamnesis
        </span>
        <ThemeToggle />
      </div>

      <div className="auth-body">
        <form className="auth-card" onSubmit={submit}>
          <h1>Create an account</h1>
          <p className="tagline">Your chats stay private to you.</p>

          <div className="field">
            <label htmlFor="register-email">Email</label>
            <input
              id="register-email"
              type="email"
              value={email}
              autoComplete="email"
              required
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="register-name">
              Name <span className="field-optional">optional</span>
            </label>
            <input
              id="register-name"
              type="text"
              value={fullName}
              autoComplete="name"
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="register-password">Password</label>
            <input
              id="register-password"
              type="password"
              value={password}
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              required
              onChange={(event) => setPassword(event.target.value)}
            />
            <span className="field-hint">
              At least {MIN_PASSWORD_LENGTH} characters.
            </span>
          </div>

          <div className="field">
            <label htmlFor="register-invite">
              Invite code <span className="field-optional">if required</span>
            </label>
            <input
              id="register-invite"
              type="text"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
            />
          </div>

          {error && <p className="form-error">{error}</p>}

          <button type="submit" className="btn btn-block" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
            {!busy && <ArrowRight />}
          </button>

          <p className="auth-switch">
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
