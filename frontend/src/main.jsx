import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./journey.css";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const NEEDS = [
  { id: "education", label: "Education", desc: "Scholarships, fee support, student welfare", goal: "Education; scholarship support" },
  { id: "agriculture", label: "Agriculture", desc: "Farmer support, subsidies, crop schemes", goal: "Agriculture support" },
  { id: "employment", label: "Employment & Business", desc: "Jobs, skilling, enterprise support", goal: "Start a business; find employment" },
  { id: "housing", label: "Housing", desc: "Affordable housing and construction support", goal: "Housing assistance" },
  { id: "women", label: "Women & Children", desc: "Welfare, nutrition, protection schemes", goal: "Women and child welfare support" },
  { id: "senior", label: "Senior Citizens", desc: "Pension and old-age support", goal: "Pension / retirement; senior citizen support" },
  { id: "disability", label: "Disability", desc: "Support for persons with disabilities", goal: "Disability support" },
  { id: "healthcare", label: "Healthcare", desc: "Health insurance and treatment support", goal: "Healthcare support" },
  { id: "social", label: "Social Security", desc: "Pensions, insurance, financial aid", goal: "Social security; financial assistance" },
  { id: "other", label: "Other", desc: "Describe your own need", goal: "" },
];

const ICONS = {
  education: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 10L12 5 2 10l10 5 10-5z"/><path d="M6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/></svg>,
  agriculture: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 22V12"/><path d="M12 12C12 7 8 4 3 4c0 5 4 8 9 8z"/><path d="M12 12c0-5 4-8 9-8 0 5-4 8-9 8z"/></svg>,
  employment: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>,
  housing: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>,
  women: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M12 12v7"/><path d="M9 16h6"/></svg>,
  senior: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="10" cy="5" r="2.5"/><path d="M10 8v6l4 6"/><path d="M10 14l-3 4"/><path d="M14 9l4-2"/></svg>,
  disability: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="5" r="2.2"/><path d="M12 8v5h5"/><path d="M15 16a5 5 0 1 1-7-6"/></svg>,
  healthcare: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 21C7 16.5 3 13 3 8.8A4.8 4.8 0 0 1 12 6a4.8 4.8 0 0 1 9 2.8C21 13 17 16.5 12 21z"/><path d="M12 10v6M9 13h6"/></svg>,
  social: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 4.5-3.2 7.7-8 9-4.8-1.3-8-4.5-8-9V6l8-3z"/></svg>,
  other: <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><circle cx="12" cy="16.5" r="0.6" fill="currentColor"/></svg>,
};

const STATUS_LABEL = {
  relevant: "Likely Eligible",
  eligible: "Likely Eligible",
  possibly_eligible: "Possibly Eligible",
  cannot_confirm: "Need More Information",
  unknown: "Need More Information",
  not_relevant: "Not Eligible",
  likely_not_eligible: "Not Eligible",
};

function statusLabel(status) {
  return STATUS_LABEL[(status || "").toLowerCase()] || "Need More Information";
}

function badgeClass(label) {
  if (label === "Likely Eligible") return "badge ok";
  if (label === "Not Eligible") return "badge bad";
  return "badge warn";
}

const STEPS = ["Need", "Telangana", "Profile", "Benefit Plan"];
const LOADING_STAGES = [
  "Searching official sources",
  "Verifying Telangana relevance",
  "Checking need relevance",
  "Evaluating eligibility",
  "Building your Benefit Plan",
];

