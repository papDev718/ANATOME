import { useEffect, useRef, useState } from "react";
import "../css/ReportModal.css";
import ReportButton from "./ReportButton";
import CareGuide from "./CareGuide";
import { displayAnatomyName } from "../utils/anatomyName";

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
  const reportErrorRef = useRef(null);

  // The error renders inside the scrollable body, so bring it into view
  // when the footer buttons fail; otherwise the click looks like a no-op.
  useEffect(() => {
    if (reportError) {
      reportErrorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [reportError]);

  const regions = Object.entries(painData || {});

  // Analysis + patient tips load as soon as the modal opens; no name needed.
  const [guideState, setGuideState] = useState({ status: "loading", guide: null, analysis: null, error: "" });
  const [guideRequest, setGuideRequest] = useState(0);
  const ageForGuide = patientAge !== "" && !Number.isNaN(Number(patientAge)) ? Number(patientAge) : null;

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setGuideState((current) => ({ ...current, status: "loading", error: "" }));
      try {
        const response = await fetch("/api/care-guide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ age: ageForGuide, questionnaire: questionnaireAnswers || {}, pain_regions: painData }),
          signal: controller.signal,
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The tips could not be loaded.");
        setGuideState({ status: "ready", guide: result.guide, analysis: result.analysis, error: "" });
      } catch (error) {
        if (error.name === "AbortError") return;
        setGuideState({ status: "error", guide: null, analysis: null, error: error.message || "The tips could not be loaded. Is the server running?" });
      }
    }, ageForGuide === null ? 0 : 500);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [ageForGuide, painData, questionnaireAnswers, guideRequest]);

  const careLevel = guideState.analysis?.care_level;
  const localization = guideState.analysis?.localization || {};

  function validateReport() {
    if (!patientName.trim()) {
      throw new Error("Please enter your name.");
    }

    if (patientAge === "" || Number.isNaN(Number(patientAge)) || Number(patientAge) < 0 || Number(patientAge) > 120) {
      throw new Error("Please enter your age (0 to 120).");
    }

    if (!reportDate) {
      throw new Error("Please choose a report date.");
    }

    if (!questionnaireAnswers) {
      throw new Error(
        "Please describe your pain before generating the report.",
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

  return (
    <div className="report-overlay">
      <div className="report-modal report-modal--wide">
        <div className="report-modal-header">
          <div>
            <p className="report-kicker">Step 3 · Check it, then download</p>
            <h2>Clinical Pain Report</h2>
          </div>

          <button
            type="button"
            className="report-close-btn"
            onClick={() => setShowReport(false)}
            disabled={isSaving}
            aria-label="Close report"
          >
            Back to body map
          </button>
        </div>

        <div className="report-modal-columns">
        <div className="report-modal-body">
          {careLevel && (
            <div className="care-level-banner" data-level={careLevel.level}>
              <strong>{careLevel.title}.</strong> {careLevel.action}
            </div>
          )}

          <div className="patient-info-section">
            <div className="info-group">
              <label htmlFor="report-name">Your name</label>

              <input
                id="report-name"
                type="text"
                value={patientName}
                onChange={(event) => setPatientName(event.target.value)}
                placeholder="Full name"
                autoFocus
                disabled={isSaving}
              />
            </div>

            <div className="info-group">
              <label htmlFor="report-age">Your age</label>

              <input
                id="report-age"
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
              <label htmlFor="report-date">Date</label>

              <input
                id="report-date"
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
            <div ref={reportErrorRef} className="report-error-message" role="alert">
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
                const displayRegionName = (data.mode === "area" ? data.areaLabel : displayAnatomyName(data.regionName)) || spotId;
                const located = localization[spotId];

                return (
                  <div key={spotId} className="pain-item">
                    <div className="pain-item-header">
                      <span className="pain-item-title">
                        {displayRegionName}
                      </span>

                      <span
                        className="pain-item-severity"
                        data-level={
                          data.severity <= 3 ? "low" : data.severity <= 6 ? "mid" : "high"
                        }
                      >
                        {data.severity}/10
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

                      {data.onset && (
                        <p>
                          <strong>Started:</strong> {data.onset}
                        </p>
                      )}

                      {data.notes && (
                        <p>
                          <strong>Notes:</strong> {data.notes}
                        </p>
                      )}
                    </div>

                    {located && !located.candidates?.length && located.note && (
                      <p className="pain-item-structures__caveat">{located.note}</p>
                    )}

                    {located?.candidates?.length > 0 && (
                      <div className="pain-item-structures">
                        <p className="pain-item-structures__label">
                          Under the spot you tapped{located.where ? ` (${located.where})` : ""} · screening estimate, {located.confidence || "unranked"} confidence
                        </p>
                        <ol>
                          {located.candidates.slice(0, 3).map((candidate) => (
                            <li key={candidate.name}>
                              <span>{candidate.display}</span>
                              <span className="pain-item-structures__meta">{candidate.type} · {Math.round(candidate.share * 100)}%</span>
                            </li>
                          ))}
                        </ol>
                        {located.caveat && <p className="pain-item-structures__caveat">{located.caveat}</p>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <CareGuide
          guide={guideState.guide}
          status={guideState.status}
          error={guideState.error}
          onRetry={() => setGuideRequest((n) => n + 1)}
        />
        </div>

        <div className="report-modal-footer">
          <p className="report-footer-hint">
            {patientName.trim() && patientAge !== "" ? "Ready. Your PDF downloads in a few seconds." : "Add your name and age above, then download."}
          </p>

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
