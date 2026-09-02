import type { ReactNode } from "react";

interface Props {
  n: number;
  title: string;
  hint?: ReactNode;
  children: ReactNode;
}

/** A numbered form step: badge + heading (+ optional hint), then its controls.
 *  Keeps the one-page form reading as an obvious 1 → 2 → 3 progression. */
export function Step({ n, title, hint, children }: Props) {
  const id = `step-${n}`;
  return (
    <section className="section" aria-labelledby={id}>
      <div className="step-head">
        <span className="step-num" aria-hidden="true">
          {n}
        </span>
        <h2 id={id} className="step-title">
          {title}
        </h2>
      </div>
      {hint && <p className="step-hint">{hint}</p>}
      {children}
    </section>
  );
}
