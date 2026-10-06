from pathlib import Path
p = Path('api/main.py')
s = p.read_text(encoding='utf-8')
old1 = '                "message": classified["message"],\n            },\n        )\n    if isinstance(exc, ValueError):'
new1 = '                "message": classified["message"],\n                "category": classified.get("category"),\n            },\n        )\n    if isinstance(exc, ValueError):'
assert old1 in s
s = s.replace(old1, new1)
old2 = '                    "message": classified["message"],\n                    "fallback_used": False,'
new2 = '                    "message": classified["message"],\n                    "category": classified.get("category"),\n                    "fallback_used": False,'
assert old2 in s
s = s.replace(old2, new2)
p.write_text(s, encoding='utf-8')
print('ok')
