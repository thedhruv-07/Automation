import { useState } from "react";
import { verifyCredentials } from "../api";
import { buildAuthHeader, setStoredAuthHeader } from "../auth";

export default function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setChecking(true);
    setError(null);
    const header = buildAuthHeader(username, password);
    const ok = await verifyCredentials(header);
    setChecking(false);
    if (!ok) {
      setError("Invalid username or password.");
      return;
    }
    setStoredAuthHeader(header);
    onSuccess();
  }

  return (
    <div className="min-h-screen bg-surface-page flex items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="bg-surface rounded-2xl shadow-xl border border-line w-full max-w-sm p-6 space-y-4"
      >
        <h1 className="text-lg font-bold text-ink-primary">Certification Manager</h1>
        <p className="text-sm text-ink-secondary">Sign in to continue.</p>
        {error && (
          <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="login-username" className="block text-sm font-medium text-ink-secondary mb-1">
            Username
          </label>
          <input
            id="login-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className="w-full px-4 py-2 rounded-lg border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
          />
        </div>
        <div>
          <label htmlFor="login-password" className="block text-sm font-medium text-ink-secondary mb-1">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full px-4 py-2 rounded-lg border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
          />
        </div>
        <button
          type="submit"
          disabled={checking}
          className="w-full px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          {checking ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
