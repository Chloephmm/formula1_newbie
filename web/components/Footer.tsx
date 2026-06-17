export default function Footer() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-6">
          <span>Terms &amp; Support</span>
          <span>Privacy Policy</span>
        </div>
        <p>
          Live data from{" "}
          <a
            href="https://jolpi.ca"
            target="_blank"
            rel="noopener noreferrer"
            className="text-fg hover:text-accent"
          >
            Jolpica
          </a>
          . Not affiliated with Formula 1.
        </p>
      </div>
    </footer>
  );
}
