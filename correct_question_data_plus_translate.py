#!/usr/bin/env python3
"""
Corrected script – properly sets action='MANUAL' when translations fail.
"""

import json, re, os, csv, time, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- Translator setup ----------
TRANSLATOR_AVAILABLE = False
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None
try:
    from googletrans import Translator as GoogleTrans
except ImportError:
    GoogleTrans = None
try:
    from deep_translator import BingTranslator
except ImportError:
    BingTranslator = None

if any([GoogleTranslator, GoogleTrans, BingTranslator]):
    TRANSLATOR_AVAILABLE = True
else:
    print("[!] No translation backends. Run: pip install deep-translator googletrans==4.0.0-rc1")

class TranslationError(Exception):
    pass

def translate_text(text, target='ne', source='en', max_retries=3):
    if not TRANSLATOR_AVAILABLE or not text or len(text.strip()) < 2:
        return text
    clean_text = re.sub(r'<[^>]+>', ' ', text)
    clean_text = clean_text.replace('\n', ' ').replace('\r', ' ')
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    if len(clean_text) < 2:
        return text

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500,502,503,504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.headers.update({'User-Agent': 'Mozilla/5.0'})

    backends = []
    if GoogleTranslator:
        backends.append(('GoogleTranslator', GoogleTranslator))
    if GoogleTrans:
        backends.append(('googletrans', GoogleTrans))
    if BingTranslator:
        backends.append(('BingTranslator', BingTranslator))

    for attempt in range(max_retries):
        for name, TranslatorClass in backends:
            try:
                if name == 'GoogleTranslator':
                    translator = TranslatorClass(source=source, target=target)
                    translator.session = session
                    result = translator.translate(clean_text)
                elif name == 'googletrans':
                    translator = TranslatorClass()
                    result = translator.translate(clean_text, src=source, dest=target).text
                else:
                    translator = TranslatorClass(source=source, target=target)
                    result = translator.translate(clean_text)
                if result and len(result.strip()) > 1:
                    return result
            except Exception as e:
                print(f"    [!] {name} failed (attempt {attempt+1}): {str(e)[:80]}")
                time.sleep(1.5)
                continue
    raise TranslationError(f"All translators failed for: {clean_text[:60]}...")

# ---------- Language detection (unchanged) ----------
DEVANAGARI = re.compile(r'[\u0900-\u097F]')
LATIN = re.compile(r'[a-zA-Z]')

def script_ratio(text):
    if not text:
        return 0, 0, 0
    dev = len(DEVANAGARI.findall(text))
    lat = len(LATIN.findall(text))
    return dev, lat, len(text)

def detect_script(text):
    if not text:
        return None
    dev, lat, total = script_ratio(text)
    if total == 0:
        return None
    dev_ratio = dev / total
    lat_ratio = lat / total
    if dev_ratio > 0.8 and lat_ratio < 0.1:
        return 'ne'
    if lat_ratio > 0.8 and dev_ratio < 0.1:
        return 'en'
    return 'mixed'

# ---------- Syllabus mapping (unchanged) ----------
PAPER_MAP = {
    'P1': 'paper_i', 'P2': 'paper_ii', 'P3': 'paper_iii'
}
SUBJECT_MAP = {
    ('P1','A1'): 'Microeconomics', ('P1','A2'): 'Development Economics',
    ('P1','A3'): 'Public Economics', ('P1','B4'): 'Macroeconomics',
    ('P1','B5'): 'Monetary Economics', ('P1','B6'): 'International Economics',
    ('P2','A1'): 'General Management', ('P2','A2'): 'Human Resource Development',
    ('P2','B3'): 'Financial Economics', ('P2','B4'): 'Managerial Economics',
    ('P3','A1'): 'Research Methodology', ('P3','B2'): 'Information and Communication Technology',
    ('P3','C3'): 'Banking Laws and Regulations',
}
GROUP_MAP = {
    ('P1','A'): 'A', ('P1','B'): 'B',
    ('P2','A'): 'A', ('P2','B'): 'B',
    ('P3','A'): 'A', ('P3','B'): 'B', ('P3','C'): 'C',
}

