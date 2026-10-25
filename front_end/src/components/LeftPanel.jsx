import "../css/LeftPanel.css";
import { displayAnatomyName } from "../utils/anatomyName";

export default function LeftPanel({ activeSpotId, painData = {}, onEdit, onDelete }) {

    const savedRegions = Object.entries(painData);
    const numRegions = savedRegions.length;

    let maxSeverity = "—";
    if (numRegions > 0) {
        maxSeverity = Math.max(...savedRegions.map(([, data]) => data.severity || 0));
    }

    return (

        <aside className="glass-panel panel-left">

            <div className="panel-title">Saved spots <span>{numRegions}</span></div>

            <div className="panel-summary">
                <div className="summary-stat">
                    <div className="stat-value">{numRegions}</div>
                    <div className="stat-label">Spots</div>
                </div>

                <div className="summary-stat">
                    <div className="stat-value">{maxSeverity}</div>
                    <div className="stat-label">Worst pain</div>
                </div>
            </div>

            <div className="region-list">

                {numRegions > 0 ? (
                    savedRegions.map(([spotId, data]) => {
                        const label = data.mode === "area" ? data.areaLabel : displayAnatomyName(data.regionName);
                        return (
                            <div key={spotId} className={`region-item ${activeSpotId === spotId ? "is-selected" : ""}`}>

                                <div className="region-item__text">
                                    <div className="region-item__name">{label || "Unknown region"}</div>
                                    <div className="region-item__meta">
                                        {data.severity}/10 · {data.painType} · {data.onset}
                                    </div>
                                </div>

                                <div className="region-item__actions">
                                    <button
                                        onClick={() => onEdit(spotId)}
                                        className="region-item__edit"
                                        aria-label={`Edit ${label}`}
                                    >
                                        Edit
                                    </button>
                                    <button
                                        onClick={() => onDelete(spotId)}
                                        className="region-item__delete"
                                        aria-label={`Delete ${label}`}
                                    >
                                        Delete
                                    </button>
                                </div>

                            </div>
                        );
                    })
                ) : (
                    <div className="empty-state">
                        <div>Nothing saved yet. Tap where it hurts, answer the questions, then press Save.</div>
                    </div>
                )}

            </div>

        </aside>

    );
}
