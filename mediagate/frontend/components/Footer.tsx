import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-line bg-canvas">
      <div className="container-page flex flex-col gap-6 py-10 text-sm text-ink-mute md:flex-row md:items-center md:justify-between">
        <p className="max-w-xl leading-relaxed">
          MediaGate uses official platform APIs only. It never bypasses sign-in, DRM or platform restrictions, and
          processed files are deleted automatically after one hour.
        </p>
        <nav className="flex gap-5" aria-label="Footer">
          <Link href="/#platforms" className="hover:text-ink">
            Platform rules
          </Link>
          <Link href="/connections" className="hover:text-ink">
            Connections
          </Link>
        </nav>
      </div>
    </footer>
  );
}
