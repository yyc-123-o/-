# 学情诊断Agent 升级分析报告

> 生成日期：2026-07-27 | 分析人：系统分析 | 版本：v2.0

---

## 一、现有系统做了什么

现有 `学情诊断Agent` 是一个**基于IRT项目反应理论的学习者画像构建系统**，核心能力：

| 模块 | 功能 | 算法 |
|------|------|------|
| IRT引擎 | 从答题数据估计学习者能力θ | 2PL-MLE + L2正则先验收缩 |
| 掌握度计算 | 30个知识点的0~1掌握度 | mastery = P(θ\|b=difficulty) + 交互行为修正 |
| 盲区分析 | 4类知识盲区优先级排序 | blindspot/weak/blocked/difficult |
| 偏好推断 | 从行为数据推断学习偏好 | 统计推断（节奏/活跃度/提示依赖） |
| 数据生成 | 3类差异化模拟学习者 | IRT概率采样 |
| 可视化 | ECharts面板（雷达图+热力图+盲区表） | FastAPI + 纯JS前端 |

**技术栈**：FastAPI + Pydantic + NumPy + SciPy + ECharts

---

## 二、两份画像输出的关键差异

### 2.1 结构对比

| 画像维度 | 现有系统 (LearnerProfile) | 之前示例 (学情画像输出-示例.json) | 最终方案要求 |
|----------|--------------------------|-----------------------------------|-------------|
| 掌握度矩阵 | ✅ mastery_map (IRT) | ✅ mastery_score (简单分数) | ✅ 必需 |
| 能力等级 | ✅ global_theta + ability_level | ✅ level_code + 子维度 | ✅ 必需 |
| 错误模式分类 | ❌ 无 | ✅ 四分类+示例+涉及节点 | ✅ **Step 6 必需** |
| 深度层次标签 | ❌ 无 | ✅ 入门/进阶/专业 | ✅ **Step 1/2 必需** |
| 学习偏好 | ⚠️ 仅4项（难度/节奏/活跃度/提示依赖） | ✅ 13项（含语言/框架/动机/注意时长） | ⚠️ 需扩展 |
| 学习路径上下文 | ❌ 无 | ✅ current_kp + 前驱后继 | ✅ **Step 3 需要** |
| 章节追踪 | ❌ 无 | ✅ prior_chapter_performance | ✅ **Step 6 需要** |
| 资源生成提示 | ❌ 无 | ✅ 讲义/实操/测试的详细约束 | ✅ **Step 3 关键输出** |
| 证据溯源 | ❌ 无 | ✅ evidence_binding | ✅ **核心创新点3** |
| 盲区分析 | ✅ 4类+优先级+阻塞依赖 | ❌ 无分类 | ✅ 必需 |
| IRT统计量 | ✅ θ + discrimination + difficulty | ❌ 无 | ✅ 加分项 |

### 2.2 结论

现有系统在**IRT数学基础**上做得更好（这是它的核心优势），但缺少最终方案要求的**5个关键输出字段**：

1. 🔴 错误模式四分类
2. 🔴 知识点深度层次标签（入门/进阶/专业）
3. 🔴 资源生成提示（直接驱动资源生成Agent）
4. 🟡 学习路径上下文
5. 🟡 证据溯源记录

---

## 三、已执行的改进

### 3.1 schemas.py 升级（已完成）

文件 `models/schemas.py` 已升级到 v2.0，新增 6 个数据模型：

#### 新增模型

```python
ErrorPattern          # 错误模式：概念混淆/计算错误/逻辑跳跃/忽略条件
DepthLevel            # 深度标签：每个知识点的入门/进阶/专业 + 分配依据
ChapterPerformance    # 章节追踪：每章的准确率/时长/深度/错误模式
ResourceGenerationHints  # 资源生成提示：讲义/实操/测试的具体约束
EvidenceRecord        # 证据溯源：每条结论的来源+置信度
```

#### 扩展模型

```python
LearningPreferences   # 新增9个字段：编程语言/框架/动机/注意时长/视觉偏好...
TestRecord            # 新增 error_pattern 字段（错题时打标）
Learner               # 新增 self_assessment 字段（自填问卷结果）
LearnerProfile        # 新增10个字段（见下方）
```

