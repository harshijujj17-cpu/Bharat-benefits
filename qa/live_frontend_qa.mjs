import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const appUrl = (process.env.QA_FRONTEND_URL || "http://127.0.0.1:5173").replace(/\/$/, "");
const outputDir = path.resolve(process.env.QA_OUTPUT_DIR || "qa/results");
const locations = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
  "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
  "Ladakh", "Lakshadweep", "Puducherry",
];

const profile = {
  age: "21", gender: "Female", category: "OBC", occupation: "student", education: "B.Tech",
  income: "250000", disability: "No", farmer: "No", student: "Yes", employment: "Student",
};

function canonicalUrl(value) {
  if (!value) return "";
  const parsed = new URL(value);
  return `${parsed.protocol.toLowerCase()}//${parsed.host.toLowerCase()}${parsed.pathname.replace(/\/$/, "")}`;
}

function validateResponse(body, location) {
  const failures = [];
  const warnings = [];
  const retrieval = body?.retrieval || {};
  if (retrieval.mode !== "live_web_search" || retrieval.provider !== "tavily") failures.push("missing_live_retrieval_metadata");
  if (retrieval.cached !== false) failures.push("live_retrieval_not_explicitly_uncached");
  if (!(retrieval.queries || []).some((query) => String(query).toLowerCase().includes(location.toLowerCase()))) failures.push("no_state_specific_generated_query");
  const grounded = new Set((retrieval.source_urls || []).map(canonicalUrl));
  for (const scheme of body?.recommendations || []) {
    const source = scheme.official_source_url || scheme.official_source;
    if (!source) failures.push(`missing_official_source:${scheme.scheme_name || "unknown"}`);
    else if (!grounded.has(canonicalUrl(source))) failures.push(`ungrounded_source:${scheme.scheme_name || source}`);
    const verified = scheme.source_verification?.is_official_government_source;
    const host = source ? new URL(source).hostname.replace(/^www\./, "") : "";
    if (!verified && !host.endsWith(".gov.in") && !host.endsWith(".nic.in") && host !== "myscheme.gov.in") warnings.push(`unverified_source:${host || "unknown"}`);
  }
  return { failures, warnings };
}

async function select(page, label, value) {
  await page.locator(`label.field:has-text("${label}") select`).selectOption({ label: value });
}

async function fill(page, label, value) {
  await page.locator(`label.field:has-text("${label}") input`).fill(value);
}

