import { useState } from "react";

import TopBar from "./components/TopBar";
import LeftPanel from "./components/LeftPanel";
import Canvas3D from "./components/BodyPartsCanvas";
import RightPanel from "./components/RightPanel";
import ReportModal from "./components/ReportModal";
import Questionnaire from "./components/Questionnaire";
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
    console.log("Saved questionnaire answers:", answers);

    setQuestionnaireAnswers(answers);
    setAppState("app");
  }

  const handleClearAll = () => {
    setPainData({});
    setSelectedRegion(null);
  };

  return (
    <>
      {appState === "landing" && (
        <LandingPage onBegin={() => setAppState("questionnaire")} />
      )}

      {appState === "questionnaire" && (
        <Questionnaire onFinish={finishQuestionnaire} />
      )}

      {appState === "app" && (
        <>
          <div id="app">
            <TopBar
              setShowReport={setShowReport}
              onClearAll={handleClearAll}
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
            />

            <RightPanel
              selectedRegion={selectedRegion}
              setSelectedRegion={setSelectedRegion}
              painData={painData}
              setPainData={setPainData}
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
