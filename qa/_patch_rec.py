from pathlib import Path
p = Path('agent/recommendation.py')
lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
assert lines[195] == '\tif client is None:\n', lines[195]
assert lines[208] == '\t\tpurpose="eligibility",\n', lines[208]
assert lines[209] == '\t)\n', lines[209]
new = [
    '\tif client is not None:\n',
    '\t\tresponse = model_config.generate_with_fallback(\n',
    '\t\t\tclient,\n',
    '\t\t\tbuild_recommendation_prompt(profile, retrieved_schemes),\n',
    '\t\t\tconfig=types.GenerateContentConfig(\n',
    '\t\t\t\tsystem_instruction=SYSTEM_INSTRUCTION,\n',
    '\t\t\t\tresponse_mime_type="application/json",\n',
    '\t\t\t\tresponse_schema=RECOMMENDATION_RESPONSE_SCHEMA,\n',
    '\t\t\t\ttemperature=0.2,\n',
    '\t\t\t),\n',
    '\t\t\tmodel_name=model_name,\n',
    '\t\t\tpurpose="eligibility",\n',
    '\t\t)\n',
    '\telse:\n',
    '\t\tfrom agent import llm_client\n',
    '\n',
    '\t\tresponse = llm_client.generate(\n',
    '\t\t\tbuild_recommendation_prompt(profile, retrieved_schemes),\n',
    '\t\t\tsystem_instruction=SYSTEM_INSTRUCTION,\n',
    '\t\t\tresponse_schema=RECOMMENDATION_RESPONSE_SCHEMA,\n',
    '\t\t\ttemperature=0.2,\n',
    '\t\t\tmodel_name=model_name,\n',
    '\t\t\tpurpose="eligibility",\n',
    '\t\t)\n',
]
lines[195:210] = new
p.write_text(''.join(lines), encoding='utf-8')
print('ok')