async function configureProfile(page, location) {
  await fill(page, "Age", profile.age);
  await select(page, "State / UT", location);
  await select(page, "Gender", profile.gender);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await select(page, "Student status", profile.student);
  await select(page, "Farmer status", profile.farmer);
  await select(page, "Employment status", profile.employment);
  await select(page, "Disability", profile.disability);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.locator("button.choice", { hasText: profile.category }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.locator("button.choice", { hasText: "Education" }).click();
  await fill(page, "Occupation", profile.occupation);
  await fill(page, "Education", profile.education);
  await fill(page, "Annual household income", profile.income);
}

function assertPayload(payload, location, failures, prefix = "") {
  const expected = {
    age: Number(profile.age), gender: profile.gender, state: location, category: profile.category,
    occupation: profile.occupation, education: profile.education, annual_income: Number(profile.income),
    annual_household_income_inr: Number(profile.income), disability_status: profile.disability,
    farmer_status: profile.farmer, student_status: profile.student, employment_status: profile.employment,
  };
  for (const [key, value] of Object.entries(expected)) {
    if (payload[key] !== value) failures.push(`${prefix}payload_mismatch:${key}:expected=${JSON.stringify(value)}:actual=${JSON.stringify(payload[key])}`);
  }
}

async function submitAndCapture(page, location, label, requestCounter) {
  const requestCountBefore = requestCounter.count;
  const requestPromise = page.waitForRequest((request) => request.url().endsWith("/recommend") && request.method() === "POST", { timeout: 120000 });
  const responsePromise = page.waitForResponse((response) => response.url().endsWith("/recommend") && response.request().method() === "POST", { timeout: 120000 });
  const button = page.getByRole("button", { name: "Research My Benefits", exact: true });
  if (await button.isDisabled()) throw new Error(`${label}: research button visually disabled`);
  await button.click();
  const [request, response] = await Promise.all([requestPromise, responsePromise]);
  const payload = request.postDataJSON();
  const body = await response.json().catch(() => null);
  await page.waitForTimeout(500);
  const requestCount = requestCounter.count - requestCountBefore;
  return { payload, body, status: response.status(), requestCount };
}

async function verifyReset(page, failures) {
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  if (await page.locator('label.field:has-text("Age") input').inputValue()) failures.push("reset_age_not_empty");
  if (await page.locator('label.field:has-text("State / UT") select').inputValue()) failures.push("reset_state_not_empty");
  if (await page.locator('label.field:has-text("Gender") select').inputValue()) failures.push("reset_gender_not_empty");
  await page.getByRole("button", { name: /2\. Situation/ }).click();
  if (await page.locator('label.field:has-text("Student status") select').inputValue() !== "No") failures.push("reset_student_status_not_default");
  if (await page.locator('label.field:has-text("Farmer status") select').inputValue() !== "No") failures.push("reset_farmer_status_not_default");
  if (await page.locator('label.field:has-text("Disability") select').inputValue() !== "No") failures.push("reset_disability_not_default");
  await page.getByRole("button", { name: /3\. Descriptors/ }).click();
  if (await page.locator("button.choice.active").count()) failures.push("reset_descriptors_not_empty");
  await page.getByRole("button", { name: /4\. Goal/ }).click();
  if (await page.locator('label.field:has-text("Annual household income") input').inputValue()) failures.push("reset_income_not_empty");
}

async function verifyClarify(page, location, failures) {
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  const ask = page.locator("#ask textarea");
  await ask.fill(`I am a 21 year old B.Tech student from ${location} seeking education support.`);
  const analyze = page.getByRole("button", { name: "Analyze Situation", exact: true });
  if (await analyze.isDisabled()) failures.push("ask_ai_button_visually_disabled_after_text");
  const responsePromise = page.waitForResponse((response) => response.url().endsWith("/clarify") && response.request().method() === "POST", { timeout: 120000 });
  await analyze.click();
  const response = await responsePromise;
  const body = await response.json().catch(() => null);
  if (response.status() !== 200) failures.push(`clarify_http_${response.status()}`);
  else if (!body?.profile || body.profile.state !== location || body.profile.age !== 21) failures.push("clarify_profile_does_not_match_text");
  else if (body.profile.gender !== null || body.profile.category !== null) failures.push("clarify_treated_unknown_as_known");
  else if (!(body.missing_questions || []).some((item) => item.field === "category")) failures.push("clarify_did_not_report_missing_information");
}

const requestedLocations = process.env.QA_LOCATIONS
  ? locations.filter((location) => process.env.QA_LOCATIONS.split(",").map((item) => item.trim()).includes(location))
  : locations;
if (!requestedLocations.length) throw new Error("QA_LOCATIONS did not match a supported state or union territory.");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.setDefaultTimeout(120000);
const requestCounter = { count: 0 };
page.on("request", (request) => {
  if (request.url().endsWith("/recommend") && request.method() === "POST") requestCounter.count += 1;
});
const rows = [];
for (let index = 0; index < requestedLocations.length; index += 1) {
  const location = requestedLocations[index];
  const nextLocation = locations[(locations.indexOf(location) + 1) % locations.length];
  const failures = [];
  const warnings = [];
  const started = Date.now();
  let primary = null;
  try {
    await page.goto(appUrl, { waitUntil: "networkidle" });
    await configureProfile(page, location);
    primary = await submitAndCapture(page, location, "primary", requestCounter);
    if (primary.status !== 200) failures.push(`recommend_http_${primary.status}`);
    if (primary.requestCount !== 1) failures.push(`duplicate_recommend_requests:${primary.requestCount}`);
    assertPayload(primary.payload, location, failures);
    const responseValidation = validateResponse(primary.body, location);
    failures.push(...responseValidation.failures);
    if (primary.body?.journey?.profile?.state !== location) failures.push("backend_returned_profile_state_mismatch");
    warnings.push(...responseValidation.warnings);

    await page.getByRole("button", { name: /1\. You/ }).click();
    await select(page, "State / UT", nextLocation);
    await page.getByRole("button", { name: /4\. Goal/ }).click();
    const changed = await submitAndCapture(page, nextLocation, "state-change", requestCounter);
    if (changed.status !== 200) failures.push(`state_change_http_${changed.status}`);
    if (changed.requestCount !== 1) failures.push(`duplicate_state_change_recommend_requests:${changed.requestCount}`);
    assertPayload(changed.payload, nextLocation, failures, "state_change_");
    if (changed.payload.state === location) failures.push("previous_state_leaked_after_state_change");

    await verifyReset(page, failures);
    await verifyClarify(page, location, failures);
  } catch (error) {
    failures.push(`browser_error:${error.message}`);
  }
  rows.push({
    location, profile: "T02", http_status: primary?.status ?? 0,
    schemes: primary?.body?.recommendations?.length ?? 0,
    official_sources: (primary?.body?.recommendations || []).filter((scheme) => scheme.source_verification?.is_official_government_source).length,
    latency_seconds: Number(((Date.now() - started) / 1000).toFixed(2)),
    status: failures.length ? "FAIL" : "PASS", failures: [...new Set(failures)], warnings: [...new Set(warnings)],
  });
  console.log(`[${index + 1}/${requestedLocations.length}] ${location}: ${rows.at(-1).status}`, rows.at(-1).failures.join("; "));
}
await browser.close();
fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(path.join(outputDir, "frontend_qa_results.json"), JSON.stringify(rows, null, 2));
const csv = ["Location,Profile,Status,Schemes,Official Sources,Eligibility Issues,Latency", ...rows.map((row) => [row.location, row.profile, row.status, row.schemes, row.official_sources, row.failures.filter((issue) => issue.includes("eligibility")).join(" | "), row.latency_seconds].map((field) => `"${String(field).replaceAll('"', '""')}"`).join(","))];
fs.writeFileSync(path.join(outputDir, "frontend_qa_table.csv"), `${csv.join("\n")}\n`);
const failed = rows.filter((row) => row.status === "FAIL");
fs.writeFileSync(path.join(outputDir, "frontend_qa_summary.md"), `# Live Frontend QA Summary\n\n- Total tests: ${rows.length}\n- Passed: ${rows.length - failed.length}\n- Failed: ${failed.length}\n- UI/network payload mismatches: ${rows.flatMap((row) => row.failures).filter((issue) => issue.includes("payload_mismatch") || issue.includes("leaked")).length}\n\n## Failed cases\n${failed.length ? failed.map((row) => `- ${row.location}: ${row.failures.join("; ")}`).join("\n") : "- None"}\n`);
process.exitCode = failed.length ? 1 : 0;