#### LearnerProfile v2.0 完整字段列表

```
基础: learner_id, learner_name, education_summary
维度1: mastery_map, global_theta, ability_level, domain_mastery
维度2: sub_ability_scores (理论/编码/数学/解题子维度)
维度3: error_patterns, primary_weakness
维度4: learning_preferences (扩展版)
盲区: knowledge_gaps
深度: depth_labels (新增)
路径: current_chapter, current_kp_id, predecessor/successor_kp_ids (新增)
历史: prior_chapters (新增)
资源: resource_hints (新增)
证据: evidence_records (新增)
摘要: summary, accuracy_overall
元信息: total_test_count, total_interaction_count, diagnosed_at, profile_version
```

---

## 四、后续待办（按优先级）

### 🔴 P0 — 必须实现（直接决定资源生成Agent能否工作）

| # | 任务 | 涉及文件 | 工作量 |
|---|------|----------|--------|
| 1 | 在 `gap_analyzer.py` 中新增 `classify_error_patterns()` 函数，从答题记录中自动分类错误模式 | `core/gap_analyzer.py` | 中 |
| 2 | 在 `profile_builder.py` 中新增 `_assign_depth_levels()` 函数，根据掌握度自动分配深度标签 | `core/profile_builder.py` | 中 |
| 3 | 在 `profile_builder.py` 中新增 `_build_resource_hints()` 函数，生成资源生成Agent所需的完整提示 | `core/profile_builder.py` | 中 |
| 4 | 更新 `profile_builder.build_profile()` 的8步流程以填充所有v2.0新字段 | `core/profile_builder.py` | 中 |

### 🟡 P1 — 应该实现（提升画像质量和可审计性）

| # | 任务 | 涉及文件 | 工作量 |
|---|------|----------|--------|
| 5 | 在 `knowledge_graph.py` 的 `KnowledgePoint` 中新增 `depth_levels` 字段（3层标注） | `models/knowledge_graph.py` | 小 |
| 6 | 在 `mock_generator.py` 中新增章节级数据生成逻辑 | `generators/mock_generator.py` | 中 |
| 7 | 在 `profile_builder.py` 中新增 `_compute_sub_ability_scores()` | `core/profile_builder.py` | 小 |
| 8 | 前端 `index.html` 新增错误模式分布的饼图/柱状图 | `static/index.html` | 小 |

### 🟢 P2 — 锦上添花

| # | 任务 | 涉及文件 | 工作量 |
|---|------|----------|--------|
| 9 | 证据溯源记录自动生成 | `core/profile_builder.py` | 小 |
| 10 | 将自填问卷纳入学历先验的调节因子 | `core/irt.py` | 小 |

---

## 五、与资源生成Agent的接口约定

学情诊断Agent的输出 → 资源生成Agent的输入，关键对接字段：

```
LearnerProfile
  ├── mastery_map           → 决定哪些知识点需要生成资源
  ├── depth_labels          → 决定每个知识点的内容深浅
  ├── resource_hints        → 讲义/实操/测试的具体约束
  ├── knowledge_gaps        → 盲区知识需要额外加练题
  ├── error_patterns        → 讲义中增加对比表格/反例
  ├── learning_preferences  → 决定代码框架、内容组织方式
  ├── current_kp_id         → 定位当前应生成哪个知识点的资源
  └── prior_chapters        → 判断是否需要回溯补充
```

**核心数据流**：`POST /api/learner/{id}/diagnose` → `LearnerProfile` → JSON → 资源生成Agent消费

---

## 六、验证方法

完成升级后，验证以下场景：

1. **画像完整性**：`/api/learner/{id}/profile` 返回的JSON包含所有v2.0新字段且非空
2. **资源生成可用性**：取出 `resource_hints` 字段直接作为资源生成Agent的prompt约束，能生成3类资源
3. **三类画像区分度**：learner_001(初学者)/002(中级)/003(高级) 的 depth_labels 和 resource_hints 有显著差异
4. **证据可追溯**：evidence_records 中每条claim可追溯到 source_type 和 source_detail
