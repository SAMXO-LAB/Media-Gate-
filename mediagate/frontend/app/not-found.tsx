import Link from "next/link";

export default function NotFound() {
  return (
    <section className="container-page py-28 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 font-display text-3xl font-bold text-ink">This page doesn&apos;t exist</h1>
      <Link href="/" className="btn-primary mt-8">Back to MediaGate</Link>
    </section>
  );
}
