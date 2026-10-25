import "../css/TopBar.css";

const STEPS = ["Describe", "Mark where it hurts", "Get your report"];

export default function TopBar({ onOpenReport, onGoHome, savedCount = 0 }) {
    return (
        <header className="top-bar">
            <button
                type="button"
                className="logo"
                onClick={onGoHome}
                aria-label="Go to home page"
            >
                <span className="logo-text">Anatome</span>
            </button>

            <ol className="top-steps" aria-label="Progress">
                {STEPS.map((step, index) => {
                    const state = index === 0 ? "done" : index === 1 ? "current" : "todo";
                    return (
                        <li key={step} className={`top-step is-${state}`} aria-current={state === "current" ? "step" : undefined}>
                            <span className="top-step__dot" aria-hidden="true">{state === "done" ? "✓" : index + 1}</span>
                            <span className="top-step__label">{step}</span>
                        </li>
                    );
                })}
            </ol>

            <div className="top-bar-actions">
                <button className="btn btn-primary" onClick={onOpenReport} disabled={savedCount === 0} title={savedCount === 0 ? "Save at least one spot first" : undefined}>
                    Make report{savedCount > 0 ? ` (${savedCount})` : ""}
                </button>
            </div>
        </header>
    );
}
