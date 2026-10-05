import "../css/LeftPanel.css";
import { displayAnatomyName } from "../utils/anatomyName";

export default function LeftPanel({ selectedRegion, painData = {}, setSelectedRegion, setPainData }) {

    const savedRegions = Object.entries(painData);
    const numRegions = savedRegions.length;
    
    let avgSeverity = "—";
    if (numRegions > 0) {
        const total = savedRegions.reduce((sum, [_, data]) => sum + data.severity, 0);
        avgSeverity = (total / numRegions).toFixed(1);
    }

    return (

        <aside className="glass-panel panel-left">

            <div className="panel-title">Marked areas <span>{numRegions}</span></div>

            <div className="panel-summary">
                <div className="summary-stat">
                    <div className="stat-value">{numRegions}</div>
                    <div className="stat-label">Spots</div>
                </div>

                <div className="summary-stat">
                    <div className="stat-value">{avgSeverity}</div>
                    <div className="stat-label">Avg Severity</div>
                </div>
            </div>

            <div className="region-list">

                {numRegions > 0 ? (
                    savedRegions.map(([spotId, data]) => (
                        <div key={spotId} className={`region-item ${selectedRegion === spotId ? "is-selected" : ""}`}>
                            
                            <div className="region-item__text">
                                <div className="region-item__name">{displayAnatomyName(data.regionName) || "Unknown region"}</div>
                                <div className="region-item__meta">
                                    {data.severity}/10 severity · {data.painType || "Pain type not set"}
                                </div>
                            </div>

                            <div className="region-item__actions">
                                <button 
                                    onClick={() => setSelectedRegion(spotId)}
                                    className="region-item__edit"
                                    title={`Edit ${data.regionName}`}
                                >
                                    Edit
                                </button>
                                <button
                                    onClick={() => {
                                        const newData = { ...painData };
                                        delete newData[spotId];
                                        setPainData(newData);
                                        if (selectedRegion === spotId) {
                                            setSelectedRegion(null);
                                        }
                                    }}
                                    className="region-item__delete"
                                    title={`Delete ${data.regionName}`}
                                >
                                    Delete
                                </button>
                            </div>

                        </div>
                    ))
                ) : (
                    <div className="empty-state">
                        <div>Select a muscle on the model to add a pain location.</div>
                    </div>
                )}

            </div>

        </aside>

    );
}
