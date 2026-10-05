import { useEffect, useRef, useState } from "react";
import "./VoiceIntake.css";

const SpeechRecognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

// Topics the old questionnaire covered, shown as hints so the spoken
// description still gives the report the same context.
const PROMPTS = [
  "When it started",
  "What you were doing",
  "Whether it spreads",
  "Better or worse since",
  "Constant or comes and goes",
  "What makes it worse",
  "What helps",
  "Had it before?",
  "Effect on daily life",
  "Other symptoms",
];

function joinText(base, addition) {
  const trimmed = addition.trim();
  if (!trimmed) return base;
  if (!base) return trimmed;
  return /\s$/.test(base) ? base + trimmed : `${base} ${trimmed}`;
}

function MicIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="17" x2="12" y2="22" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

export default function VoiceIntake({ onFinish, onBack }) {
  const [text, setText] = useState("");
  const [interim, setInterim] = useState("");
  const [listening, setListening] = useState(false);
  const [revising, setRevising] = useState(false);
  const [preRevisionText, setPreRevisionText] = useState(null);
  const [rawTranscript, setRawTranscript] = useState("");
  const [error, setError] = useState("");

  const recognitionRef = useRef(null);
  const listeningRef = useRef(false);

  useEffect(() => {
    return () => {
      listeningRef.current = false;
      recognitionRef.current?.abort();
    };
  }, []);

  function startListening() {
    if (!SpeechRecognition) return;

    setError("");

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";

    recognition.onresult = (event) => {
      let finalChunk = "";
      let interimChunk = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) finalChunk += result[0].transcript;
        else interimChunk += result[0].transcript;
      }

      if (finalChunk) {
        setText((prev) => joinText(prev, finalChunk));
        setRawTranscript((prev) => joinText(prev, finalChunk));
        setPreRevisionText(null);
      }
      setInterim(interimChunk);
    };

    recognition.onerror = (event) => {
      if (event.error === "no-speech" || event.error === "aborted") return;

      listeningRef.current = false;
      setListening(false);
      setError(
        event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Microphone access was blocked. Allow it in your browser settings, or type your description instead."
          : `Voice input stopped (${event.error}). You can try again or type instead.`,
      );
    };

    // Browsers end recognition after a pause; keep going until the user stops.
    recognition.onend = () => {
      setInterim("");
      if (listeningRef.current) {
        try {
          recognition.start();
          return;
        } catch {
          listeningRef.current = false;
        }
      }
      setListening(false);
    };

    recognitionRef.current = recognition;
    listeningRef.current = true;
    setListening(true);
    recognition.start();
  }

  function stopListening() {
    listeningRef.current = false;
    recognitionRef.current?.stop();
  }

  async function reviseWithAi() {
    if (!text.trim() || revising) return;

    stopListening();
    setRevising(true);
    setError("");

    try {
      const response = await fetch("/api/revise-transcript", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(result.detail || "The AI revision failed.");
      }

      setPreRevisionText(text);
      setText(result.revised);
    } catch (err) {
      setError(err.message || "The AI revision failed.");
    } finally {
      setRevising(false);
    }
  }

  function undoRevision() {
    if (preRevisionText === null) return;
    setText(preRevisionText);
    setPreRevisionText(null);
  }

  function finish() {
    if (text.trim().length < 10) {
      setError("Please describe your pain in a little more detail before continuing.");
      return;
    }

    stopListening();

    onFinish?.({
      patient_description: text.trim(),
      original_transcript: rawTranscript.trim() || text.trim(),
      ai_revised: preRevisionText !== null,
    });
  }

  return (
    <div className="intake-page">
      <header className="intake-top">
        <button type="button" className="intake-brand" onClick={onBack} disabled={!onBack}>
          Anatome
        </button>
        <span className="intake-step">Step 1 of 2 · Describe</span>
      </header>

      <div className="intake-layout">
        <section className="intake-intro">
          <h1>Tell us about your pain.</h1>

          <p className="intake-subtitle">
            {SpeechRecognition
              ? "Speak in your own words. Everything is transcribed below, and you can edit it before continuing."
              : "Voice input isn't supported in this browser (try Chrome, Edge or Safari), but you can type your description instead."}
          </p>

          <p className="intake-prompts-label">Things worth mentioning</p>
          <ol className="prompt-list">
            {PROMPTS.map((prompt, index) => (
              <li key={prompt}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {prompt}
              </li>
            ))}
          </ol>
        </section>

        <section className="intake-work">
          {SpeechRecognition && (
            <div className={listening ? "mic-row is-listening" : "mic-row"}>
              <button
                className="mic-button"
                onClick={listening ? stopListening : startListening}
                disabled={revising}
                aria-label={listening ? "Stop recording" : "Start recording"}
              >
                {listening ? <StopIcon /> : <MicIcon />}
              </button>
              <div className="mic-copy">
                <span className="mic-status">
                  {listening ? "Listening" : "Tap to start speaking"}
                </span>
                <span className="mic-hint">
                  {listening ? "Tap again to stop. Pauses are fine." : "Or type straight into the box below."}
                </span>
              </div>
            </div>
          )}

          <div className="transcript-box">
            <textarea
              className={revising ? "transcript revising" : "transcript"}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setPreRevisionText(null);
              }}
              readOnly={revising}
              aria-label="Pain description"
              placeholder="It started two days ago after I lifted a heavy box. Sharp pain in my lower back that gets worse when I bend over..."
            />
            <p className="interim" aria-live="polite">{interim}</p>
          </div>

          <div className="ai-row">
            <button
              className={revising ? "ai-button loading" : "ai-button"}
              onClick={reviseWithAi}
              disabled={!text.trim() || revising}
            >
              {revising ? "Tidying up..." : "Tidy up with AI"}
            </button>

            {preRevisionText !== null && !revising && (
              <button className="undo-button" onClick={undoRevision}>
                Undo
              </button>
            )}

            <span className="char-count">{text.trim() ? `${text.trim().split(/\s+/).length} words` : ""}</span>
          </div>

          {error && <p className="intake-error" role="alert">{error}</p>}

          <div className="navigation">
            {onBack ? (
              <button type="button" className="back-button" onClick={onBack}>
                Back
              </button>
            ) : <span />}
            <button className="next-button" onClick={finish} disabled={revising}>
              Continue to the body map
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
