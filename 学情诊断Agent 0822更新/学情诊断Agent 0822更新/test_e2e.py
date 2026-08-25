import urllib.request, json, random

# 1. Create learner via questionnaire
payload = json.dumps({
    'name': 'Test User', 'education': {'level': '本科', 'major': 'CS'},
    'self_assessment': {'ml_level': 'entry', 'dl_level': 'zero', 'math_level': 'ok', 'learning_goal': 'learn CNN', 'weekly_hours': 8},
    'test_records': [], 'interaction_records': []
}).encode()
req = urllib.request.Request('http://localhost:8000/api/learner/upload', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
r = urllib.request.urlopen(req)
d = json.loads(r.read())
lid = d['learner_id']
print(f'1. Created learner: {lid}')

# 2. Start adaptive test
req2 = urllib.request.Request(f'http://localhost:8000/api/adaptive-test/start/{lid}', data=b'', method='POST')
r2 = urllib.request.urlopen(req2)
d2 = json.loads(r2.read())
sid = d2['session_id']
qid = d2['next_question']['question_id']
print(f'2. Started session: {sid}, first q: {qid}')

# 3. Answer until finished
for i in range(30):
    correct = random.random() > 0.4
    ans = json.dumps({'session_id': sid, 'question_id': qid, 'is_correct': correct, 'time_spent': 45}).encode()
    req3 = urllib.request.Request('http://localhost:8000/api/adaptive-test/answer', data=ans, headers={'Content-Type': 'application/json'}, method='POST')
    r3 = urllib.request.urlopen(req3)
    d3 = json.loads(r3.read())
    if d3.get('finished'):
        print(f'3. Test finished after {d3["question_count"]} questions: {d3["stop_reason"]}')
        break
    elif d3.get('next_question'):
        qid = d3['next_question']['question_id']

# 4. Apply answers to learner
req4 = urllib.request.Request(f'http://localhost:8000/api/adaptive-test/apply/{lid}?session_id={sid}', data=b'', method='POST')
r4 = urllib.request.urlopen(req4)
d4 = json.loads(r4.read())
print(f'4. Applied: {d4["message"]}')

# 5. Diagnose
req5 = urllib.request.Request(f'http://localhost:8000/api/learner/{lid}/diagnose?chapter_id=ch03_cnn', data=b'', method='POST')
r5 = urllib.request.urlopen(req5)
d5 = json.loads(r5.read())
p = d5['profile']
print(f'5. Diagnosis OK: theta={p["knowledge_mastery"]["global_theta"]}, gaps={len(p["knowledge_gaps"])}, tests={p["meta"]["total_test_count"]}')
print('=== FULL FLOW: SUCCESS ===')
