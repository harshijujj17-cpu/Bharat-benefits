import json, glob, collections

rows = []
for p in sorted(glob.glob('qa/full-results/backend-*/live_qa_results.json')):
    batch = p.split('\\')[-2] if '\\' in p else p.split('/')[-2]
    for r in json.load(open(p, encoding='utf-8'))['rows']:
        r['_batch'] = batch
        rows.append(r)

norel = [r for r in rows if r.get('outcome') == 'NO_RELEVANT_SCHEMES_FOUND']
print('NO_RELEVANT_SCHEMES_FOUND total:', len(norel))
print('\nBy state:')
print(dict(collections.Counter(r['location'] for r in norel)))
print('\nBy batch:')
print(dict(collections.Counter(r['_batch'] for r in norel)))
print('\nBy profile:')
print(dict(collections.Counter(r['profile'] for r in norel)))
print('\nBy retrieval mode/result_count/official_count:')
print(collections.Counter((r.get('retrieval', {}) or {}).get('mode') for r in norel))
print(collections.Counter((r.get('retrieval', {}) or {}).get('result_count') for r in norel))
print(collections.Counter((r.get('retrieval', {}) or {}).get('official_result_count') for r in norel))
print('\nLatency stats:')
lat = sorted(r['latency_seconds'] for r in norel)
print('min/med/max:', lat[0], lat[len(lat)//2], lat[-1])
print('\nGenerated query sample (first case):')
print(json.dumps(norel[0]['generated_queries'], indent=1)[:600])
print('\nCases with nonzero retrieval result_count (retrieval found something but none passed filters?):')
odd = [r for r in norel if (r.get('retrieval') or {}).get('result_count', 0) > 0]
print('count:', len(odd))
for r in odd[:10]:
    rt = r['retrieval']
    print(f"  {r['_batch']} {r['location']} {r['profile']}: results={rt.get('result_count')} official={rt.get('official_result_count')} http={r['http_status']}")
