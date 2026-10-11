"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSupabase } from "@/lib/supabase";

export default function AuthCallback() {
  const router = useRouter();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    const sb = getSupabase();
    (code ? sb.auth.exchangeCodeForSession(code) : sb.auth.getSession())
      .then(({ error }) => (error ? setFailed(true) : router.replace("/")))
      .catch(() => setFailed(true));
  }, [router]);

  return (
    <section className="container-page flex min-h-[60vh] items-center justify-center">
      {failed ? (
        <div className="text-center" role="alert">
          <h1 className="font-display text-xl font-bold text-ink">That sign-in link didn&apos;t work</h1>
          <p className="mt-2 text-sm text-ink-soft">It may have expired or been used already.</p>
          <a href="/login" className="btn-primary mt-6">
            Request a new link
          </a>
        </div>
      ) : (
        <p className="flex items-center gap-3 text-sm text-ink-soft" role="status">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" aria-hidden />
          Signing you in…
        </p>
      )}
    </section>
  );
}
