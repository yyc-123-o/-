"""验证问卷 → 上传 → 诊断全链路（新五维自评结构）"""
import urllib.request, json

# 1. 问卷提交（五维自评结构）
payload = json.dumps({
    'name': '李四',
    'education': {'level': '本科', 'major': '计算机科学与技术', 'institution': '某大学', 'gpa': 3.5},
    'self_assessment': {
        'learning_goal': '系统掌握深度学习',
        'weekly_hours': 10,
        'domain_assessments': [
            {'domain': '数学基础', 'note': '数学还行', 'courses': [
                {'name': '高等数学', 'level': '基础', 'note': ''},
                {'name': '线性代数', 'level': '熟练', 'note': ''},
                {'name': '概率论与数理统计', 'level': '基础', 'note': ''},
                {'name': '最优化方法', 'level': '未学过', 'note': ''},
            ]},
            {'domain': '机器学习基础', 'note': '', 'courses': [
                {'name': '机器学习', 'level': '基础', 'note': ''},
                {'name': '数据结构与算法', 'level': '熟练', 'note': ''},
            ]},
            {'domain': '深度学习', 'note': '刚开始学', 'courses': [
                {'name': '深度学习', 'level': '入门', 'note': ''},
                {'name': '计算机视觉', 'level': '未学过', 'note': ''},
                {'name': '自然语言处理', 'level': '未学过', 'note': ''},
            ]},
            {'domain': '优化算法', 'note': '', 'courses': [
                {'name': '最优化方法', 'level': '未学过', 'note': ''},
                {'name': '凸优化', 'level': '未学过', 'note': ''},
            ]},
            {'domain': '实践应用', 'note': '会Python', 'courses': [
                {'name': 'Python编程', 'level': '熟练', 'note': ''},
                {'name': '数据处理与特征工程', 'level': '基础', 'note': ''},
                {'name': '模型调参与部署', 'level': '未学过', 'note': ''},
            ]},
        ],
        'projects': [{'name': '图像分类', 'role': '独立完成', 'description': 'CNN', 'tech_stack': ['PyTorch'], 'duration_months': 2}],
    },
    'test_records': [],
    'interaction_records': [],
}).encode()
req = urllib.request.Request('http://localhost:8000/api/learner/upload', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
r = urllib.request.urlopen(req)
d = json.loads(r.read())
lid = d['learner_id']
print(f'1. 创建学习者: {lid}')

# 2. 诊断
req2 = urllib.request.Request(f'http://localhost:8000/api/learner/{lid}/diagnose?chapter_id=ch03_cnn', data=b'', method='POST')
r2 = urllib.request.urlopen(req2)
d2 = json.loads(r2.read())
p = d2['profile']
print('2. 诊断成功')

# 3. 验证画像中的问卷相关字段
li = p['learner']
sa = li['self_assessment']
print('3. 画像 learner 字段:')
print('   name:', li['name'])
print('   domain_assessments:', len(li.get('domain_assessments', [])), '个领域')
print('   projects:', len(li.get('projects', [])))
print('   self_assessment keys:', list(sa.keys()))
print('   framework_level (编程能力):', p['learning_preferences']['format']['framework_level'])
print('   confidence_note:', p['learning_preferences']['format']['confidence_note'][:60])
# 验证 evidence 中的五维自评
for e in p['evidence']:
    if '五维领域自评' in e['claim']:
        print('   证据-五维自评:', e['claim'][:80])
print('=== QUESTIONNAIRE FLOW SUCCESS ===')
