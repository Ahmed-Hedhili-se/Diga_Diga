// "?" in the page header. The plain-language words for this page, and on the Overview the "Examples to try", live behind it
// instead of under every page. A popover, not a modal: Esc closes it, clicking elsewhere closes it, focus returns to the button.
import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { hintsFor } from "./PageHints";
import TryThese from "./TryThese";

export default function HelpButton() {
  const { pathname } = useLocation();
  const hints = hintsFor(pathname);
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  if (!hints) return null;
  return (
    <span className="help-wrap">
      <button ref={button} type="button" className="help-btn" aria-label="Help for this page" aria-haspopup="dialog"
        aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        ?
      </button>
      {open && (
        <div ref={panel} id={id} className="help-pop" role="dialog" aria-label="Help for this page" tabIndex={-1}>
          <h2>Words used on this page</h2>
          <dl>
            {hints.map(([term, meaning]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{meaning}</dd>
              </div>
            ))}
          </dl>
          {pathname === "/overview" && <TryThese onOpen={() => setOpen(false)} />}
        </div>
      )}
    </span>
  );
}
