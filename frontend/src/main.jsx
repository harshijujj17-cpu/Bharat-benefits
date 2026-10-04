import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const indianStates = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
  "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
  "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

const situations = ["Student", "Farmer", "Employee", "Self-employed", "Entrepreneur", "Unemployed", "Homemaker", "Retired", "Other"];
const descriptors = ["SC", "ST", "OBC", "General", "EWS", "Minority", "Person with disability", "Low-income household", "Woman", "Senior citizen", "Farmer", "Entrepreneur", "Student"];
const goals = ["Education", "Start a business", "Find employment", "Agriculture support", "Housing", "Healthcare", "Financial assistance", "Skill development", "Women's support", "Disability support", "Pension / retirement", "Child welfare", "Energy / electricity"];

const initialProfile = {
  age: "",
  state: "",
  district: "",
  gender: "",
  situation: "",
  descriptors: [],
  goals: [],
  customGoal: "",
  education: "",
  occupation: "",
  category: "",
  annual_income: "",
  disability_status: "No",
  farmer_status: "No",
  student_status: "No",
  employment_status: "",
  top_k: 8,
};

const loadingSteps = [
  "Understanding your situation",
  "Generating official-source research queries",
  "Searching live government sources",
  "Extracting scheme facts",
  "Checking eligibility and missing information",
  "Building your benefits journey",
];

