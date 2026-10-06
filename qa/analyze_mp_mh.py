import json
from collections import Counter

d = json.load(open('qa/full-results/backend-07/live_qa_results.json', encoding='utf-8'))
targets_mp = {'T02','T03','T04','T08','T09','T10','E01','E02'}
targets_mh = {f'T{i:02d}' for i in range(1,13)} | {'E01','E02','E03'}

for r in d['rows']:
    loc, prof = r['location'], r['profile']
    if not ((loc=='Madhya Pradesh' and prof in targets_mp) or (loc=='Maharashtra' and prof in targets_mh)):
        continue
    print(f"\n=== {loc} {prof} | HTTP {r['http_status']} | outcome {r['outcome']} | latency {r['latency_seconds']}s ===")
    print(f"  provider_error: {r.get('provider_error')}")
    print(f"  network_error: {r.get('network_error')}")
    print(f"  failures: {r['failures'][:6]}{'...' if len(r['failures'])>6 else ''}")
    print(f"  warnings: {r['warnings']}")
    print(f"  retrieval: {(r.get('retrieval') or {}).get('mode')}/{(r.get('retrieval') or {}).get('provider')} results={len((r.get('retrieval') or {}).get('source_urls', []) or []) if r.get('retrieval') else None}")
    print(f"  schemes: {r['scheme_count']}, official: {r['official_source_count']}")
    print(f"  eligibility_counts: {r['eligibility_counts']}")
    print(f"  eligibility_issues: {r['eligibility_issues']}")
    # any success rows with grounding info
    if r['schemes']:
        s = r['schemes'][0]
        print(f"  first scheme official={s['official']} domain={s['domain']} scope={s['scope']} elig_class={s['eligibility_class']}")
        print(f"  missing_information present: {bool(s.get('missing_information'))}")

# MP T02 warning detail
for r in d['rows']:
    if r['location']=='Madhya Pradesh' and r['profile']=='T02':
        print('\nMP T02 warnings raw:', r['warnings'])
        print('MP T02 eligibility_issues:', r['eligibility_issues'])
        for s in r['schemes']:
            print('  scheme:', s['name'][:60], '| missing_information:', bool(s.get('missing_information')), '| elig_status:', s.get('eligibility_status'))
# MP E01/E02 income mismatch detail
for r in d['rows']:
    if r['location']=='Madhya Pradesh' and r['profile'] in ('E01','E02'):
        print(f"\nMP {r['profile']} failures income-related:", [f for f in r['failures'] if 'income' in f])
        print('  payload annual_household_income_inr:', r['payload'].get('annual_household_income_inr'))
        print('  HTTP:', r['http_status'], '| provider_error:', r.get('provider_error'))
