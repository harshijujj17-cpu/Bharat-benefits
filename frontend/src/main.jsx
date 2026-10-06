import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
  "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
  "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

const NEEDS = [
  { id: "education", icon: "🎓", label: "Education", goal: "Education; scholarship support" },
  { id: "agriculture", icon: "🌾", label: "Agriculture", goal: "Agriculture support" },
  { id: "employment", icon: "💼", label: "Employment & Business", goal: "Start a business; find employment" },
  { id: "housing", icon: "🏠", label: "Housing", goal: "Housing assistance" },
  { id: "women", icon: "👩", label: "Women & Children", goal: "Women and child welfare support" },
  { id: "senior", icon: "👴", label: "Senior Citizens", goal: "Pension / retirement; senior citizen support" },
  { id: "disability", icon: "♿", label: "Disability", goal: "Disability support" },
  { id: "healthcare", icon: "🏥", label: "Healthcare", goal: "Healthcare support" },
  { id: "social", icon: "🛡", label: "Social Security", goal: "Social security; financial assistance" },
  { id: "other", icon: "✨", label: "Other", goal: "" },
];

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

function App() {
  const [step, setStep] = useState("home"); // home | profile | results
  const [need, setNeed] = useState(null);
  const [state, setState] = useState("");
  const [profile, setProfile] = useState({
    age: "", gender: "", occupation: "", annual_income: "", category: "",
    education: "", farmer_status: "No", student_status: "No", disability_status: "No",
    employment_status: "", district: "", customNeed: "",
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
    try {
      const resp = await fetch(`${API_URL}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) {
        setError(body?.detail?.message || body?.detail?.error || `Request failed (${resp.status})`);
      } else {
        setResult(body);
      }
    } catch (e) {
      setError("Could not reach the backend. Is the API server running?");
    } finally {
      setLoading(false);
    }
  }

  function startOver() {
    setStep("home");
    setNeed(null);
    setState("");
    setResult(null);
    setError("");
    setProfile({ age: "", gender: "", occupation: "", annual_income: "", category: "", education: "", farmer_status: "No", student_status: "No", disability_status: "No", employment_status: "", district: "", customNeed: "" });
  }

  return (
    <div className="app">
      <header className="site-header">
        <h1>Bharat Benefit Navigator</h1>
        <p className="tagline">AI-Powered State-Wise Citizen Welfare &amp; Benefit Assistant</p>
      </header>

      {step === "home" && (
        <main className="panel">
          <h2>What do you need help with?</h2>
          <p className="muted">Select a need, your state, and a few details. We will build your personalized benefit journey from live official government sources.</p>
          <div className="need-grid">
            {NEEDS.map((n) => (
              <button key={n.id} className={`need-card ${need?.id === n.id ? "selected" : ""}`}
                onClick={() => setNeed(n)}>
                <span className="need-icon">{n.icon}</span>
                <span>{n.label}</span>
              </button>
            ))}
          </div>
          {need?.id === "other" && (
            <label className="field">Describe your need<input value={profile.customNeed} onChange={(e) => update("customNeed", e.target.value)} placeholder="e.g. free coaching for entrance exams" /></label>
          )}
          <label className="field">Select Your State
            <select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="">Choose state / UT…</option>
              {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <div className="row">
            <button className="primary" disabled={!need || !state} onClick={() => setStep("profile")}>Continue</button>
          </div>
        </main>
      )}

      {step === "profile" && (
        <main className="panel">
          <h2>Tell us about yourself</h2>
          <p className="muted">Results for <strong>{state}</strong> · Need: <strong>{need?.label}</strong></p>
          <div className="form-grid">
            <label className="field">Age<input type="number" value={profile.age} onChange={(e) => update("age", e.target.value)} /></label>
            <label className="field">Gender<select value={profile.gender} onChange={(e) => update("gender", e.target.value)}><option value="">Select…</option><option>Female</option><option>Male</option><option>Other</option></select></label>
            <label className="field">Occupation<input value={profile.occupation} onChange={(e) => update("occupation", e.target.value)} placeholder="e.g. farmer, student" /></label>
            <label className="field">Annual household income (₹)<input type="number" value={profile.annual_income} onChange={(e) => update("annual_income", e.target.value)} /></label>
            <label className="field">Social category<select value={profile.category} onChange={(e) => update("category", e.target.value)}><option value="">Select…</option><option>General</option><option>OBC</option><option>SC</option><option>ST</option><option>EWS</option></select></label>
            <label className="field">Education<input value={profile.education} onChange={(e) => update("education", e.target.value)} placeholder="e.g. B.Tech, 10th pass" /></label>
            <label className="field">Farmer status<select value={profile.farmer_status} onChange={(e) => update("farmer_status", e.target.value)}><option>No</option><option>Yes</option></select></label>
            <label className="field">Student status<select value={profile.student_status} onChange={(e) => update("student_status", e.target.value)}><option>No</option><option>Yes</option></select></label>
            <label className="field">Disability status<select value={profile.disability_status} onChange={(e) => update("disability_status", e.target.value)}><option>No</option><option>Yes</option></select></label>
            <label className="field">Employment status<input value={profile.employment_status} onChange={(e) => update("employment_status", e.target.value)} placeholder="e.g. Student, Unemployed" /></label>
            <label className="field">District (optional)<input value={profile.district} onChange={(e) => update("district", e.target.value)} /></label>
          </div>
          <div className="row">
            <button className="ghost" onClick={() => setStep("home")}>Back</button>
            <button className="primary" onClick={findBenefits}>Find My Benefits</button>
          </div>
        </main>
      )}

      {step === "results" && (
        <main className="panel">
          <h2>Your Citizen Benefit Plan</h2>
          <p className="muted">Results for <strong>{state}</strong> · Need: <strong>{need?.label}</strong></p>
          {loading && <p className="muted">Searching live official sources and building your benefit journey…</p>}
          {error && <div className="error-box">⚠ {error}</div>}
          {result && <Results result={result} state={state} />}
          <div className="row">
            <button className="ghost" onClick={startOver}>Start over</button>
            <button className="ghost" onClick={() => setStep("profile")}>Edit profile</button>
          </div>
        </main>
      )}
    </div>
  );
}

function Results({ result, state }) {
  const recs = result.recommendations || [];
  const counts = { likely: 0, possible: 0, no: 0, info: 0 };
  for (const r of recs) {
    const label = statusLabel(r.eligibility_status);
    if (label === "Likely Eligible") counts.likely += 1;
    else if (label === "Possibly Eligible") counts.possible += 1;
    else if (label === "Not Eligible") counts.no += 1;
    else counts.info += 1;
  }
  return (
    <div>
      <div className="summary-cards">
        <div className="summary-card"><strong>{recs.length}</strong><span>Potential Benefits</span></div>
        <div className="summary-card"><strong>{counts.likely}</strong><span>Likely Eligible</span></div>
        <div className="summary-card"><strong>{counts.info}</strong><span>Need More Information</span></div>
        <div className="summary-card"><strong>{counts.no}</strong><span>Not Eligible</span></div>
      </div>
      {recs.length === 0 && <p className="muted">No relevant government benefits were found from live official sources for this profile. Try adding more details or a different need.</p>}
      {recs.map((r, i) => <BenefitCard key={i} scheme={r} state={state} others={recs.filter((_, j) => j !== i)} />)}
    </div>
  );
}

function BenefitCard({ scheme, state, others }) {
  const label = statusLabel(scheme.eligibility_status);
  const notEligible = label === "Not Eligible";
  return (
    <article className="benefit-card">
      <h3>{scheme.scheme_name}</h3>
      <div className={`badge ${label === "Likely Eligible" ? "ok" : label === "Not Eligible" ? "bad" : "warn"}`}>{label}</div>
      {scheme.relevance_explanation && <p><strong>Why:</strong> {scheme.relevance_explanation}</p>}
      {scheme.eligibility && <p><strong>Eligibility conditions:</strong> {typeof scheme.eligibility === "string" ? scheme.eligibility : JSON.stringify(scheme.eligibility)}</p>}
      {scheme.missing_information?.length > 0 && (
        <div><strong>Missing information:</strong><ul>{scheme.missing_information.map((m, i) => <li key={i}>{m}</li>)}</ul></div>
      )}
      {scheme.required_documents?.length > 0 && (
        <div><strong>Required documents:</strong><ul>{scheme.required_documents.map((d, i) => <li key={i}>{d}</li>)}</ul></div>
      )}
      {scheme.application_process && <p><strong>How to apply:</strong> {scheme.application_process}</p>}
      {scheme.government_department && <p><strong>State/Department:</strong> {scheme.government_department}</p>}
      {scheme.official_source_url && <p><a href={scheme.official_source_url} target="_blank" rel="noreferrer">View Official Government Source</a></p>}
      {notEligible && others.length > 0 && (
        <div className="alt-box">
          <strong>Why am I not eligible?</strong>
          <p>Based on the information provided, this benefit's conditions appear unmet. You may want to explore these alternatives:</p>
          <ul>{others.slice(0, 3).map((o, i) => <li key={i}>{o.scheme_name}</li>)}</ul>
        </div>
      )}
      <details className="journey">
        <summary>Application journey</summary>
        <ol>
          <li>Check eligibility against the official source</li>
          <li>Prepare the required documents above</li>
          <li>Visit the official portal/department</li>
          <li>Submit the application</li>
          <li>Track application status on the official portal</li>
        </ol>
        <p className="muted">Only steps supported by the retrieved official source are shown. Where the source text is silent, we mark the step as needing verification.</p>
      </details>
    </article>
  );
}

createRoot(document.getElementById("root")).render(<App />);
