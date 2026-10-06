import json, collections, sys
d = json.load(open('qa/nationwide/backend/live_qa_results.json', encoding='utf-8'))
rows = d['rows']
done = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    key = 'PASS' if r['outcome'] == 'PASS' else ('NO_MATCH' if r['outcome'] == 'NO_RELEVANT_SCHEMES_FOUND' else 'FAIL')
    done[r['location']][key] += 1
for loc in sorted(done):
    c = done[loc]
    total = sum(c.values())
    print(f"{loc}: {total} done | PASS {c['PASS']} | NO_MATCH {c['NO_MATCH']} | FAIL {c['FAIL']}")
print('\nTotal rows:', len(rows))
