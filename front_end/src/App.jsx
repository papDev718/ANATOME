import { useMemo, useState, useRef } from "react";

import TopBar from "./components/TopBar";
import Canvas3D from "./components/BodyPartsCanvas";
import RightPanel from "./components/RightPanel";
import ReportModal from "./components/ReportModal";
import VoiceIntake from "./components/VoiceIntake";
import LandingPage from "./components/LandingPage";
import { spotKey } from "./utils/bodyAreas";
import { EMPTY_VALUES, validateSpot } from "./utils/spotForm";
import { suggestAreas } from "./utils/suggestAreas";
import { prefillFromText } from "./utils/prefillFromText";

export default function App() {
  // Saved spots only. Pointing at the body never writes here; Save does.
  const [painData, setPainData] = useState({});

  // The spot being described: { spotId, isNew, target, values, dirty }.
  const [draft, setDraft] = useState(null);
  const [notice, setNotice] = useState("");
  // Label of the spot just saved, so the panel can confirm it and point to the next one.
  const [lastSaved, setLastSaved] = useState("");

  const [showReport, setShowReport] = useState(false);
  const [questionnaireAnswers, setQuestionnaireAnswers] = useState(null);

  // "landing", "questionnaire", "app"
  const [appState, setAppState] = useState("landing");

  const frameBodyRef = useRef(null);
  const pickAreaRef = useRef(null);

  // Areas the patient mentioned in their description, suggested on the map.
  const suggestions = useMemo(
    () => suggestAreas(questionnaireAnswers?.patient_description),
    [questionnaireAnswers],
  );
  const savedKeys = useMemo(() => new Set(Object.values(painData).map(spotKey)), [painData]);
  // Answers the patient already gave in the intake, offered on each new spot.
  const prefill = useMemo(
    () => prefillFromText(questionnaireAnswers?.patient_description),
    [questionnaireAnswers],
  );

  function finishQuestionnaire(answers) {
    setQuestionnaireAnswers(answers);
    setAppState("app");
  }

  function blockedByDraft(nextLabel) {
    if (!draft?.dirty) return false;
    setNotice(`Save or cancel ${draft.target.regionLabel} before moving to ${nextLabel}.`);
    return true;
  }

  function openTarget(target) {
    const existing = Object.entries(painData).find(([, spot]) => spotKey(spot) === target.key);
    const label = target.mode === "area" ? target.areaLabel : target.regionName;
    if (draft && draft.target.key === target.key) {
      // Another tap inside the open area moves the marked spot.
      if (target.clickPosition) {
        setDraft((current) => current && { ...current, target: { ...current.target, clickPosition: target.clickPosition } });
      }
      return;
    }
    if (blockedByDraft(label)) return;
    setNotice("");
    setLastSaved("");
    if (existing) {
      const [spotId, spot] = existing;
      setDraft({
        spotId,
        isNew: false,
        // A new tap inside a saved area moves its marker once saved.
        target: { ...target, regionLabel: label, clickPosition: target.clickPosition || spot.clickPosition },
        values: { ...EMPTY_VALUES, ...spot },
        dirty: false,
      });
    } else {
      setDraft({
        spotId: crypto.randomUUID(),
        isNew: true,
        target: { ...target, regionLabel: label },
        values: { ...EMPTY_VALUES, ...prefill },
        prefilled: Object.keys(prefill),
        dirty: false,
      });
    }
  }

  function editSpot(spotId) {
    const spot = painData[spotId];
    if (!spot || draft?.spotId === spotId) return;
    const label = spot.mode === "area" ? spot.areaLabel : spot.regionName;
    if (blockedByDraft(label)) return;
    setNotice("");
    setLastSaved("");
    const target = spot.mode === "area"
      ? { mode: "area", key: spotKey(spot), regionName: spot.areaLabel, areaKey: spot.areaKey, areaLabel: spot.areaLabel, side: spot.side, system: "area", clickPosition: spot.clickPosition }
      : { mode: "structure", key: spot.regionName, regionName: spot.regionName, system: spot.anatomicalSystem || "muscular", clickPosition: spot.clickPosition };
    setDraft({ spotId, isNew: false, target: { ...target, regionLabel: label }, values: { ...EMPTY_VALUES, ...spot }, dirty: false });
  }

  function dismissDraft({ force = false } = {}) {
    if (!draft) return;
    if (draft.dirty && !force) {
      setNotice(`You have unsaved details for ${draft.target.regionLabel}. Press Save, or Cancel to discard them.`);
      return;
    }
    setDraft(null);
    setNotice("");
    frameBodyRef.current?.();
  }

  function updateDraft(values) {
    setDraft((current) => current && {
      ...current,
      values: { ...current.values, ...values },
      // A changed answer is the patient's own, no longer a prefill.
      prefilled: (current.prefilled || []).filter((field) => !(field in values)),
      dirty: true,
    });
  }

  function saveDraft() {
    if (!draft) return {};
    const errors = validateSpot(draft.values);
    if (Object.keys(errors).length) return errors;
    const { target, values } = draft;
    setPainData((previous) => ({
      ...previous,
      [draft.spotId]: {
        ...values,
        mode: target.mode,
        regionName: target.regionName,
        areaKey: target.areaKey,
        areaLabel: target.areaLabel,
        side: target.side,
        anatomicalSystem: target.system,
        clickPosition: target.clickPosition,
      },
    }));
    setLastSaved(target.mode === "area" ? target.areaLabel : target.regionName);
    setDraft(null);
    setNotice("");
    frameBodyRef.current?.();
    return {};
  }

  function deleteSpot(spotId) {
    setPainData((previous) => {
      const next = { ...previous };
      delete next[spotId];
      return next;
    });
    if (draft?.spotId === spotId) setDraft(null);
  }

  const handleClearAll = () => {
    setPainData({});
    setDraft(null);
    setNotice("");
    setLastSaved("");
  };

  function openReport() {
    if (draft?.dirty) {
      setNotice(`Save or cancel ${draft.target.regionLabel} before making the report.`);
      return false;
    }
    if (Object.keys(painData).length === 0) {
      setNotice("Mark where it hurts and press Save on at least one spot before making the report.");
      return false;
    }
    setDraft(null);
    setNotice("");
    setShowReport(true);
    return true;
  }

  return (
    <>
      {appState === "landing" && (
        <LandingPage onBegin={() => setAppState("questionnaire")} />
      )}

      {appState === "questionnaire" && (
        <VoiceIntake
          onFinish={finishQuestionnaire}
          onBack={() => setAppState("landing")}
        />
      )}

      {appState === "app" && (
        <>
          <div id="app">
            <TopBar
              onOpenReport={openReport}
              savedCount={Object.keys(painData).length}
              onGoHome={() => {
                setShowReport(false);
                setAppState("landing");
              }}
            />

            <Canvas3D
              activeTarget={draft?.target || null}
              painData={painData}
              onPick={openTarget}
              onDismiss={() => dismissDraft()}
              frameBodyRef={frameBodyRef}
              pickAreaRef={pickAreaRef}
              suggestedKeys={suggestions.map((suggestion) => suggestion.key)}
            />

            <RightPanel
              draft={draft}
              notice={notice}
              suggestions={suggestions}
              savedKeys={savedKeys}
              onPickSuggestion={(key) => pickAreaRef.current?.(key)}
              onChange={updateDraft}
              onSave={saveDraft}
              onCancel={() => dismissDraft({ force: true })}
              onDelete={() => draft && deleteSpot(draft.spotId)}
              painData={painData}
              lastSaved={lastSaved}
              onEditSpot={editSpot}
              onDeleteSpot={deleteSpot}
              onClearAll={handleClearAll}
              onOpenReport={openReport}
            />
          </div>

          {showReport && (
            <ReportModal
              setShowReport={setShowReport}
              painData={painData}
              questionnaireAnswers={questionnaireAnswers}
            />
          )}
        </>
      )}
    </>
  );
}
