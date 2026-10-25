import { useRef, useState } from "react";
import "../css/RightPanel.css";
import { displayAnatomyName } from "../utils/anatomyName";
import { AREA_CAVEATS } from "../utils/bodyAreas";

const PAIN_TYPES = ["Sharp", "Dull", "Aching", "Burning", "Throbbing", "Shooting", "Cramping", "Pressure", "Tingling", "Numb"];
const FREQUENCIES = ["Constant", "Comes and goes", "Only when I move it", "Rarely"];
// Same wording the red-flag rules read on the server.
const ONSETS = ["Within the last hour", "Today", "1–3 days ago", "4–7 days ago", "1–4 weeks ago", "More than one month ago"];
const SEVERITY_WORDS = { 1: "Barely there", 2: "Mild", 3: "Mild", 4: "Moderate", 5: "Moderate", 6: "Moderate", 7: "Severe", 8: "Severe", 9: "Very severe", 10: "Worst imaginable" };
const REQUIRED = ["severity", "painType", "frequency", "onset"];

function severityLevel(value) {
  if (value <= 3) return "low";
  if (value <= 6) return "mid";
  return "high";
}

function spotName(spot) {
  return (spot.mode === "area" ? spot.areaLabel : displayAnatomyName(spot.regionName)) || "Unknown spot";
}

function FieldError({ id, message }) {
  if (!message) return null;
  return <p id={id} className="field-error" role="alert">{message}</p>;
}

function Question({ id, number, label, answered, prefilled, error, children, aside }) {
  return (
    <fieldset className={`form-section ${error ? "has-error" : ""}`} id={id} aria-describedby={error ? `${id}-error` : undefined}>
      <legend className="form-label form-label--row">
        <span>
          <span className={`question-number ${answered ? "is-answered" : ""}`} aria-hidden="true">{number}</span>
          {label}
        </span>
        {aside}
      </legend>
      {children}
      {prefilled && <p className="prefill-note">Filled in from what you told us. Change it if this spot is different.</p>}
      <FieldError id={`${id}-error`} message={error} />
    </fieldset>
  );
}

function Pills({ options, value, onSelect }) {
  return (
    <div className="option-pills">
      {options.map((option) => (
        <button key={option} type="button" className={`option-pill ${value === option ? "active" : ""}`} onClick={() => onSelect(option)} aria-pressed={value === option}>
          {option}
        </button>
      ))}
    </div>
  );
}

function SavedList({ painData, onEdit, onDelete, onClearAll }) {
  const [confirmClear, setConfirmClear] = useState(false);
  const spots = Object.entries(painData);
  if (!spots.length) return null;
  return (
    <section className="saved-list" aria-label="Saved spots">
      <div className="saved-list__head">
        <p className="step-label">Saved · {spots.length}</p>
        {confirmClear ? (
          <span className="saved-list__confirm">
            Remove all?
            <button type="button" onClick={() => { onClearAll(); setConfirmClear(false); }}>Yes</button>
            <button type="button" onClick={() => setConfirmClear(false)}>No</button>
          </span>
        ) : (
          <button type="button" className="text-button" onClick={() => setConfirmClear(true)}>Clear all</button>
        )}
      </div>
      {spots.map(([spotId, spot]) => (
        <div key={spotId} className="saved-spot">
          <span className="saved-spot__severity" data-level={severityLevel(spot.severity)}>{spot.severity}</span>
          <button type="button" className="saved-spot__main" onClick={() => onEdit(spotId)} aria-label={`Edit ${spotName(spot)}`}>
            <span className="saved-spot__name">{spotName(spot)}</span>
            <span className="saved-spot__meta">{spot.painType} · {spot.onset}</span>
          </button>
          <button type="button" className="saved-spot__remove" onClick={() => onDelete(spotId)} aria-label={`Remove ${spotName(spot)}`}>Remove</button>
        </div>
      ))}
    </section>
  );
}

