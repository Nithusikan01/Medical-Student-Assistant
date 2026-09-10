import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

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
      <form className="auth-card" onSubmit={submit}>
        <h1>Create an account</h1>
        <p className="tagline">Ask questions about the study library</p>

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
          Name <span className="optional">(optional)</span>
          <input
            type="text"
            value={fullName}
            autoComplete="name"
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            autoComplete="new-password"
            minLength={MIN_PASSWORD_LENGTH}
            required
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="hint">
            At least {MIN_PASSWORD_LENGTH} characters.
          </span>
        </label>

        <label>
          Invite code <span className="optional">(if required)</span>
          <input
            type="text"
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value)}
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>

        <p className="auth-switch">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
