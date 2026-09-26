import { useState } from "react";
import "../css/ReportModal.css";
import ReportButton from "./ReportButton";

export default function ReportModal({
  setShowReport,
  painData,
  questionnaireAnswers,
}) {
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [reportDate, setReportDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  const [isSaving, setIsSaving] = useState(false);
  const [savedPatientId, setSavedPatientId] = useState(null);
  const [reportError, setReportError] = useState("");

  const regions = Object.entries(painData || {});

  function validateReport() {
    if (!patientName.trim()) {
      throw new Error("Please enter the patient's name.");
    }

    if (patientAge === "" || Number.isNaN(Number(patientAge))) {
      throw new Error("Please enter a valid patient age.");
    }

    if (!reportDate) {
      throw new Error("Please choose a report date.");
    }

    if (!questionnaireAnswers) {
      throw new Error(
        "Please complete the questionnaire before generating the report.",
      );
    }

    if (regions.length === 0) {
      throw new Error("Please select at least one pain region.");
    }
  }

  async function saveReport() {
    setReportError("");

    try {
      validateReport();
      setIsSaving(true);

      const response = await fetch("/api/reports", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          patient_name: patientName.trim(),
          patient_age: Number(patientAge),
          report_date: reportDate,
          questionnaire: questionnaireAnswers,
          pain_regions: painData,
        }),
      });

      let result;

      try {
        result = await response.json();
      } catch {
        throw new Error(
          `The server returned an invalid response. Status: ${response.status}`,
        );
      }

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail) ||
                "The report could not be generated.",
        );
      }

      if (!result.ai_report) {
        throw new Error("The report was saved, but no AI report was returned.");
      }

      setSavedPatientId(result.patient_id);

      return result;
    } catch (error) {
      setReportError(error.message || "The report could not be generated.");

      throw error;
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSaveOnly() {
    try {
      const result = await saveReport();

      alert(`Report saved successfully.\nPatient ID: ${result.patient_id}`);
    } catch {
      // The error is already displayed in reportError.
    }
  }

  return (
    <div className="report-overlay">
      <div className="report-modal">
        <div
          className="report-modal-header"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h2>📋 Clinical Pain Report</h2>

          <button
            type="button"
            className="report-close-btn"
            onClick={() => setShowReport(false)}
            disabled={isSaving}
          >
            ✕
          </button>
        </div>

        <div className="report-modal-body">
          <div className="patient-info-section">
            <div className="info-group">
              <label>Patient Name:</label>

              <input
                type="text"
                value={patientName}
                onChange={(event) => setPatientName(event.target.value)}
                placeholder="Full Name"
                disabled={isSaving}
              />
            </div>

            <div className="info-group">
              <label>Age:</label>

              <input
                type="number"
                min="0"
                max="130"
                value={patientAge}
                onChange={(event) => setPatientAge(event.target.value)}
                placeholder="Age"
                disabled={isSaving}
              />
            </div>

            <div className="info-group">
              <label>Date:</label>

              <input
                type="date"
                value={reportDate}
                onChange={(event) => setReportDate(event.target.value)}
                disabled={isSaving}
              />
            </div>
          </div>

          {isSaving && (
            <div className="report-status-message">
              Generating the AI report and saving it...
            </div>
          )}

          {reportError && (
            <div className="report-error-message">
              <strong>Report error:</strong> {reportError}
            </div>
          )}

          {savedPatientId && (
            <div className="saved-report-message">
              <strong>Saved successfully.</strong>
              <br />
              <strong>Patient ID:</strong> {savedPatientId}
            </div>
          )}

          <hr className="report-divider" />

          <h3>Pain Assessment</h3>

          {regions.length === 0 ? (
            <div className="report-empty">
              No pain regions recorded. Select regions on the 3D model to add
              them to this report.
            </div>
          ) : (
            <div className="pain-list">
              {regions.map(([spotId, data]) => {
                const displayRegionName = data.regionName || spotId;

                return (
                  <div key={spotId} className="pain-item">
                    <div className="pain-item-header">
                      <span className="pain-item-title">
                        📍 {data.regionName || regionName}
                      </span>

                      <span
                        className="pain-item-severity"
                        style={{
                          backgroundColor:
                            data.severity <= 3
                              ? "#4caf50"
                              : data.severity <= 6
                                ? "#ff9800"
                                : "#f44336",
                        }}
                      >
                        Severity: {data.severity}/10
                      </span>
                    </div>

                    <div className="pain-item-details">
                      <p>
                        <strong>Type:</strong>{" "}
                        {data.painType || "Not specified"}
                      </p>

                      {data.frequency && (
                        <p>
                          <strong>Frequency:</strong> {data.frequency}
                        </p>
                      )}

                      {data.startDate && (
                        <p>
                          <strong>Onset Date:</strong> {data.startDate}
                        </p>
                      )}

                      {data.notes && (
                        <p>
                          <strong>Notes:</strong> {data.notes}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="report-modal-footer">
          <button
            type="button"
            className="save-report-button"
            onClick={handleSaveOnly}
            disabled={isSaving}
          >
            {isSaving ? "Generating Report..." : "Save Report"}
          </button>

          <ReportButton
            patientName={patientName}
            patientAge={patientAge}
            reportDate={reportDate}
            regions={regions}
            saveReport={saveReport}
            isSaving={isSaving}
          />
        </div>
      </div>
    </div>
  );
}
