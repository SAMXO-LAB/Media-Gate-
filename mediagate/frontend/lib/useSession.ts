"use client";

import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { getSupabase, supabaseConfigured } from "./supabase";

export interface SessionState {
  session: Session | null;
  loading: boolean;
  isAdmin: boolean;
}

export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({ session: null, loading: true, isAdmin: false });

  useEffect(() => {
    if (!supabaseConfigured()) {
      setState({ session: null, loading: false, isAdmin: false });
      return;
    }
    const sb = getSupabase();
    let active = true;

    async function load(session: Session | null) {
      let isAdmin = false;
      if (session) {
        // RLS lets a user read only their own profile row. This only toggles UI;
        // the API enforces admin access on every request.
        const { data } = await sb.from("profiles").select("role").eq("id", session.user.id).maybeSingle();
        isAdmin = data?.role === "admin";
      }
      if (active) setState({ session, loading: false, isAdmin });
    }

    sb.auth.getSession().then(({ data }) => load(data.session));
    const { data: sub } = sb.auth.onAuthStateChange((_e, session) => load(session));
    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  return state;
}
