"use client";

import { useState } from "react";
import { Logo } from "@/components/Navbar";
import { getSupabase, supabaseConfigured } from "@/lib/supabase";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const configured = supabaseConfigured();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setError(null);
    const { error } = await getSupabase().auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) {
      setError(error.status === 429 ? "Too many attempts. Please wait a minute." : "We couldn't send the link. Check the address and try again.");
      setState("error");
    } else {
      setState("sent");
    }
  }

  return (
    <section className="container-page flex min-h-[70vh] items-center justify-center py-16">
      <div className="card w-full max-w-md p-8">
        <Logo />
        {state === "sent" ? (
          <div className="mt-8" role="status">
            <h1 className="font-display text-2xl font-bold text-ink">Check your inbox</h1>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">
              We sent a sign-in link to <strong className="text-ink">{email}</strong>. It expires shortly, so use it soon.
            </p>
            <button className="btn-ghost mt-6 px-0" onClick={() => setState("idle")}>
              Use a different email
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
            <div>
              <h1 className="font-display text-2xl font-bold text-ink">Sign in</h1>
              <p className="mt-1 text-sm text-ink-soft">No password needed — we&apos;ll email you a secure link.</p>
            </div>
            {!configured && (
              <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
                Sign-in isn&apos;t configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
              </p>
            )}
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input h-11"
                placeholder="you@example.com"
                aria-invalid={state === "error"}
                aria-describedby={error ? "email-error" : undefined}
              />
              {error && (
                <p id="email-error" className="mt-1.5 text-sm text-rose-700">
                  {error}
                </p>
              )}
            </div>
            <button type="submit" className="btn-primary h-11 w-full" disabled={!configured || state === "sending" || !/.+@.+\..+/.test(email)}>
              {state === "sending" ? "Sending link…" : "Email me a sign-in link"}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}
