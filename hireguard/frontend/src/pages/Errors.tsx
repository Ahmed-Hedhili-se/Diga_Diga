import { Link } from "react-router-dom";

export function Forbidden({ home }: { home: string }) {
  return (
    <section className="error-page" aria-labelledby="err-title">
      <div className="error-code">403</div>
      <h1 id="err-title">You don't have access to this page</h1>
      <p className="muted">
        Your role doesn't include this area. If you need it for your work, ask your administrator.
      </p>
      <Link className="btn primary" to={home}>
        Back to my home page
      </Link>
    </section>
  );
}

export function NotFound({ home }: { home: string }) {
  return (
    <section className="error-page" aria-labelledby="err-title">
      <div className="error-code">404</div>
      <h1 id="err-title">Page not found</h1>
      <p className="muted">The address may be mistyped, or the page has moved.</p>
      <Link className="btn primary" to={home}>
        Back to my home page
      </Link>
    </section>
  );
}