function App() {
  const [profile, setProfile] = useState(initialProfile);
  const [step, setStep] = useState(0);
  const [askText, setAskText] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [selectedCompare, setSelectedCompare] = useState([]);

  const recommendations = result?.recommendations || [];
  const knownMissing = useMemo(
    () => profileCompleteness(profile, recommendations),
    [profile, recommendations],
  );

  function update(field, value) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  function toggleList(field, value) {
    setProfile((current) => {
      const exists = current[field].includes(value);
      const next = exists
        ? current[field].filter((item) => item !== value)
        : [...current[field], value];
      const patch = { [field]: next };
      if (field === "descriptors") {
        if (value === "Farmer") patch.farmer_status = exists ? "No" : "Yes";
        if (value === "Student") patch.student_status = exists ? "No" : "Yes";
        if (value === "Person with disability") patch.disability_status = exists ? "No" : "Yes";
        if (["SC", "ST", "OBC", "General", "EWS", "Minority"].includes(value)) {
          patch.category = exists ? "" : value;
        }
      }
      return { ...current, ...patch };
    });
  }

  function resetProfile() {
    setProfile(initialProfile);
    setStep(0);
    setAskText("");
    setResult(null);
    setError("");
    setSelectedCompare([]);
  }

  function analyzeAskText() {
    const parsed = inferProfileFromText(askText);
    setProfile(parsed);
    setStep(3);
  }

  async function submitProfile(nextProfile = profile) {
    setLoading(true);
    setError("");
    setResult(null);
    setSelectedCompare([]);
    setActiveStep(0);
    const timer = window.setInterval(() => {
      setActiveStep((current) => Math.min(current + 1, loadingSteps.length - 1));
    }, 850);

    try {
      const requestPayload = buildPayload(nextProfile);
      const response = await fetch(`${API_URL}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail?.message || "Live government-source verification is currently unavailable.");
      }
      const journeyResponse = await fetch(`${API_URL}/benefits/journey`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload),
      });
      const journey = journeyResponse.ok ? await journeyResponse.json() : null;
      setResult({ ...payload, journey });
      setActiveStep(loadingSteps.length - 1);
    } catch {
      setError("Live government-source verification is currently unavailable. Please try again in a moment.");
    } finally {
      window.clearInterval(timer);
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <Nav />
      <Hero />
      <section className="navigator-layout" id="profile">
        <ProfileBuilder
          profile={profile}
          step={step}
          setStep={setStep}
          update={update}
          toggleList={toggleList}
          submitProfile={submitProfile}
          resetProfile={resetProfile}
          loading={loading}
        />
        <AskAI askText={askText} setAskText={setAskText} analyzeAskText={analyzeAskText} />
      </section>
      {!result && !loading && !error && <EmptyBenefitsMap />}
      {loading && <LoadingPanel activeStep={activeStep} />}
      {(result || error) && !loading && (
        <BenefitsWorkspace
          result={result}
          error={error}
          profile={profile}
          recommendations={recommendations}
          knownMissing={knownMissing}
          selectedCompare={selectedCompare}
          setSelectedCompare={setSelectedCompare}
          submitProfile={submitProfile}
        />
      )}
      <HowItWorks />
    </main>
  );
}

function Nav() {
  return (
    <nav className="navbar">
      <a className="brand" href="#home"><span className="brand-mark">AI</span><span>Benefits Navigator</span></a>
      <div className="nav-links">
        <a href="#home">Home</a>
        <a href="#profile">My Profile</a>
        <a href="#benefits">My Benefits</a>
        <a href="#ask">Search / Ask AI</a>
        <a href="#about">About</a>
      </div>
      <span className="powered">Official-source AI</span>
    </nav>
  );
}

function Hero() {
  return (
    <section className="hero product-hero" id="home">
      <div className="hero-copy">
        <p className="eyebrow">AI decision-support assistant</p>
        <h1>Government benefits, personalized for you.</h1>
        <p className="hero-subtitle">Tell us what you're going through.</p>
        <p className="hero-description">
          We'll find relevant government support, explain your eligibility, identify missing information, and show you what to do next.
        </p>
        <div className="hero-actions">
          <a className="primary-button hero-button" href="#profile">Build My Benefits Profile →</a>
          <a className="secondary-button hero-button" href="#ask">Ask the AI</a>
        </div>
      </div>
      <div className="glass-card journey-card">
        <p className="eyebrow">Personalized journey</p>
        {["Profile and goals", "Live official-source research", "Eligibility reasoning", "Missing info and action plan"].map((item, index) => (
          <div className="journey-line" key={item}><span>{String(index + 1).padStart(2, "0")}</span><p>{item}</p></div>
        ))}
      </div>
    </section>
  );
}

function ProfileBuilder({ profile, step, setStep, update, toggleList, submitProfile, resetProfile, loading }) {
  const steps = ["You", "Situation", "Descriptors", "Goal"];
  return (
    <section className="glass-card profile-card progressive-card">
      <div className="card-heading">
        <div><p className="eyebrow">My Profile</p><h2>Build your benefits profile</h2></div>
        <button className="text-button" onClick={resetProfile}>Reset</button>
      </div>
      <div className="progress-tabs">
        {steps.map((label, index) => (
          <button className={step === index ? "active" : ""} onClick={() => setStep(index)} key={label}>{index + 1}. {label}</button>
        ))}
      </div>
      {step === 0 && (
        <div className="form-grid">
          <Field label="Age"><input type="number" min="1" max="120" value={profile.age} onChange={(event) => update("age", event.target.value)} placeholder="24" /></Field>
          <Field label="State / UT"><select value={profile.state} onChange={(event) => update("state", event.target.value)}><option value="">Select state</option>{indianStates.map((state) => <option key={state}>{state}</option>)}</select></Field>
          <Field label="District / City"><input value={profile.district} onChange={(event) => update("district", event.target.value)} placeholder="Mysuru, Pune, Delhi..." /></Field>
          <Field label="Gender"><select value={profile.gender} onChange={(event) => update("gender", event.target.value)}><option value="">Select</option><option>Female</option><option>Male</option><option>Other</option><option>Prefer not to say</option></select></Field>
        </div>
      )}
      {step === 1 && (
        <div className="goal-panel">
          <ChoiceGrid items={situations} selected={[profile.situation]} onSelect={(item) => update("situation", item)} />
          <div className="form-grid">
            <Field label="Student status"><select value={profile.student_status} onChange={(event) => update("student_status", event.target.value)}><option>No</option><option>Yes</option></select></Field>
            <Field label="Farmer status"><select value={profile.farmer_status} onChange={(event) => update("farmer_status", event.target.value)}><option>No</option><option>Yes</option></select></Field>
            <Field label="Employment status"><select value={profile.employment_status} onChange={(event) => update("employment_status", event.target.value)}><option value="">Select</option><option>Student</option><option>Employed</option><option>Self-employed</option><option>Unemployed</option><option>Retired</option><option>Homemaker</option></select></Field>
            <Field label="Disability"><select value={profile.disability_status} onChange={(event) => update("disability_status", event.target.value)}><option>No</option><option>Yes</option></select></Field>
          </div>
        </div>
      )}
      {step === 2 && <ChoiceGrid items={descriptors} selected={profile.descriptors} onSelect={(item) => toggleList("descriptors", item)} />}
      {step === 3 && (
        <div className="goal-panel">
          <ChoiceGrid items={goals} selected={profile.goals} onSelect={(item) => toggleList("goals", item)} />
          <Field label="Your own goal"><textarea value={profile.customGoal} onChange={(event) => update("customGoal", event.target.value)} placeholder="I want to start a small dairy business." /></Field>
          <div className="form-grid">
            <Field label="Occupation"><input value={profile.occupation} onChange={(event) => update("occupation", event.target.value)} placeholder="Student, farmer, tailor..." /></Field>
            <Field label="Education"><input value={profile.education} onChange={(event) => update("education", event.target.value)} placeholder="B.Tech, 12th pass..." /></Field>
            <Field label="Annual household income"><input type="number" min="0" value={profile.annual_income} onChange={(event) => update("annual_income", event.target.value)} placeholder="250000" /></Field>
            <Field label="Results"><select value={profile.top_k} onChange={(event) => update("top_k", event.target.value)}><option value="5">5 insights</option><option value="8">8 insights</option><option value="12">12 insights</option></select></Field>
          </div>
        </div>
      )}
      <div className="builder-actions">
        <button className="secondary-button" disabled={step === 0} onClick={() => setStep(Math.max(0, step - 1))}>Back</button>
        {step < 3 ? (
          <button className="primary-button compact-button" onClick={() => setStep(step + 1)}>Continue</button>
        ) : (
          <button className="primary-button compact-button" disabled={loading} onClick={() => submitProfile(profile)}>Research My Benefits</button>
        )}
      </div>
    </section>
  );
}

function AskAI({ askText, setAskText, analyzeAskText }) {
  return (
    <section className="glass-card ask-card" id="ask">
      <p className="eyebrow">Search / Ask AI</p>
      <h2>Tell us naturally</h2>
      <p className="muted">Speak or type your situation and goal. The app converts it into backend profile fields, then uses live official-source research.</p>
      <textarea value={askText} onChange={(event) => setAskText(event.target.value)} placeholder="I'm 24, from Karnataka, unemployed, OBC, and I want to start a tailoring business." />
      <button className="secondary-button" disabled={!askText.trim()} onClick={analyzeAskText}>Analyze Situation</button>
      <div className="voice-note">Voice can plug into the existing speech helpers when exposed by the backend; no API keys are exposed here.</div>
    </section>
  );
}

function ChoiceGrid({ items, selected, onSelect }) {
  return <div className="choice-grid">{items.map((item) => <button className={selected.includes(item) ? "choice active" : "choice"} onClick={() => onSelect(item)} key={item}>{item}</button>)}</div>;
}

function Field({ label, children }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function EmptyBenefitsMap() {
  return (
    <section className="glass-card state-card" id="benefits">
      <p className="eyebrow">My Benefits</p>
      <h2>Your benefits map is empty.</h2>
      <p>Build your profile to discover support relevant to your situation.</p>
      <a className="source-button empty-cta" href="#profile">Build My Profile →</a>
    </section>
  );
}

function LoadingPanel({ activeStep }) {
  return (
    <section className="glass-card loading-panel" aria-live="polite">
      <div><p className="eyebrow">Live Research</p><h2>Building your benefits journey</h2><p className="muted">No local scheme catalogue is used. Verification depends on current official-source retrieval.</p></div>
      <div className="step-list">{loadingSteps.map((item, index) => <div className={`step ${index < activeStep ? "done" : ""} ${index === activeStep ? "active" : ""}`} key={item}><span>{index < activeStep ? "✓" : index === activeStep ? "⟳" : "○"}</span><p>{item}</p></div>)}</div>
    </section>
  );
}

function BenefitsWorkspace({ result, error, profile, recommendations, knownMissing, selectedCompare, setSelectedCompare, submitProfile }) {
  if (error) {
    return <section className="glass-card state-card error-card"><p className="eyebrow">Live verification unavailable</p><h2>We couldn't verify live government information right now.</h2><p>{error}</p><button className="secondary-button empty-cta" onClick={() => submitProfile(profile)}>Try again</button></section>;
  }
  if (!recommendations.length) {
    return <section className="glass-card state-card"><p className="eyebrow">No strong match</p><h2>No matching benefits found from live official sources.</h2><p>{result?.notice || "Add more details about your income, situation, category, or goal and run a new search."}</p></section>;
  }
  return (
    <section className="results-section" id="benefits">
      <div className="results-heading">
        <div><p className="eyebrow">Personalized benefits map</p><h2>Based on your profile and current official sources.</h2><p>{profileLine(profile)}</p></div>
        <div className="count-card"><strong>{recommendations.length}</strong><span>benefit insights</span></div>
      </div>
      <BenefitsJourney recommendations={recommendations} profile={profile} />
      <MissingInfo knownMissing={knownMissing} />
      <BackendJourney journey={result?.journey} />
      {result?.retrieval && <SourcesChecked retrieval={result.retrieval} />}
      <div className="scheme-grid">{recommendations.map((scheme, index) => <BenefitInsight key={`${scheme.scheme_name}-${index}`} scheme={scheme} selected={selectedCompare.includes(index)} onCompare={() => toggleCompare(index, selectedCompare, setSelectedCompare)} />)}</div>
      {selectedCompare.length > 0 && <ComparePanel recommendations={selectedCompare.map((index) => recommendations[index]).filter(Boolean)} />}
    </section>
  );
}

function BenefitsJourney({ recommendations, profile }) {
  const lanes = ["Education", "Career", "Financial", "Agriculture", "Housing", "Healthcare"];
  return (
    <div className="journey-map">
      {lanes.map((lane) => {
        const match = recommendations.find((scheme) => textBlob(scheme).includes(lane.toLowerCase()) || textBlob(scheme).includes(profile.goals.join(" ").toLowerCase()));
        return <div className="glass-card journey-mini" key={lane}><span>{lane}</span><strong>{match ? "Possible support" : "No strong match found"}</strong><p>{match?.scheme_name || "Add more profile details to improve this area."}</p></div>;
      })}
    </div>
  );
}

function BackendJourney({ journey }) {
  const steps = journey?.journey || [];
  if (!steps.length) return null;
  return (
    <div className="glass-card missing-panel">
      <div><p className="eyebrow">Benefits journey</p><h3>Backend action plan</h3></div>
      <div className="known-grid">
        {steps.slice(0, 4).map((step) => (
          <div key={`${step.step}-${step.scheme_name}`}>
            <strong>{step.eligibility_state}: {step.scheme_name}</strong>
            <span>{step.next_action}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MissingInfo({ knownMissing }) {
  return (
    <div className="glass-card missing-panel">
      <div><p className="eyebrow">Complete your profile</p><h3>Improve the results</h3></div>
      <div className="known-grid">
        <div><strong>We know</strong>{knownMissing.known.map((item) => <span key={item}>✓ {item}</span>)}</div>
        <div><strong>We still need</strong>{knownMissing.missing.map((item) => <span key={item}>⚠ {item}</span>)}</div>
      </div>
    </div>
  );
}

function SourcesChecked({ retrieval }) {
  const urls = retrieval.source_urls || [];
  return (
    <div className="glass-card trust-panel">
      <div><p className="eyebrow">Sources checked</p><h3>Official-source transparency</h3></div>
      <div className="source-list">{urls.slice(0, 8).map((url) => <a href={url} target="_blank" rel="noreferrer" key={url}>✓ {domainOf(url)}</a>)}</div>
    </div>
  );
}

function BenefitInsight({ scheme, selected, onCompare }) {
  const sourceUrl = scheme.official_source_url || scheme.official_source || scheme.application_url;
  const verification = scheme.source_verification || {};
  return (
    <article className="glass-card scheme-card insight-card">
      <div className="scheme-top"><div><p className="eyebrow">{scheme.government_department || "Benefit insight"}</p><h3>{scheme.scheme_name}</h3></div><span className={`status-pill ${scheme.eligibility_status || "cannot_confirm"}`}>{labelForStatus(scheme.eligibility_status)}</span></div>
      {verification.domain && <div className="verified-line"><span>{verification.is_official_government_source ? "✓ Official source" : "Source returned by API"}</span><strong>{verification.domain}</strong></div>}
      <InfoBlock title="Why this matches you" value={scheme.relevance_explanation} />
      <InfoBlock title="You appear to match" value={scheme.eligibility} />
      <ListBlock title="We still need to verify" value={scheme.missing_information} warn />
      <InfoBlock title="What you may receive" value={scheme.benefits} />
      <ListBlock title="What to prepare" value={scheme.required_documents} />
      <InfoBlock title="Next action" value={scheme.application_process || "Open the official source and verify the latest eligibility notification before applying."} />
      <InfoBlock title="Important restrictions / dates" value={scheme.important_dates} />
      <div className="card-actions"><button className={selected ? "secondary-button selected" : "secondary-button"} onClick={onCompare}>{selected ? "Added to compare" : "Compare option"}</button>{sourceUrl && <a className="source-button" href={sourceUrl} target="_blank" rel="noreferrer">Open Official Portal →</a>}</div>
    </article>
  );
}

function ComparePanel({ recommendations }) {
  return (
    <section className="glass-card compare-panel">
      <p className="eyebrow">Compare options</p>
      <div className="compare-grid">{recommendations.map((scheme) => <div key={scheme.scheme_name}><h3>{scheme.scheme_name}</h3><p><strong>Purpose:</strong> {scheme.description || "Not stated in source."}</p><p><strong>Eligibility:</strong> {asText(scheme.eligibility)}</p><p><strong>Benefit:</strong> {scheme.benefits || "Not stated in source."}</p><p><strong>Application:</strong> {scheme.application_process || "Use official source."}</p></div>)}</div>
    </section>
  );
}

function InfoBlock({ title, value }) {
  if (!value) return null;
  return <section className="info-block"><h4>{title}</h4><p>{asText(value)}</p></section>;
}

function ListBlock({ title, value, warn = false }) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  if (!items.length) return null;
  return <section className="info-block"><h4>{title}</h4><ul>{items.map((item, index) => <li key={`${item}-${index}`}>{warn ? "⚠" : "✓"} {item}</li>)}</ul></section>;
}

function HowItWorks() {
  return <section className="how-section" id="about"><div className="section-heading"><p className="eyebrow">How it works</p><h2>Not a scheme directory. A benefits navigation assistant.</h2></div><div className="how-grid">{["Tell us about yourself", "We research official sources", "AI checks your situation", "Get your personalized action plan"].map((item, index) => <div className="glass-card how-card" key={item}><span>{String(index + 1).padStart(2, "0")}</span><h3>{item}</h3></div>)}</div></section>;
}

function inferProfileFromText(text) {
  const lowered = text.toLowerCase();
  const parsed = { ...initialProfile };
  const ageMatch = lowered.match(/(\d{1,2})\s*(?:year|yr|-year|,)/);
  const incomeMatch = lowered.match(/(?:income|family income|annual income)[^\d]*(\d+(?:\.\d+)?)\s*(lakh|lakhs|k|thousand)?/) || lowered.match(/₹\s*(\d+(?:\.\d+)?)\s*(lakh|lakhs|k|thousand)?/);
  if (ageMatch) parsed.age = ageMatch[1];
  for (const state of indianStates) if (lowered.includes(state.toLowerCase())) parsed.state = state;
  if (lowered.includes("female") || lowered.includes("woman") || lowered.includes("girl")) parsed.gender = "Female";
  if (lowered.includes("male") || lowered.includes("man") || lowered.includes("boy")) parsed.gender = "Male";
  for (const item of situations) if (lowered.includes(item.toLowerCase())) parsed.situation = item;
  if (lowered.includes("b.tech") || lowered.includes("btech")) parsed.education = "B.Tech";
  if (lowered.includes("student")) { parsed.situation = "Student"; parsed.occupation = "Student"; parsed.student_status = "Yes"; parsed.employment_status = "Student"; parsed.descriptors = unique([...parsed.descriptors, "Student"]); }
  if (lowered.includes("farmer")) { parsed.situation = "Farmer"; parsed.occupation = "Farmer"; parsed.farmer_status = "Yes"; parsed.descriptors = unique([...parsed.descriptors, "Farmer"]); }
  if (lowered.includes("unemployed")) { parsed.situation = "Unemployed"; parsed.employment_status = "Unemployed"; }
  if (lowered.includes("retired")) { parsed.situation = "Retired"; parsed.employment_status = "Retired"; }
  if (lowered.includes("business") || lowered.includes("startup") || lowered.includes("tailoring") || lowered.includes("dairy")) parsed.goals = unique([...parsed.goals, "Start a business"]);
  for (const item of goals) if (lowered.includes(item.toLowerCase())) parsed.goals = unique([...parsed.goals, item]);
  for (const category of ["OBC", "SC", "ST", "General", "EWS", "Minority"]) if (lowered.includes(category.toLowerCase())) { parsed.category = category; parsed.descriptors = unique([...parsed.descriptors, category]); }
  if (lowered.includes("disabled") || lowered.includes("disability")) { parsed.disability_status = "Yes"; parsed.descriptors = unique([...parsed.descriptors, "Person with disability"]); }
  if (incomeMatch) {
    const raw = Number(incomeMatch[1]);
    const unit = incomeMatch[2] || "";
    parsed.annual_income = Math.round(unit.startsWith("lakh") ? raw * 100000 : unit.startsWith("k") || unit.startsWith("thousand") ? raw * 1000 : raw);
  }
  parsed.customGoal = text;
  return parsed;
}

function buildPayload(profile) {
  const occupation = profile.occupation || profile.situation || null;
  const category = profile.category || profile.descriptors.find((item) => ["SC", "ST", "OBC", "General", "EWS", "Minority"].includes(item)) || null;
  const education = profile.education || (profile.descriptors.includes("Student") || profile.situation === "Student" ? "Student" : null);
  const goalText = unique([...profile.goals, profile.customGoal]).join("; ");
  return {
    age: profile.age ? Number(profile.age) : null,
    gender: profile.gender || null,
    state: profile.state || null,
    district: profile.district || null,
    education,
    occupation,
    category,
    annual_income: profile.annual_income ? Number(profile.annual_income) : null,
    annual_household_income_inr: profile.annual_income ? Number(profile.annual_income) : null,
    disability_status: profile.disability_status,
    farmer_status: profile.farmer_status,
    student_status: profile.student_status,
    employment_status: profile.employment_status || null,
    goal: goalText || null,
    current_situation: profile.situation || null,
    descriptors: profile.descriptors,
    other_relevant_information: goalText || null,
    top_k: Number(profile.top_k || 8),
  };
}

function profileCompleteness(profile, recommendations) {
  const known = [];
  const missing = [];
  if (profile.age) known.push("Age"); else missing.push("Age");
  if (profile.state) known.push("State"); else missing.push("State");
  if (profile.situation || profile.occupation) known.push("Current situation"); else missing.push("Occupation / situation");
  if (profile.category) known.push("Category"); else missing.push("Social category if applicable");
  if (profile.annual_income) known.push("Household income"); else missing.push("Annual household income");
  const sourceMissing = unique(recommendations.flatMap((item) => item.missing_information || [])).slice(0, 3);
  return { known, missing: unique([...missing, ...sourceMissing]).slice(0, 6) };
}

function toggleCompare(index, selectedCompare, setSelectedCompare) {
  setSelectedCompare(selectedCompare.includes(index) ? selectedCompare.filter((item) => item !== index) : [...selectedCompare, index].slice(-3));
}

function labelForStatus(status) {
  if (status === "relevant") return "Likely match";
  if (status === "likely_not_eligible" || status === "not_relevant") return "Not a match";
  return "Needs verification";
}

function profileLine(profile) {
  return [profile.age && `${profile.age} years`, profile.gender, profile.state, profile.situation, profile.category, profile.goals.join(", ")].filter(Boolean).join(" • ");
}

function textBlob(scheme) {
  return Object.values(scheme).flat().join(" ").toLowerCase();
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

function asText(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return Object.entries(value).map(([key, val]) => `${key}: ${val}`).join(", ");
  return value || "Not stated in source.";
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

createRoot(document.getElementById("root")).render(<App />);
