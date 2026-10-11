"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getSupabase } from "@/lib/supabase";
import { useSession } from "@/lib/useSession";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#1F4FF0" />
        <path d="M10 9v14M22 9v14" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M16 11v8m0 0-3-3m3 3 3-3" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="font-display text-[1.05rem] font-bold tracking-tight text-ink">MediaGate</span>
    </span>
  );
}

export function Navbar() {
  const pathname = usePathname();
  const { session, isAdmin, loading } = useSession();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => setOpen(false), [pathname]);

  const links = [
    { href: "/", label: "Analyze" },
    { href: "/#platforms", label: "What's allowed" },
    ...(session ? [{ href: "/connections", label: "Connections" }] : []),
    ...(isAdmin ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  async function signOut() {
    await getSupabase().auth.signOut();
    window.location.href = "/";
  }

  return (
    <header
      className={`sticky top-0 z-40 transition-[background,box-shadow,border-color] duration-300 ${
        scrolled ? "border-b border-line bg-white/85 backdrop-blur-md" : "border-b border-transparent bg-white/0"
      }`}
    >
      <nav className="container-page flex h-16 items-center justify-between" aria-label="Main">
        <Link href="/" className="rounded-lg" aria-label="MediaGate home">
          <Logo />
        </Link>

        <ul className="hidden items-center gap-1 md:flex">
          {links.map((l) => {
            const active = l.href === pathname;
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                    active ? "bg-brand-50 text-brand-700" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="hidden items-center gap-2 md:flex">
          {loading ? (
            <span className="h-9 w-24 animate-pulse rounded-full bg-brand-50" />
          ) : session ? (
            <>
              <span className="max-w-[12rem] truncate text-sm text-ink-mute" title={session.user.email ?? ""}>
                {session.user.email}
              </span>
              <button onClick={signOut} className="btn-secondary py-2">
                Sign out
              </button>
            </>
          ) : (
            <Link href="/login" className="btn-primary py-2">
              Sign in
            </Link>
          )}
        </div>

        <button
          className="rounded-full p-2 text-ink md:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((o) => !o)}
        >
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </nav>

      {open && (
        <div id="mobile-nav" className="border-t border-line bg-white md:hidden">
          <ul className="container-page flex flex-col py-3">
            {links.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="block rounded-xl px-3 py-3 text-base font-medium text-ink hover:bg-brand-50">
                  {l.label}
                </Link>
              </li>
            ))}
            <li className="mt-2 border-t border-line pt-3">
              {session ? (
                <button onClick={signOut} className="btn-secondary w-full">
                  Sign out
                </button>
              ) : (
                <Link href="/login" className="btn-primary w-full">
                  Sign in
                </Link>
              )}
            </li>
          </ul>
        </div>
      )}
    </header>
  );
}
