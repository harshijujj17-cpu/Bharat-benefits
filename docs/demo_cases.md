# Demo Cases — Bharat Benefit Navigator

Curated set of demo profiles for live presentation testing.

## Keep (6)

| # | State | Need | Citizen Profile |
|---|---|---|---|
| 1 | Telangana | Education | Female, student, OBC, UG, income ₹2,00,000 |
| 2 | Telangana | Agriculture | Male, farmer, General, secondary, income ₹2,50,000 |
| 3 | Andhra Pradesh | Agriculture | Male, farmer, OBC, secondary, income ₹2,00,000 |
| 5 | Kerala | Women & Children | Female, homemaker, General, secondary, income ₹1,50,000 |
| 6 | Kerala | Senior Citizens | Male, retired, General, secondary, income ₹1,20,000 |
| 10 | Odisha | Disability | Male, unemployed, SC, secondary, disabled = Yes |

## Pruned (4)

- 4 — Andhra Pradesh Education → too similar to Telangana Education
- 7 — Karnataka Employment & Business → lower priority for presentation
- 8 — Maharashtra Women & Children → duplicates Kerala category
- 9 — Rajasthan Agriculture → duplicates agriculture pattern

## Presentation order (priority 3)

1. **Telangana + Education** — strongest, previously validated live flow
2. **Andhra Pradesh + Agriculture** — proves state-aware results
3. **Kerala + Women & Children** — proves different welfare domain

## Usage

1. Run `python qa/provider_smoke.py` — all four checks must be `yes`.
2. Wake the backend: open `/health`.
3. Open the deployed frontend, pick the state/need, fill the profile, and wait ~30s for live retrieval.
