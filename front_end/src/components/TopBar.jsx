import "../css/TopBar.css";

export default function TopBar({ setShowReport, onClearAll, onGoHome }) {
    const handleClearAll = () => {
        if (window.confirm("Are you sure you want to clear all logged pain data?")) {
            onClearAll();
        }
    };

    return (
        <header className="top-bar">
            <button
                type="button"
                className="logo"
                onClick={onGoHome}
                aria-label="Go to home page"
            >
                <span className="logo-text">Anatome</span>
                <span className="logo-tag">Pain map</span>
            </button>

            <div className="top-bar-actions">
                <button className="btn btn-secondary" onClick={handleClearAll}>
                    Clear all
                </button>

                <button className="btn btn-primary" onClick={() => setShowReport(true)}>
                    Generate report
                </button>
            </div>
        </header>
    );
}
