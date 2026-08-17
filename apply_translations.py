import json

translations = {
    517: "फ्रिज प्यान भनेको के हो? तपाईं स्प्रेडसिट फाइलमा फ्रिज प्यानहरू कसरी लागू गर्नुहुन्छ?",
    536: '"कुनै पनि संगठन राम्रो वा नराम्रो हुँदैन। यो संगठनको नेताले नै यसलाई त्यस्तो बनाउँछ।" संक्षिप्त चर्चा गर्नुहोस्।',
    548: "पुँजीको लागत के हो? के तपाईं इक्विटी पूँजी लागतरहित छ भन्ने कुरामा सहमत हुनुहुन्छ? यसलाई औचित्य दिनुहोस्।",
    553: "नेपालको बाह्रौं आवधिक योजना (२०६७/६८ देखि २०६९/७०) का प्राप्त उपलब्धिहरूको मूल्याङ्कन गर्नुहोस्।",
    587: "मेल मर्ज भनेको के हो, र यसलाई कहाँ लागू गर्नुहुन्छ? पासवर्ड प्रयोग गरेर आफ्नो कागजात सुरक्षित गर्न चरणहरू सूचीबद्ध गर्नुहोस्।",
    606: "लामो अवधिको औसत लागत वक्र 'U' आकारको सट्टा 'L' आकारको किन हुन्छ? छलफल गर्नुहोस्।",
    608: "(i) वस्तु र सेवाहरू, (ii) श्रम, (iii) पुँजी, (iv) उद्यमशीलता र (v) विदेशी विनिमयको मूल्यहरू एकअर्कासँग कसरी अन्तरक्रिया गर्छन्? तिनीहरूको अन्तरसम्बन्ध देखाउनुहोस्।",
    684: "नेपाल राष्ट्र बैंकले आर्थिक वर्ष २०१०-११ को लागि घोषणा गरेको नयाँ मौद्रिक नीतिका मुख्य विशेषताहरूको गणना गर्नुहोस् र यसको सफल कार्यान्वयनको सम्भावनाहरू पनि जाँच गर्नुहोस्।",
    695: '"उपभोक्ताको सन्तुलन" भन्नाले के बुझिन्छ? (क) त्यस वस्तुको मूल्य बढ्यो, (ख) उपभोक्ताको आम्दानी घट्यो र (ग) विकल्प वस्तुको मूल्य घट्यो भने कुनै विशेष वस्तुको सन्दर्भमा उपभोक्ताको सन्तुलन कसरी प्रभावित हुन्छ? उत्तरको लागि उदासीनता वक्र प्रविधि प्रयोग गर्नुहोस्।',
    707: "यसमा छोटो टिप्पणी लेख्नुहोस्: <br>क. अस्थायी विनिमय दर <br>ख. व्यवस्थित विनिमय दर <br>ग. स्थिर विनिमय दर",
    744: "MS Excel मा डेटा क्रमबद्ध गर्नु र फिल्टर गर्नु बीच के भिन्नता छ? स्तम्भ र मानहरूद्वारा डेटा कसरी सम्भव छ र यदि छ भने कसरी?",
    746: "यदि तपाईंसँग Microsoft Office 2007 छ र तपाईंको साथीसँग Microsoft Office 2003 छ भने Office को विभिन्न संस्करणहरूद्वारा सिर्जना गरिएका कागजातहरू कसरी आदान-प्रदान गर्न र प्रयोग गर्न सम्भव छ? Microsoft Office को दुई संस्करणहरूद्वारा सिर्जना गरिएको फाइललाई तपाईं कसरी पहिचान गर्न सक्नुहुन्छ?",
}

# Convert keys to both int and str for flexibility
trans_keys_int = set(translations.keys())
trans_keys_str = {str(k) for k in translations.keys()}

with open('questions_corrected_final.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

updated = 0
for q in data:
    qid = q['id']
    # Try matching as int if possible, else as string
    if isinstance(qid, int) and qid in trans_keys_int:
        q['nepali_transcription'] = translations[qid]
        updated += 1
        print(f"✅ Updated ID {qid} (Q{q['question_no']})")
    elif isinstance(qid, str) and qid in trans_keys_str:
        q['nepali_transcription'] = translations[int(qid)]
        updated += 1
        print(f"✅ Updated ID {qid} (Q{q['question_no']})")

if updated == 0:
    print("⚠️ No matching IDs found. Check that the IDs in the JSON match the ones in the script.")
    print(f"First few IDs in JSON: {[q['id'] for q in data[:5]]}")
else:
    with open('questions_fully_patched.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Patched {updated} questions. Saved as questions_fully_patched.json")