function App() {
  const [step, setStep] = useState("need"); // need | state | profile | results
  const [need, setNeed] = useState(null);
  const [state, setState] = useState("Telangana");
  const [profile, setProfile] = useState({
    age: "", gender: "", occupation: "", annual_income: "", category: "",
    education: "", farmer_status: "No", student_status: "No", disability_status: "No",
    employment_status: "", district: "", customNeed: "",
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    if (!loading) return;
    setStageIndex(0);
    const id = setInterval(() => setStageIndex((i) => Math.min(i + 1, LOADING_STAGES.length - 1)), 2500);
    return () => clearInterval(id);
  }, [loading]);

  function update(field, value) {
    setProfile((p) => ({ ...p, [field]: value }));
  }

  async function findBenefits() {
    setLoading(true);
    setError("");
    setResult(null);
    setStep("results");
    const goalText = need && need.goal ? need.goal : profile.customNeed || "Government benefit support";
    const payload = {
      state,
      age: profile.age === "" ? null : Number(profile.age),
      gender: profile.gender || null,
      occupation: profile.occupation || null,
      annual_income: profile.annual_income === "" ? null : Number(profile.annual_income),
      category: profile.category || null,
      education: profile.education || null,
      farmer_status: profile.farmer_status,
      student_status: profile.student_status,
      disability_status: profile.disability_status,
      employment_status: profile.employment_status || null,
      district: profile.district || null,
      goal: goalText,
      need: need ? need.label : null,
      top_k: 8,
    };
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);
    try {
      const resp = await fetch(`${API_URL}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const body = await resp.json();
      if (!resp.ok) {
        setError(body?.detail?.message || body?.detail?.error || `Request failed (${resp.status})`);
      } else {
        setResult(body);
      }
    } catch (e) {
      if (e.name === "AbortError") {
        setError("The server took too long to respond. Please try again.");
      } else {
        setError("Could not reach the backend. Is the API server running?");
      }
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  function startOver() {
    setStep("need");
    setNeed(null);
    setState("Telangana");
    setResult(null);
    setError("");
    setProfile({ age: "", gender: "", occupation: "", annual_income: "", category: "", education: "", farmer_status: "No", student_status: "No", disability_status: "No", employment_status: "", district: "", customNeed: "" });
  }

  const stepIndex = STEPS.findIndex((_, i) => ["need", "state", "profile", "results"][i] === step);

  return (
    <div className="app">
      <header className="site-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18"/><path d="M5 21V10l7-6 7 6v11"/><path d="M9 21v-6h6v6"/></svg>
          </span>
          <div>
            <p className="wordmark">Bharat Benefit Navigator</p>
            <p className="tagline">Find government benefits that fit your needs.</p>
            <p className="support-line">AI-powered welfare discovery for citizens of Telangana.</p>
          </div>
        </div>
      </header>

      <nav className="stepper" aria-label="Progress">
        {STEPS.map((label, i) => (
          <div key={label} className={`step ${i === stepIndex ? "active" : ""} ${i < stepIndex ? "done" : ""}`}>
            <span className="step-num">{i + 1}</span>
            <span className="step-label">{label}</span>
            {i < STEPS.length - 1 && <span className="step-bar" aria-hidden="true" />}
          </div>
        ))}
      </nav>

      <main className="page">
        {(need || state) && step !== "results" && (
          <div className="chipbar" aria-label="Current selection">
            {need && <span className="chip">Need: <strong>{need.label}</strong></span>}
            {state && <span className="chip">State: <strong>{state}</strong></span>}
          </div>
        )}

        {step === "need" && (
          <section className="card panel">
            <h2>What do you need help with?</h2>
            <p className="muted">Pick a need. We will build your benefit plan from live official government sources.</p>
            <div className="need-grid">
              {NEEDS.map((n) => (
                <button key={n.id} type="button" className={`need-card ${need?.id === n.id ? "selected" : ""}`}
                  onClick={() => setNeed(n)} aria-pressed={need?.id === n.id}>
                  <span className="need-icon">{ICONS[n.id]}</span>
                  <span className="need-title">{n.label}</span>
                  <span className="need-desc">{n.desc}</span>
                </button>
              ))}
            </div>
            {need?.id === "other" && (
              <label className="field">Describe your need
                <input value={profile.customNeed} onChange={(e) => update("customNeed", e.target.value)} placeholder="e.g. free coaching for entrance exams" />
              </label>
            )}
            <div className="row">
              <button className="primary" disabled={!need} onClick={() => setStep("state")}>Continue</button>
            </div>
          </section>
        )}

        {step === "state" && (
          <section className="card panel">
            <h2>Your state</h2>
            <p className="muted">Bharat Benefit Navigator currently serves citizens of Telangana.</p>
            <div className="state-current">
              <span className="state-current-label">State</span>
              <strong className="state-current-value">Telangana</strong>
            </div>
            <div className="row">
              <button className="ghost" onClick={() => setStep("need")}>Back</button>
              <button className="primary" onClick={() => setStep("profile")}>Continue</button>
            </div>
          </section>
        )}

        {step === "profile" && (
          <div className="profile-layout">
            <section className="card panel">
              <h2>Tell us about yourself</h2>
              <p className="muted">Optional details can improve recommendation accuracy.</p>

              <h3 className="group-title">Basics</h3>
              <div className="form-grid">
                <label className="field">Age<input type="number" value={profile.age} onChange={(e) => update("age", e.target.value)} /></label>
                <label className="field">Gender<select value={profile.gender} onChange={(e) => update("gender", e.target.value)}><option value="">Select…</option><option>Female</option><option>Male</option><option>Other</option></select></label>
                <label className="field">Annual household income
                  <span className="income-wrap"><span className="rupee">₹</span><input type="number" value={profile.annual_income} onChange={(e) => update("annual_income", e.target.value)} /></span>
                  <span className="hint">Approximate is fine</span>
                </label>
              </div>

              <h3 className="group-title">Situation</h3>
              <div className="form-grid">
                <label className="field">Occupation<input value={profile.occupation} onChange={(e) => update("occupation", e.target.value)} placeholder="e.g. farmer, student" /></label>
                <label className="field">Education<input value={profile.education} onChange={(e) => update("education", e.target.value)} placeholder="e.g. B.Tech, 10th pass" /></label>
                <label className="field">Employment status<input value={profile.employment_status} onChange={(e) => update("employment_status", e.target.value)} placeholder="e.g. Student, Unemployed" /></label>
              </div>

              <h3 className="group-title">Status</h3>
              <div className="form-grid">
                <Segmented label="Farmer" value={profile.farmer_status} onChange={(v) => update("farmer_status", v)} />
                <Segmented label="Student" value={profile.student_status} onChange={(v) => update("student_status", v)} />
                <Segmented label="Disability" value={profile.disability_status} onChange={(v) => update("disability_status", v)} />
              </div>
              <div className="field">
                <span className="field-label">Social category</span>
                <div className="chip-row" role="radiogroup" aria-label="Social category">
                  {["General", "OBC", "SC", "ST", "EWS"].map((c) => (
                    <button type="button" key={c} role="radio" aria-checked={profile.category === c}
                      className={`chip-option ${profile.category === c ? "selected" : ""}`}
                      onClick={() => update("category", profile.category === c ? "" : c)}>{c}</button>
                  ))}
                </div>
              </div>

              <h3 className="group-title">Optional</h3>
              <div className="form-grid">
                <label className="field">District<input value={profile.district} onChange={(e) => update("district", e.target.value)} /></label>
              </div>

              <div className="row">
                <button className="ghost" onClick={() => setStep("state")}>Back</button>
                <button className="primary" disabled={loading} onClick={findBenefits}>{loading ? "Searching…" : "Find My Benefits"}</button>
              </div>
            </section>

            <aside className="card summary-side" aria-label="Profile summary">
              <h3>Citizen Profile Summary</h3>
              <dl>
                <dt>Need</dt><dd>{need ? need.label : "—"}</dd>
                <dt>State</dt><dd>{state || "—"}</dd>
                <dt>Age</dt><dd>{profile.age || "—"}</dd>
                <dt>Gender</dt><dd>{profile.gender || "—"}</dd>
                <dt>Income</dt><dd>{profile.annual_income ? `₹${Number(profile.annual_income).toLocaleString("en-IN")}/yr` : "—"}</dd>
                <dt>Category</dt><dd>{profile.category || "—"}</dd>
                <dt>Occupation</dt><dd>{profile.occupation || "—"}</dd>
                <dt>Education</dt><dd>{profile.education || "—"}</dd>
                <dt>Employment</dt><dd>{profile.employment_status || "—"}</dd>
                <dt>Farmer / Student / Disability</dt><dd>{`${profile.farmer_status} / ${profile.student_status} / ${profile.disability_status}`}</dd>
                <dt>District</dt><dd>{profile.district || "—"}</dd>
              </dl>
            </aside>
          </div>
        )}

        {step === "results" && (
          <section className="card panel">
            <h2>Your Citizen Benefit Plan</h2>
            <div className="chipbar">
              <span className="chip">State: <strong>{state || "—"}</strong></span>
              <span className="chip">Need: <strong>{need ? need.label : "—"}</strong></span>
            </div>

            {loading && (
              <div>
                <h3>Finding benefits for you</h3>
                <ol className="loader-stages" aria-live="polite">
                {LOADING_STAGES.map((label, i) => (
                  <li key={label} className={i < stageIndex ? "done" : i === stageIndex ? "active" : ""}>
                    <span className="dot" aria-hidden="true" />{label}{i < LOADING_STAGES.length - 1 ? "" : "…"}
                  </li>
                ))}
                </ol>
              </div>
            )}

            {error && (
              <div className="error-box" role="alert">
                ⚠ Government sources are temporarily busy. Please try again.
                <div className="row"><button className="primary" onClick={findBenefits}>Try Again</button></div>
              </div>
            )}

            {result?.notice && (
              <div className="notice-box" role="status">ℹ {result.notice}</div>
            )}

            {result && <Results result={result} state={state} />}

            <div className="row">
              <button className="ghost" onClick={startOver}>Start over</button>
              <button className="ghost" onClick={() => setStep("profile")}>Edit profile</button>
            </div>
          </section>
        )}
      </main>

      <footer className="site-footer">
        <p>Bharat Benefit Navigator · Telangana</p>
        <p>Guidance only, not a guarantee of eligibility. Confirm details on the official government website.</p>
      </footer>
    </div>
  );
}

function Segmented({ label, value, onChange }) {
  return (
    <div className="field">
      <span className="field-label" id={`seg-${label}`}>{label}</span>
      <div className="segmented" role="radiogroup" aria-labelledby={`seg-${label}`}>
        {["Yes", "No"].map((opt) => (
          <button type="button" key={opt} role="radio" aria-checked={value === opt}
            className={value === opt ? "selected" : ""} onClick={() => onChange(opt)}>{opt}</button>
        ))}
      </div>
    </div>
  );
}

function Results({ result, state }) {
  const recs = result.recommendations || [];
  const [selectedIndex, setSelectedIndex] = useState(null);
  const counts = { likely: 0, possible: 0, no: 0, info: 0 };
  for (const r of recs) {
    const label = statusLabel(r.eligibility_status);
    if (label === "Likely Eligible") counts.likely += 1;
    else if (label === "Possibly Eligible" || label === "Need More Information") counts.info += 1;
    else if (label === "Not Eligible") counts.no += 1;
    else counts.info += 1;
  }
  return (
    <div>
      <div className="summary-cards">
        <div className="summary-card"><strong>{recs.length}</strong><span>Potential Benefits</span></div>
        <div className="summary-card"><strong className="ok-text">{counts.likely}</strong><span>Likely Eligible</span></div>
        <div className="summary-card"><strong className="warn-text">{counts.info}</strong><span>Need More Information</span></div>
        <div className="summary-card"><strong className="bad-text">{counts.no}</strong><span>Not Eligible</span></div>
      </div>
      {recs.length === 0 && !result?.notice && (
        <p className="muted">No verified matching benefits found yet. The system could not find sufficiently supported matches for this profile. Try adding more details or a different need.</p>
      )}
      {recs.map((r, i) => <BenefitCard key={i} scheme={r} state={state} others={recs.filter((_, j) => j !== i)} onDetails={() => setSelectedIndex(i)} />)}
      {selectedIndex !== null && recs[selectedIndex] && (
        <div className="details-overlay" role="dialog" aria-modal="true" onClick={() => setSelectedIndex(null)}>
          <div className="details-panel" onClick={(e) => e.stopPropagation()}>
            <button className="ghost details-close" onClick={() => setSelectedIndex(null)} aria-label="Close details">Close</button>
            <DetailsView scheme={recs[selectedIndex]} state={state} others={recs.filter((_, j) => j !== selectedIndex)} />
          </div>
        </div>
      )}
    </div>
  );
}

function BenefitCard({ scheme, state, others, onDetails }) {
  const label = statusLabel(scheme.eligibility_status);
  const notEligible = label === "Not Eligible";
  return (
    <article className="benefit-card">
      <h3>{scheme.scheme_name}</h3>
      <div className={badgeClass(label)}>{label}</div>
      {scheme.relevance_explanation && <p className="reason"><strong>Why:</strong> {scheme.relevance_explanation}</p>}
      {scheme.official_source_url && (
        <p><a className="source-btn" href={scheme.official_source_url} target="_blank" rel="noreferrer">Open official source →</a></p>
      )}
      <button className="ghost details-btn" onClick={onDetails} aria-label={`Details for ${scheme.scheme_name}`}>Details</button>
      <details className="card-details">
        <summary>Benefits, eligibility, documents &amp; steps</summary>
        {scheme.benefits && <p><strong>Benefits:</strong> {scheme.benefits}</p>}
        {scheme.eligibility && <p><strong>Eligibility:</strong> {typeof scheme.eligibility === "string" ? scheme.eligibility : JSON.stringify(scheme.eligibility)}</p>}
        {scheme.required_documents?.length > 0 && (
          <div><strong>Required documents:</strong><ul>{scheme.required_documents.map((d, i) => <li key={i}>{d}</li>)}</ul></div>
        )}
        {scheme.application_process && <p><strong>How to apply:</strong> {scheme.application_process}</p>}
        {scheme.government_department && <p><strong>State/Department:</strong> {scheme.government_department}</p>}
        {scheme.missing_information?.length > 0 && (
          <div className="missing"><strong>Missing information:</strong><ul>{scheme.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul></div>
        )}
        {scheme.source_verification && <p className="muted">Source: {scheme.source_verification.domain || "official source"} ({scheme.source_verification.tier || "verified"})</p>}
        <ol className="journey">
          <li>Check eligibility against the official source</li>
          <li>Prepare the required documents above</li>
          <li>Visit the official portal/department</li>
          <li>Submit the application</li>
          <li>Track application status on the official portal</li>
        </ol>
      </details>
      {notEligible && others.length > 0 && (
        <div className="alt-box">
          <strong>Why am I not eligible?</strong>
          <p>Based on the information provided, this benefit's conditions appear unmet. You may want to explore these alternatives:</p>
          <ul>{others.slice(0, 3).map((o, i) => <li key={i}>{o.scheme_name}</li>)}</ul>
        </div>
      )}
    </article>
  );
}

function DetailsView({ scheme, state, others }) {
  const label = statusLabel(scheme.eligibility_status);
  return (
    <div>
      <h3>{scheme.scheme_name || "Unnamed benefit"}</h3>
      <div className={badgeClass(label)}>{label}</div>
      <DetailSection title="Why this result was produced" value={scheme.relevance_explanation} />
      <DetailSection title="Eligibility status" value={label} />
      <DetailSection title="Benefit description" value={scheme.description} />
      <DetailSection title="Benefit value" value={scheme.benefits} />
      <DetailSection title="Eligibility conditions" value={typeof scheme.eligibility === "string" ? scheme.eligibility : null} />
      <DetailSection title="Required documents" list={scheme.required_documents} />
      <DetailSection title="Application process" value={scheme.application_process} />
      <DetailSection title="Important dates" value={scheme.important_dates} />
      <DetailSection title="State/Department" value={scheme.government_department} />
      <DetailSection title="Missing information" list={scheme.missing_information} emptyText="No missing information reported." missing />
      <p><strong>State:</strong> {state || "Not provided"}</p>
      {scheme.official_source_url ? (
        <p><a className="source-btn" href={scheme.official_source_url} target="_blank" rel="noreferrer">Open official source →</a></p>
      ) : (
        <p className="muted">No official source URL returned.</p>
      )}
      {scheme.source_verification && <p className="muted">Source: {scheme.source_verification.domain || "official source"} ({scheme.source_verification.tier || "verified"})</p>}
      {others.length > 0 && (
        <div className="alt-box">
          <strong>Alternatives:</strong>
          <ul>{others.slice(0, 3).map((o, i) => <li key={i}>{o.scheme_name || "Unnamed benefit"}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function DetailSection({ title, value, list, emptyText, missing }) {
  const cls = missing ? "detail-block missing" : "detail-block";
  if (list && Array.isArray(list) && list.length > 0) {
    return <Detail blockTitle={title} cls={cls}><ul>{list.map((item, i) => <li key={i}>{String(item)}</li>)}</ul></Detail>;
  }
  if (list && Array.isArray(list) && list.length === 0) {
    return <Detail blockTitle={title} cls={cls}><p className="muted">{emptyText || "Not provided by the retrieved source."}</p></Detail>;
  }
  if (value === null || value === undefined || value === "") {
    return <Detail blockTitle={title} cls={cls}><p className="muted">Not provided by the retrieved source.</p></Detail>;
  }
  if (typeof value === "object") {
    return <Detail blockTitle={title} cls={cls}><p className="muted">Not provided by the retrieved source.</p></Detail>;
  }
  return <Detail blockTitle={title} cls={cls}><p>{String(value)}</p></Detail>;
}

function Detail({ blockTitle, children, cls }) {
  return <div className={cls || "detail-block"}><strong>{blockTitle}</strong>{children}</div>;
}

createRoot(document.getElementById("root")).render(<App />);