function IdleView({ notice, suggestions, savedKeys, onPickSuggestion, painData, lastSaved, onEditSpot, onDeleteSpot, onClearAll, onOpenReport }) {
  const savedCount = Object.keys(painData).length;
  const next = suggestions.find((s) => !savedKeys.has(s.key));
  const words = [...new Set(suggestions.flatMap((s) => s.words))];

  return (
    <>
      <div className="panel-scroll">
        {lastSaved && (
          <p className="saved-confirmation" role="status">
            <strong>{displayAnatomyName(lastSaved)}</strong> saved.
            {next ? " Do the next one, or tap anywhere else that hurts." : " Add another spot, or make your report."}
          </p>
        )}

        <div className="no-selection">
          <div className="no-sel-title">{savedCount ? "Anywhere else?" : "Where does it hurt?"}</div>
          <div className="no-sel-desc">
            {savedCount
              ? "Tap another place on the body, or make your report when you're done."
              : "Tap that place on the body. A few quick questions will open right here."}
          </div>
          {notice && <p className="panel-notice" role="status">{notice}</p>}
        </div>

        {suggestions.length > 0 && (
          <section className="suggestions" aria-label="Places you mentioned">
            <p className="step-label">You mentioned {words.map((w) => `"${w}"`).join(", ")}</p>
            <div className="suggestions__list">
              {suggestions.map((s) => {
                const done = savedKeys.has(s.key);
                return (
                  <button key={s.key} type="button" className={`suggestion ${done ? "is-done" : ""}`} onClick={() => onPickSuggestion(s.key)}>
                    <span>{s.label}</span>
                    <span className="suggestion__state">{done ? "Saved" : s.sideUnknown ? "Which side?" : "Describe"}</span>
                  </button>
                );
              })}
            </div>
            {suggestions.some((s) => s.sideUnknown && !savedKeys.has(s.key)) && (
              <p className="suggestions__why">You didn't say which side, so both are listed. Pick the one that hurts.</p>
            )}
          </section>
        )}

        <SavedList painData={painData} onEdit={onEditSpot} onDelete={onDeleteSpot} onClearAll={onClearAll} />
      </div>

      <div className="panel-footer">
        {next && (
          <button type="button" className="btn btn-primary btn-wide" onClick={() => onPickSuggestion(next.key)}>
            {savedCount ? "Next" : "Start"}: {next.label}
          </button>
        )}
        {savedCount > 0 ? (
          <button type="button" className={`btn ${next ? "btn-secondary" : "btn-primary"} btn-wide`} onClick={onOpenReport}>
            {next ? `I'm done, make my report (${savedCount})` : `Make my report (${savedCount} ${savedCount === 1 ? "spot" : "spots"})`}
          </button>
        ) : (
          !next && <p className="panel-footer__hint">Your report unlocks after you save one spot.</p>
        )}
      </div>
    </>
  );
}

