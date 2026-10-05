import { useState, useRef, useCallback } from "react"; // useCallback kept for handlePainSaved

import TopBar from "./components/TopBar";
import LeftPanel from "./components/LeftPanel";
import Canvas3D from "./components/BodyPartsCanvas";
import RightPanel from "./components/RightPanel";
import ReportModal from "./components/ReportModal";
import VoiceIntake from "./components/VoiceIntake";
import LandingPage from "./components/LandingPage";

export default function App() {
  // Despite its name, this stores the generated spot ID
  const [selectedRegion, setSelectedRegion] = useState(null);

  const [showReport, setShowReport] = useState(false);
  const [painData, setPainData] = useState({});

  const [questionnaireAnswers, setQuestionnaireAnswers] = useState(null);

  // "landing", "questionnaire", "app"
  const [appState, setAppState] = useState("landing");

  function finishQuestionnaire(answers) {
    setQuestionnaireAnswers(answers);
    setAppState("app");
  }

  const framBodyRef = useRef(null);
  const deselectRef = useRef(null);

  const handleClearAll = () => {
    setPainData({});
    setSelectedRegion(null);
  };

  const handlePainSaved = useCallback(() => {
    setSelectedRegion(null);
    framBodyRef.current?.();
  }, []);

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
              setShowReport={setShowReport}
              onClearAll={handleClearAll}
              onGoHome={() => {
                setShowReport(false);
                setAppState("landing");
              }}
            />

            <LeftPanel
              selectedRegion={selectedRegion}
              setSelectedRegion={setSelectedRegion}
              painData={painData}
              setPainData={setPainData}
            />

            <Canvas3D
              selectedRegion={selectedRegion}
              setSelectedRegion={setSelectedRegion}
              setPainData={setPainData}
              painData={painData}
              frameBodyRef={framBodyRef}
              deselectRef={deselectRef}
            />

            <RightPanel
              selectedRegion={selectedRegion}
              setSelectedRegion={setSelectedRegion}
              painData={painData}
              setPainData={setPainData}
              onPainSaved={handlePainSaved}
              onCancel={() => deselectRef.current?.()}
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
