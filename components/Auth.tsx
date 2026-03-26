"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";
import "./auth.css";

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState<string | null>(null);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (mode === "signup") {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
        });
        if (signUpError) throw signUpError;
        alert("Check your email for the confirmation link!");
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) throw signInError;
      }
    } catch (err: any) {
      setError(err.message || "An authentication error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <h1 className="auth-title">ET GENAI</h1>
          <p className="auth-subtitle">Financial Intelligence Redefined</p>
        </div>

        <div className="auth-tabs">
          <button
            className={`auth-tab ${mode === "signin" ? "active" : ""}`}
            onClick={() => setMode("signin")}
          >
            Sign In
          </button>
          <button
            className={`auth-tab ${mode === "signup" ? "active" : ""}`}
            onClick={() => setMode("signup")}
          >
            Sign Up
          </button>
        </div>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleAuth}>
          <div className="auth-form-group">
            <label className="auth-label">Email Address</label>
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
            />
          </div>

          <div className="auth-form-group">
            <label className="auth-label">Password</label>
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button type="submit" className="auth-submit-btn" disabled={loading}>
            {loading ? "Authenticating..." : mode === "signin" ? "Sign In" : "Sign Up"}
          </button>
        </form>
      </div>
    </div>
  );
}
