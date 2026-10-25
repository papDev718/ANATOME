// Patient-facing "while you wait" panel. The tips are chosen on the server
// from a vetted list (back_end/care_guide.py); a language model only
// rewords them, and anything it adds is filtered out before it gets here.

function Section({ title, items, tone }) {
  if (!items?.length) return null;
  return (
    <section className={`care-section ${tone ? `care-section--${tone}` : ""}`}>
      <h4>{title}</h4>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  );
}

export default function CareGuide({ guide, status, error, onRetry }) {
  if (status === "loading") {
    return (
      <aside className="care-guide" aria-busy="true">
        <p className="care-kicker">For you, while you wait</p>
        <p className="care-loading">Putting together tips for your spots...</p>
      </aside>
    );
  }

  if (status === "error") {
    return (
      <aside className="care-guide">
        <p className="care-kicker">For you, while you wait</p>
        <p className="care-error" role="alert">{error}</p>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>Try again</button>
      </aside>
    );
  }

  if (!guide) return null;
  const emergency = guide.mode === "emergency";

  return (
    <aside className={`care-guide ${emergency ? "care-guide--emergency" : ""}`} aria-label="What you can do while you wait">
      <p className="care-kicker">For you, while you wait</p>
      <h3 className="care-headline">{guide.headline}</h3>
      {guide.why?.length > 0 && (
        <p className="care-why">Because you reported: {guide.why.join("; ")}.</p>
      )}

      <Section title={emergency ? "Right now" : "Things that can help"} items={guide.do_now} />
      <Section title="Try to avoid" items={guide.avoid} />
      <Section title="Go to the emergency department or call 911 if" items={guide.go_now_if} tone="warn" />
      <Section title="Keep track of" items={guide.track} />
      <Section title="Questions to ask your doctor" items={guide.ask_doctor} />

      <p className="care-footnote">
        General tips, not a diagnosis or treatment plan. Picked from {guide.sources?.length ? guide.sources.join(", ") : "public health guidance"}
        {guide.source === "llm" ? `, then reworded for you by an AI model (${guide.model}) and checked for anything added.` : "."}
      </p>
    </aside>
  );
}
