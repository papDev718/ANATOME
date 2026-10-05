import { motion } from "framer-motion";
import AnatomyHero from "./AnatomyHero";
import "./LandingPage.css";

const reveal = {
  initial: { opacity: 0, y: 14 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
};

const PROBLEMS = [
  {
    term: "Location",
    text: "\"My lower back\" covers a dozen muscles. Patients rarely have the words to narrow it down, and forms rarely ask.",
  },
  {
    term: "Intensity",
    text: "A 7 out of 10 means different things to different people. Without what it stops you doing, the number on its own doesn't say much.",
  },
  {
    term: "Context",
    text: "Onset, triggers, what helps, what makes it worse. These are the details clinicians ask for first, and the ones a checkbox form tends to lose.",
  },
];

const REPORT_SECTIONS = [
  "Patient information",
  "Pain assessment by region",
  "Patient-reported clinical summary",
  "Aggravating and relieving factors",
  "Region-specific documentation",
  "Items for clinician review",
  "Documentation statement",
  "Clinician notes",
];

const TEAM = [
  { name: "Pranav Arun Pillai", role: "UI/UX design, lead research, project coordination" },
  { name: "Arush Banerjee", role: "Team lead, front-end lead, 3D anatomy" },
  { name: "Kyle Hwang", role: "Lead software engineer, AI model development" },
  { name: "Mustafa Ali", role: "AI model development" },
];

function Waveform() {
  const bars = [4, 9, 14, 7, 18, 11, 22, 16, 8, 13, 20, 10, 6, 15, 9, 5, 12, 17, 7, 4];
  return (
    <svg className="wave" viewBox="0 0 120 24" aria-hidden="true">
      {bars.map((h, i) => (
        <rect key={i} x={i * 6} y={12 - h / 2} width="2" height={h} rx="1" style={{ animationDelay: `${i * 70}ms` }} />
      ))}
    </svg>
  );
}

export default function LandingPage({ onBegin }) {
  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="landing">
      <header className="lp-nav">
        <button type="button" className="lp-wordmark" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
          Anatome
        </button>
        <nav className="lp-nav__links" aria-label="Sections">
          <button type="button" onClick={() => scrollTo("how")}>How it works</button>
          <button type="button" onClick={() => scrollTo("report")}>The report</button>
          <button type="button" onClick={() => scrollTo("team")}>Team</button>
        </nav>
        <button type="button" className="lp-btn lp-btn--small" onClick={onBegin}>
          Start assessment
        </button>
      </header>

      <section className="lp-hero">
        <div className="lp-hero__copy">
          <motion.h1
            className="lp-hero__title"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          >
            Show us <em>where</em> it hurts.
          </motion.h1>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.35 }}
          >
            <p className="lp-hero__lede">
              Describe your pain out loud, mark it on a detailed model of the human body, and walk
              into your appointment with a report your clinician can read in a minute.
            </p>
            <div className="lp-hero__actions">
              <button type="button" className="lp-btn" onClick={onBegin}>
                Start assessment
              </button>
              <button type="button" className="lp-link" onClick={() => scrollTo("how")}>
                How it works
              </button>
            </div>
          </motion.div>
        </div>

        <div className="lp-hero__stage">
          <AnatomyHero />
        </div>

        <dl className="lp-hero__facts">
          <div><dt>669</dt><dd>named anatomical structures to select from</dd></div>
          <div><dt>Voice</dt><dd>or typed intake, in your own words</dd></div>
          <div><dt>8</dt><dd>section clinical PDF</dd></div>
          <div><dt>0</dt><dd>accounts or installs needed</dd></div>
        </dl>
      </section>

      <section className="lp-section lp-problem">
        <motion.h2 className="lp-statement" {...reveal}>
          Pain is specific. The forms we use to describe it are not.
        </motion.h2>
        <motion.dl className="lp-rows" {...reveal}>
          {PROBLEMS.map((item) => (
            <div className="lp-row" key={item.term}>
              <dt>{item.term}</dt>
              <dd>{item.text}</dd>
            </div>
          ))}
        </motion.dl>
      </section>

      <section className="lp-section" id="how">
        <motion.header className="lp-section__head" {...reveal}>
          <h2>How it works</h2>
          <p>Three steps. Nothing to install, no account.</p>
        </motion.header>

        <ol className="lp-steps">
          <motion.li className="lp-step" {...reveal}>
            <span className="lp-step__num">01</span>
            <div className="lp-step__text">
              <h3>Describe it</h3>
              <p>
                Talk through what happened, when it started and what makes it worse. Speech is
                transcribed as you go, and you can edit or tidy it before moving on.
              </p>
            </div>
            <figure className="lp-step__artifact lp-transcript">
              <div className="lp-transcript__bar">
                <span className="lp-rec" />
                <Waveform />
                <span className="mono">00:21</span>
              </div>
              <blockquote>
                It started about three weeks ago after moving furniture. Aching on the left side of my
                lower back, worse when I sit for long, a bit better after walking.
              </blockquote>
            </figure>
          </motion.li>

          <motion.li className="lp-step" {...reveal}>
            <span className="lp-step__num">02</span>
            <div className="lp-step__text">
              <h3>Point to it</h3>
              <p>
                Rotate a full musculoskeletal model and select the exact structure. Give each one a
                severity, a pain type, a frequency and when it began.
              </p>
            </div>
            <figure className="lp-step__artifact lp-mapped">
              <div className="lp-mapped__row">
                <span className="mono">Selected</span>
                <strong>Latissimus dorsi muscle, left</strong>
              </div>
              <div className="lp-mapped__scale" aria-hidden="true">
                {Array.from({ length: 10 }, (_, i) => (
                  <span key={i} className={i < 7 ? "is-on" : ""} />
                ))}
              </div>
              <div className="lp-mapped__meta mono">
                <span>7 / 10</span><span>Aching</span><span>Intermittent</span>
              </div>
            </figure>
          </motion.li>

          <motion.li className="lp-step" {...reveal}>
            <span className="lp-step__num">03</span>
            <div className="lp-step__text">
              <h3>Take the report</h3>
              <p>
                Your description and map are organised into a structured clinical summary, saved, and
                exported as a PDF you can print or send ahead of your visit.
              </p>
            </div>
            <figure className="lp-step__artifact lp-mini-doc">
              <span className="mono">Clinical_Pain_Report.pdf</span>
              <p className="lp-mini-doc__title">Clinical Pain Report</p>
              <p className="lp-mini-doc__line"><b>Primary region</b> L. latissimus dorsi</p>
              <p className="lp-mini-doc__line"><b>Aggravating</b> prolonged sitting</p>
              <p className="lp-mini-doc__line"><b>Relieving</b> walking</p>
            </figure>
          </motion.li>
        </ol>
      </section>

      <section className="lp-section lp-report" id="report">
        <motion.div className="lp-report__copy" {...reveal}>
          <h2>What your clinician receives</h2>
          <p>
            A plain, consistent document that puts location, severity and history on one page, in the
            order a clinician would ask for them. It records what you reported. It does not diagnose.
          </p>
          <ol className="lp-report__toc">
            {REPORT_SECTIONS.map((section, i) => (
              <li key={section}>
                <span className="mono">{String(i + 1).padStart(2, "0")}</span>
                {section}
              </li>
            ))}
          </ol>
        </motion.div>

        <motion.figure className="lp-paper" {...reveal}>
          <figcaption className="mono">Sample, fictional patient</figcaption>
          <header className="lp-paper__head">
            <div>
              <p className="lp-paper__title">Clinical Pain Report</p>
              <p className="lp-paper__sub">J. Rivera, 34 · 2 regions recorded</p>
            </div>
            <span className="lp-paper__date mono">2026-10-05</span>
          </header>

          <table className="lp-paper__table">
            <thead>
              <tr><th>Region</th><th>Severity</th><th>Type</th><th>Onset</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>L. latissimus dorsi</td>
                <td><span className="lp-sev lp-sev--high">7</span></td>
                <td>Aching</td>
                <td>3 wk</td>
              </tr>
              <tr>
                <td>L. deltoid, acromial part</td>
                <td><span className="lp-sev lp-sev--mid">5</span></td>
                <td>Sharp</td>
                <td>10 d</td>
              </tr>
            </tbody>
          </table>

          <div className="lp-paper__block">
            <p className="lp-paper__label">Patient-reported summary</p>
            <p>
              Onset after lifting furniture. Low back pain is worse with prolonged sitting and eases
              with walking. Shoulder pain is limited to overhead reaching. No numbness or weakness
              reported.
            </p>
          </div>
          <div className="lp-paper__block">
            <p className="lp-paper__label">For clinician review</p>
            <p>Sleep disturbance on two nights per week. Taking over-the-counter analgesia.</p>
          </div>
        </motion.figure>
      </section>

      <section className="lp-section lp-team" id="team">
        <motion.header className="lp-section__head" {...reveal}>
          <h2>Built by</h2>
        </motion.header>
        <motion.ul className="lp-team__list" {...reveal}>
          {TEAM.map((member) => (
            <li key={member.name}>
              <span className="lp-team__name">{member.name}</span>
              <span className="lp-team__role">{member.role}</span>
            </li>
          ))}
        </motion.ul>
      </section>

      <section className="lp-cta">
        <motion.h2 {...reveal}>Start with where it hurts.</motion.h2>
        <motion.div {...reveal}>
          <button type="button" className="lp-btn lp-btn--large" onClick={onBegin}>
            Start assessment
          </button>
        </motion.div>
      </section>

      <footer className="lp-footer">
        <span className="lp-wordmark lp-wordmark--static">Anatome</span>
        <p>
          Anatome is an educational screening tool. It does not provide medical diagnoses. Always
          consult a licensed healthcare professional.
        </p>
      </footer>
    </div>
  );
}
