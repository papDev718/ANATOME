import { useEffect, useState } from "react";
import "../css/RightPanel.css";
import { displayAnatomyName } from "../utils/anatomyName";

const PAIN_TYPES = [
  "Sharp",
  "Dull",
  "Aching",
  "Burning",
  "Throbbing",
  "Shooting",
  "Cramping",
];

export default function RightPanel({
  selectedRegion,
  setSelectedRegion,
  painData = {},
  setPainData,
  onPainSaved,
  onCancel,
}) {
  const handleCancel = () => {
    if (onCancel) onCancel(selectedRegion);
    else setSelectedRegion(null);
  };

  const [severity, setSeverity] = useState(5);
  const [painType, setPainType] = useState("");
  const [notes, setNotes] = useState("");
  const [startDate, setStartDate] = useState("");
  const [frequency, setFrequency] = useState("");

  // selectedRegion contains the generated spot ID
  const selectedSpot = selectedRegion ? painData[selectedRegion] : null;

  // Load selected spot data into the form
  useEffect(() => {
    if (!selectedRegion) {
      setSeverity(5);
      setPainType("");
      setNotes("");
      setStartDate("");
      setFrequency("");
      return;
    }

    const existingData = painData[selectedRegion];

    if (existingData) {
      setSeverity(existingData.severity ?? 5);
      setPainType(existingData.painType ?? "");
      setNotes(existingData.notes ?? "");
      setStartDate(existingData.startDate ?? "");
      setFrequency(existingData.frequency ?? "");
    } else {
      setSeverity(5);
      setPainType("");
      setNotes("");
      setStartDate("");
      setFrequency("");
    }
  }, [selectedRegion, painData]);

  const handleSave = () => {
    if (!selectedRegion) return;

    setPainData((previousPainData) => ({
      ...previousPainData,
      [selectedRegion]: {
        ...previousPainData[selectedRegion],
        severity,
        painType,
        notes,
        startDate,
        frequency,
      },
    }));

    // Notify App: clears selectedRegion AND zooms canvas back to full body
    if (onPainSaved) onPainSaved();
    else setSelectedRegion(null);
  };

  const handleDelete = () => {
    if (!selectedRegion) {
      return;
    }

    setPainData((previousPainData) => {
      const updatedPainData = { ...previousPainData };

      delete updatedPainData[selectedRegion];

      return updatedPainData;
    });

    setSelectedRegion(null);
  };

  const getSeverityColor = (value) => {
    if (value <= 3) {
      return "var(--sev-low)";
    }

    if (value <= 6) {
      return "var(--sev-mid)";
    }

    return "var(--sev-high)";
  };

  return (
    <aside className="glass-panel panel-right">
      {!selectedRegion ? (
        <div className="no-selection">
          <div className="no-sel-title">Select where it hurts</div>

          <div className="no-sel-desc">
            Click a muscle or tendon on the model, or choose one from the structure list. Its pain details will open here.
          </div>
        </div>
      ) : (
        <div className="detail-form">
          <div className="detail-header">
            <div>
              <div className="region-title">
                {displayAnatomyName(selectedSpot?.regionName) || "Unknown region"}
              </div>

              <div className="region-subtitle">Describe the pain at this structure</div>
            </div>
          </div>

          <div className="form-section">
            <label className="form-label form-label--row" htmlFor="pain-severity">
              <span>Pain Severity</span>

              <span style={{ color: getSeverityColor(severity) }}>
                {severity} / 10
              </span>
            </label>

            <input
              id="pain-severity"
              type="range"
              min="1"
              max="10"
              value={severity}
              onChange={(event) => setSeverity(Number(event.target.value))}
              style={{
                width: "100%",
                accentColor: getSeverityColor(severity),
              }}
            />
          </div>

          <div className="form-section">
            <div className="form-label">Pain Type</div>

            <div className="option-pills">
              {PAIN_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  className={`option-pill ${painType === type ? "active" : ""}`}
                  onClick={() => setPainType(type)}
                  aria-pressed={painType === type}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div className="form-section">
            <label className="form-label" htmlFor="pain-frequency">Frequency</label>

            <select
              id="pain-frequency"
              value={frequency}
              onChange={(event) => setFrequency(event.target.value)}
            >
              <option value="">Select frequency...</option>

              <option value="Constant">Constant</option>

              <option value="Intermittent">Intermittent</option>

              <option value="Occasional">Occasional</option>

              <option value="Rare">Rare</option>
            </select>
          </div>

          <div className="form-section">
            <label className="form-label" htmlFor="pain-onset">Onset Date</label>

            <input
              id="pain-onset"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </div>

          <div className="form-section">
            <label className="form-label" htmlFor="pain-notes">Additional Notes</label>

            <textarea
              id="pain-notes"
              className="notes-textarea"
              placeholder="Describe symptoms, when it started, what makes it worse..."
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>

          <div className="detail-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSave}
            >
              Save
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCancel}
              title="Deselect without saving"
            >
              Cancel
            </button>

            <button
              type="button"
              className="btn btn-danger"
              onClick={handleDelete}
              title="Clear this region"
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
