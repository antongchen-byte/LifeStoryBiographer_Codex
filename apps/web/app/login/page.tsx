"use client";
import { useState, type FormEvent } from "react";
import { signIn } from "next-auth/react";
import { BookOpen, ArrowRight } from "lucide-react";
import { Button } from "../../components/ui/button";
export default function Login() {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [showPassword, setShowPassword] = useState(false),
    [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email")),
      password = String(data.get("password"));
    try {
      if (register) {
        const response = await fetch("/api/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, name: data.get("name") }),
        });
        if (!response.ok) {
          const payload = await response.json();
          throw new Error(
            typeof payload.detail === "string"
              ? payload.detail
              : "Please check your account details.",
          );
        }
      }
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });
      if (result?.error)
        throw new Error(
          "Unable to sign in. Check your email and password, then try again.",
        );
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please try again.");
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <BookOpen />
          </span>
          LifeStory
        </div>
        <div>
          <span className="eyebrow">A LIFE, WELL TOLD</span>
          <h1>
            Some stories
            <br />
            deserve to
            <br />
            <em>last forever.</em>
          </h1>
          <p>
            A place for the memories, voices, and photographs that make a life.
          </p>
        </div>
        <span className="tiny-label">
          YOUR MEMORIES. YOUR VOICE. YOUR STORY.
        </span>
      </div>
      <div className="login-form-wrap">
        <form onSubmit={submit} className="login-form">
          <span className="eyebrow">WELCOME TO YOUR STUDIO</span>
          <h2>{register ? "Begin your story" : "Welcome back"}</h2>
          <p className="muted">
            {register
              ? "Create your account to start preserving a life."
              : "Sign in to continue your biographies."}
          </p>
          {register && (
            <label>
              Your name
              <input name="name" required maxLength={200} autoComplete="name" />
            </label>
          )}
          <label>
            Email address
            <input type="email" name="email" required autoComplete="email" />
          </label>
          <label>
            Password
            <input
              type={showPassword ? "text" : "password"}
              id="login-password"
              name="password"
              required
              minLength={10}
              maxLength={200}
              autoComplete={register ? "new-password" : "current-password"}
            />
          </label>
          <label className="password-visibility">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
              aria-controls="login-password"
            />
            Show password
          </label>
          {register && (
            <small className="muted">Use at least 10 characters.</small>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <Button disabled={busy} className="full-width">
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            <ArrowRight size={16} />
          </Button>
          <p className="login-toggle">
            {register ? "Already have an account?" : "New to LifeStory?"}{" "}
            <button
              type="button"
              onClick={() => {
                setRegister(!register);
                setShowPassword(false);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create an account"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
