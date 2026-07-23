import { useState } from "react";
import { verifyCredentials } from "../api";
import { buildAuthHeader, setStoredAuthHeader } from "../auth";

export default function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
          <div className="relative">
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="w-full px-4 py-2 pr-10 rounded-lg border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-ink-muted hover:text-ink-primary transition-colors"
            >
              {showPassword ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                  <path d="M17.94 17.94A10.94 10.94 0 0112 20c-7 0-11-8-11-8a21.8 21.8 0 015.06-6.06M9.9 4.24A10.4 10.4 0 0112 4c7 0 11 8 11 8a21.8 21.8 0 01-3.22 4.44M14.12 14.12a3 3 0 11-4.24-4.24" />
                  <path d="M1 1l22 22" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
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
