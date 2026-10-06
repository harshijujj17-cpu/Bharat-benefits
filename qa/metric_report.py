import json, glob, collections, statistics

rows = []
for p in sorted(glob.glob('qa/full-results/backend-*/live_qa_results.json')):
    rows += json.load(open(p, encoding='utf-8'))['rows']
front = []
for p in glob.glob('qa/full-results/frontend-*/frontend_qa_results.json'):
    front += json.load(open(p, encoding='utf-8'))
smoke_front = json.load(open('qa/smoke-results/frontend_qa_results.json', encoding='utf-8'))

fails = [f for r in rows for f in r.get('failures', [])]
warns = [w for r in rows for w in r.get('warnings', [])]
ffails = [f for r in front + smoke_front for f in r.get('failures', [])]

http_prov = [f for f in fails + ffails if f.startswith(('http_', 'network', 'tavily', 'gemini')) or 'provider' in f.lower()]
wrong_state = [f for f in fails + ffails if 'wrong_state' in f or 'state_mismatch' in f or 'state_leaked' in f]
elig_rows = [r for r in rows if r.get('eligibility_issues')]
elig_issues = [i for r in rows for i in r.get('eligibility_issues', [])]
unground = [f for f in fails + ffails + warns if 'ungrounded' in f or 'non_government' in f or 'source_url_not_grounded' in f]
fw_mismatch = [f for f in ffails if 'payload_mismatch' in f]
norel = [r for r in rows if r.get('outcome') == 'NO_RELEVANT_SCHEMES_FOUND']
dup = [f for f in fails + ffails if 'duplicate' in f]
lat = [r['latency_seconds'] for r in rows if isinstance(r.get('latency_seconds'), (int, float))]

print('backend rows:', len(rows), '| frontend rows:', len(front), '| smoke frontend rows:', len(smoke_front))
print('HTTP/provider failures:', len(http_prov), dict(collections.Counter(f.split(':')[0] for f in http_prov)))
print('Wrong-state recommendations:', len(wrong_state), dict(collections.Counter(f.split(':')[0] for f in wrong_state)))
print('Eligibility mismatch rows:', len(elig_rows), '| tags:', len(elig_issues), dict(collections.Counter(i.split(':')[0] for i in elig_issues).most_common(5)))
print('Ungrounded/non-government:', len(unground), dict(collections.Counter(f.split(':')[0] for f in unground)))
print('FE->BE payload mismatches:', len(fw_mismatch), dict(collections.Counter(f.split(':')[0] for f in fw_mismatch)))
print('NO_RELEVANT_SCHEMES_FOUND:', len(norel))
print('Duplicate pipeline calls:', len(dup), dict(collections.Counter(f.split(':')[0] for f in dup)))
if lat:
    s = sorted(lat)
    print(f"Latency: avg {statistics.mean(lat):.2f}s p95 {s[int(0.95*(len(s)-1))]:.2f}s (n={len(lat)})")
print('State/UT breakdown:', dict(collections.Counter(r['location'] for r in rows)))