function DraftView({ draft, notice, onChange, onSave, onCancel, onDelete }) {
  const [errors, setErrors] = useState({});
  const [showNotes, setShowNotes] = useState(Boolean(draft.values.notes));
  const scrollRef = useRef(null);

  const { values, target, isNew } = draft;
  const prefilled = new Set(draft.prefilled || []);
  const title = target.mode === "area" ? target.areaLabel : displayAnatomyName(target.regionName);
  const answered = REQUIRED.filter((field) => values[field]).length;
  const errorCount = Object.values(errors).filter(Boolean).length;

  const scrollTo = (field) => requestAnimationFrame(() => {
    scrollRef.current?.querySelector(`#spot-${field}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  const set = (field) => (value) => {
    onChange({ [field]: value });
    if (errors[field]) setErrors((current) => ({ ...current, [field]: undefined }));
    // Bring the next unanswered question into view so the patient never hunts for it.
    if (field !== "notes") {
      const nextField = REQUIRED.find((f) => f !== field && !values[f]);
      if (nextField) scrollTo(nextField);
    }
  };

  const handleSave = () => {
    const result = onSave();
    const missing = Object.keys(result || {});
    setErrors(result || {});
    if (missing.length) scrollTo(missing[0]);
  };

  return (
    <>
      <div className="panel-scroll" ref={scrollRef}>
        <div className="detail-header">
          <div className="detail-header__row">
            <div className="region-kicker">{isNew ? "Describe this spot" : "Editing saved spot"}</div>
            <button type="button" className="text-button" onClick={onCancel}>{isNew ? "Cancel" : "Discard changes"}</button>
          </div>
          <div className="region-title">{title}</div>
          {target.mode === "area" && (
            <p className="region-subtitle">
              {target.clickPosition ? "Exact spot marked. Tap again to move it." : "Optional: tap the exact spot inside the highlighted area."}
            </p>
          )}
          {target.mode === "area" && AREA_CAVEATS[target.areaKey] && (
            <p className="area-caveat">{AREA_CAVEATS[target.areaKey]}</p>
          )}
        </div>

        {notice && <p className="panel-notice" role="status">{notice}</p>}

        <Question
          id="spot-severity"
          number={1}
          label="How bad is it?"
          answered={Boolean(values.severity)}
          error={errors.severity}
          aside={values.severity && <span data-level={severityLevel(values.severity)} className="severity-readout">{values.severity}/10 · {SEVERITY_WORDS[values.severity]}</span>}
        >
          <div className="severity-scale" role="radiogroup" aria-label="Pain severity from 1 to 10">
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <button key={n} type="button" role="radio" aria-checked={values.severity === n} data-level={severityLevel(n)}
                className={`severity-step ${values.severity === n ? "active" : ""}`} onClick={() => set("severity")(n)}>
                {n}
              </button>
            ))}
          </div>
          <div className="severity-ends"><span>Mild</span><span>Worst</span></div>
        </Question>

        <Question id="spot-painType" number={2} label="What does it feel like?" answered={Boolean(values.painType)} prefilled={prefilled.has("painType")} error={errors.painType}>
          <Pills options={PAIN_TYPES} value={values.painType} onSelect={set("painType")} />
        </Question>
        <Question id="spot-frequency" number={3} label="How often?" answered={Boolean(values.frequency)} prefilled={prefilled.has("frequency")} error={errors.frequency}>
          <Pills options={FREQUENCIES} value={values.frequency} onSelect={set("frequency")} />
        </Question>
        <Question id="spot-onset" number={4} label="When did it start?" answered={Boolean(values.onset)} prefilled={prefilled.has("onset")} error={errors.onset}>
          <Pills options={ONSETS} value={values.onset} onSelect={set("onset")} />
        </Question>

        <div className="form-section">
          {showNotes ? (
            <>
              <label className="form-label" htmlFor="pain-notes">Anything else about this spot? <span className="optional-mark">optional</span></label>
              <textarea
                id="pain-notes"
                className="notes-textarea"
                placeholder="What makes it worse or better, whether it spreads, swelling..."
                value={values.notes}
                autoFocus
                onChange={(event) => set("notes")(event.target.value)}
              />
            </>
          ) : (
            <button type="button" className="text-button" onClick={() => setShowNotes(true)}>+ Add a note (optional)</button>
          )}
        </div>

        {!isNew && (
          <div className="form-section">
            <button type="button" className="text-button text-button--danger" onClick={onDelete}>Remove this spot</button>
          </div>
        )}
      </div>

      <div className="panel-footer">
        {errorCount > 0 ? (
          <p className="form-error-summary" role="alert">
            {errorCount === 1 ? "One question still needs an answer." : `${errorCount} questions still need an answer.`}
          </p>
        ) : (
          <div className="answer-progress" aria-label={`${answered} of 4 questions answered`}>
            {REQUIRED.map((field) => <span key={field} className={values[field] ? "is-done" : ""} />)}
            <span className="answer-progress__text">{answered === 4 ? "All set" : `${answered} of 4 answered`}</span>
          </div>
        )}
        <button type="button" className="btn btn-primary btn-wide" onClick={handleSave}>
          {isNew ? "Save this spot" : "Save changes"}
        </button>
      </div>
    </>
  );
}

export default function RightPanel(props) {
  const { draft } = props;
  return (
    <aside className="glass-panel panel-right">
      {draft
        ? <DraftView key={draft.spotId} {...props} />
        : <IdleView {...props} />}
    </aside>
  );
}
