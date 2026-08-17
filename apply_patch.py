import csv, json

# Load the corrected JSON (the one we just saved)
JSON_IN = 'questions_corrected_final.json'
JSON_OUT = 'questions_fully_patched.json'

with open(JSON_IN, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Read the edited review CSV
with open('full_review.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        qid = int(row['id'])
        for q in data:
            if q['id'] == qid:
                # Apply field overrides if present and non-empty
                for field in ['paper', 'subject', 'group', 'english_transcription', 'nepali_transcription']:
                    new_val = row.get('new_' + field, '').strip()
                    if new_val:
                        q[field] = new_val
                break

with open(JSON_OUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"[✓] Patched JSON saved as {JSON_OUT}")