def extract_syllabus_code(chapter):
    if not chapter:
        return None
    match = re.search(r'(P\d+[-_][A-Z]\d+(?:\.\d+)?)', chapter)
    return match.group(1) if match else None

def derive_values(code):
    if not code:
        return None, None, None
    parts = code.split('-') if '-' in code else code.split('_')
    if len(parts) != 2:
        return None, None, None
    paper, rest = parts
    topic = rest[:2]
    section = rest[0]
    return PAPER_MAP.get(paper), SUBJECT_MAP.get((paper, topic)), GROUP_MAP.get((paper, section))

# ---------- Main correction function ----------
def correct_question_file(input_file, output_file, translate=True, verbose=True):
    if not os.path.exists(input_file):
        print(f"[!] Input file not found: {input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    corrected = []
    review = []
    stats = {'paper':0, 'subject':0, 'group':0, 'translated':0, 'manual':0}
    total = len(data)

    for idx, q in enumerate(data, 1):
        progress = f"  [{idx:3d}/{total}]"
        print(f"\r{progress} Q{q.get('question_no','?')}", end='')

        orig_paper = q.get('paper', '')
        orig_subject = q.get('subject', '')
        orig_group = q.get('group', '')
        orig_eng = q.get('english_transcription', '').strip()
        orig_nep = q.get('nepali_transcription', '').strip()

        # Syllabus fixes
        code = extract_syllabus_code(q.get('chapter', ''))
        changes = []
        if code:
            new_paper, new_subject, new_group = derive_values(code)
            if new_paper and new_paper != orig_paper:
                q['paper'] = new_paper
                changes.append(f"paper: {orig_paper} → {new_paper}")
                stats['paper'] += 1
            if new_subject and new_subject != orig_subject:
                q['subject'] = new_subject
                changes.append(f"subject: {orig_subject} → {new_subject}")
                stats['subject'] += 1
            if new_group and new_group != orig_group:
                q['group'] = new_group
                changes.append(f"group: {orig_group} → {new_group}")
                stats['group'] += 1
            q['syllabus_code'] = code

        # --- Translation logic with proper MANUAL setting ---
        nep = q.get('nepali_transcription', '').strip()
        eng = q.get('english_transcription', '').strip()
        action = 'KEPT'
        reason = 'No change'

        nep_script = detect_script(nep)
        eng_script = detect_script(eng)

        if not nep and not eng:
            action = 'KEPT'
            reason = 'Both empty'

        elif not nep and eng:
            # English present, Nepali missing
            if translate and TRANSLATOR_AVAILABLE:
                try:
                    nep = translate_text(eng, target='ne')
                    action = 'TRANSLATED'
                    reason = 'English → Nepali (fallback)'
                    stats['translated'] += 1
                except TranslationError as e:
                    action = 'MANUAL'
                    reason = str(e)
                    stats['manual'] += 1
            else:
                action = 'MANUAL'
                reason = 'Nepali empty, English present but translation disabled'
                stats['manual'] += 1

        elif not eng and nep:
            # Nepali present, English missing
            if translate and TRANSLATOR_AVAILABLE:
                try:
                    eng = translate_text(nep, source='ne', target='en')
                    action = 'TRANSLATED'
                    reason = 'Nepali → English (fallback)'
                    stats['translated'] += 1
                except TranslationError as e:
                    action = 'MANUAL'
                    reason = str(e)
                    stats['manual'] += 1
            else:
                action = 'MANUAL'
                reason = 'English empty, Nepali present but translation disabled'
                stats['manual'] += 1

        elif nep and eng and nep == eng:
            # Identical
            if nep_script == 'ne':
                if translate and TRANSLATOR_AVAILABLE:
                    try:
                        eng = translate_text(nep, source='ne', target='en')
                        action = 'TRANSLATED'
                        reason = 'Both same (Nepali) → English (fallback)'
                        stats['translated'] += 1
                    except TranslationError as e:
                        action = 'MANUAL'
                        reason = str(e)
                        stats['manual'] += 1
                else:
                    action = 'MANUAL'
                    reason = 'Both same Nepali, translation disabled'
                    stats['manual'] += 1
            elif nep_script == 'en':
                if translate and TRANSLATOR_AVAILABLE:
                    try:
                        nep = translate_text(eng, target='ne')
                        action = 'TRANSLATED'
                        reason = 'Both same (English) → Nepali (fallback)'
                        stats['translated'] += 1
                    except TranslationError as e:
                        action = 'MANUAL'
                        reason = str(e)
                        stats['manual'] += 1
                else:
                    action = 'MANUAL'
                    reason = 'Both same English, translation disabled'
                    stats['manual'] += 1
            else:
                action = 'MANUAL'
                reason = 'Identical but mixed script – manual needed'
                stats['manual'] += 1

        else:
            # Both non-empty and different
            action = 'KEPT'
            reason = 'Both fields differ – no automatic move'

        # Apply changes
        if action not in ('KEPT', 'MANUAL'):
            q['nepali_transcription'] = nep
            q['english_transcription'] = eng
            changes.append(f"translation: {action} ({reason})")

        # Record review if any change occurred
        if changes:
            review.append({
                'id': q.get('id'),
                'question_no': q.get('question_no'),
                'syllabus_code': q.get('syllabus_code'),
                'old_paper': orig_paper,
                'new_paper': q.get('paper', ''),
                'old_subject': orig_subject,
                'new_subject': q.get('subject', ''),
                'old_group': orig_group,
                'new_group': q.get('group', ''),
                'old_english': orig_eng,
                'new_english': q.get('english_transcription', ''),
                'old_nepali': orig_nep,
                'new_nepali': q.get('nepali_transcription', ''),
                'action': action,
                'reason': reason,
            })

        corrected.append(q)

    print()

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(corrected, f, indent=2, ensure_ascii=False)

    if review:
        fieldnames = ['id','question_no','syllabus_code',
                      'old_paper','new_paper',
                      'old_subject','new_subject',
                      'old_group','new_group',
                      'old_english','new_english',
                      'old_nepali','new_nepali',
                      'action','reason']
        with open('full_review.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(review)
        print(f"\n[✓] Full review CSV generated: full_review.csv ({len(review)} rows)")

    print("\n" + "═" * 70)
    print("  📊 SUMMARY")
    print("═" * 70)
    print(f"  📁 Output file       : {output_file}")
    print(f"  📝 Total questions   : {total}")
    print(f"  🔄 Paper fixes       : {stats['paper']}")
    print(f"  🔄 Subject fixes     : {stats['subject']}")
    print(f"  🔄 Group fixes       : {stats['group']}")
    print(f"  🌐 Translations      : {stats['translated']}")
    print(f"  ⚠️  Manual needed    : {stats['manual']}")
    print("═" * 70)

    if stats['manual'] > 0:
        print("\n💡 Manual entries found. Edit full_review.csv and use the patch script to apply fixes.")

if __name__ == "__main__":
    print("\n" + "═" * 70)
    print("  📚 FIXED QUESTION BANK CORRECTOR (proper MANUAL tagging)")
    print("═" * 70)
    input_json = input("Enter JSON file path (default: questions_export_20260816_184738.json): ").strip()
    if not input_json:
        input_json = "questions_export_20260816_184738.json"
    output_json = input("Enter output path (default: questions_corrected_final.json): ").strip()
    if not output_json:
        output_json = "questions_corrected_final.json"
    do_translate = input("Auto-translate missing fields? (y/n, default y): ").strip().lower() != 'n'
    correct_question_file(input_json, output_json, translate=do_translate)
