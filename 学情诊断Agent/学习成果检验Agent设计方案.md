# 学习成果检验 Agent — 设计方案

> 定位：多智能体系统中的「第二流程」——在「资源生成 Agent」之后，检验学习者经过系统提供的资源学习后，是否获得明显提升。

---

## 一、与第一流程的本质区别

| 维度 | 第一流程（初始学情诊断） | 第二流程（学习成果检验） |
|------|------------------------|------------------------|
| 目标 | 建立 baseline 画像 | 检验学习效果 |
| 输入 | 自填问卷 + 自适应测试 | 学习后的复测数据 |
| 核心动作 | 单次诊断 | **两次画像对比** |
| 输出 | 四维画像 P0 | **学习成果检验报告** |
| 关键问题 | "学习者现在是什么水平" | "学习者有没有进步、进步了多少" |

## 二、整体数据流

```
第一流程: 诊断 → 画像 P0 (baseline) → 保存 → 学习路径规划 → 资源生成 → 学习者学习
                                                                              ↓
第二流程: 复测 → 画像 P1 (post) → 对比(P0, P1) → 学习成果检验报告 → 决定下一章
```

## 三、核心设计思路

### 1. 画像存储机制

第一流程诊断完成后，**持久化保存 baseline 画像**（按 `learner_id + chapter_id` 索引），供第二流程对比。

### 2. 复诊机制

复用第一流程的完整诊断引擎（IRT、掌握度、盲区、错误模式），但标记为"复诊"，输出画像 P1。

### 3. 对比分析（核心新增能力）

对 P0 和 P1 的**六个维度**逐一对比：

| 对比维度 | baseline P0 | 学习后 P1 | 提升指标 |
|---------|------------|----------|---------|
| 全局能力 θ | θ0 | θ1 | Δθ = θ1 - θ0 |
| 总正确率 | acc0 | acc1 | Δacc |
| 各领域掌握度 | domain0 | domain1 | Δdomain |
| 各知识点掌握度 | mastery0 | mastery1 | Δmastery（分类） |
| 知识盲区 | gaps0 | gaps1 | 消除/持续/新增 |
| 错误模式 | errors0 | errors1 | 改善/恶化 |
| 能力等级 | level0 | level1 | 是否升级 |

## 四、关键指标与阈值

### 知识点提升分类
```
显著提升:  Δmastery ≥ 0.3
提升:      0.1 ≤ Δmastery < 0.3
不变:      -0.1 ≤ Δmastery < 0.1
下降:      Δmastery < -0.1
```

### 盲区变化判定（掌握阈值 mastery ≥ 0.6）
```
已消除:  baseline mastery < 0.6 且 post mastery ≥ 0.6
持续:    baseline mastery < 0.6 且 post mastery < 0.6
新增:    baseline mastery ≥ 0.6 且 post mastery < 0.6（遗忘信号）
```

### 综合判定（verdict）
```
显著提升:    Δθ ≥ 0.5 且盲区消除率 ≥ 50%
一般提升:    Δθ ≥ 0.2 且盲区消除率 ≥ 30%
无明显提升:  -0.2 ≤ Δθ < 0.2
退步:        Δθ < -0.2
```

## 五、输出：学习成果检验报告

```json
{
  "report_id": "OUTCOME-xxx",
  "learner_id": "...",
  "chapter_id": "ch03_cnn",
  "baseline_profile_id": "...",
  "post_profile_id": "...",
  "overall_verdict": "显著提升",
  "theta": {"before": -0.5, "after": 0.3, "delta": 0.8},
  "accuracy": {"before": 0.35, "after": 0.62, "delta": 0.27},
  "ability_level": {"before": "beginner", "after": "intermediate"},
  "domain_changes": [{"domain": "深度学习", "before": 0.22, "after": 0.58, "delta": 0.36}],
  "kp_changes": [
    {"kp_id": "kp_012", "name": "CNN", "before": 0.18, "after": 0.65, "delta": 0.47, "category": "显著提升"},
    ...
  ],
  "gaps_resolved": [{"kp_id": "kp_012", "name": "CNN", "before": 0.18, "after": 0.65}],
  "gaps_remaining": [{"kp_id": "kp_017", "name": "反向传播", "mastery": 0.48}],
  "gaps_new": [],
  "error_pattern_changes": [...],
  "recommendation": "建议进入下一章节 ch04_transfer"
}
```

## 六、实现架构

```
新增模块:
├── core/learning_verifier.py   # 核心对比逻辑
├── models/schemas.py           # 扩展: LearningOutcomeReport 等报告模型
└── main.py                     # 扩展: 3 个新端点

新增端点:
POST /api/learner/{id}/save-baseline   # 保存 baseline 画像
POST /api/learner/{id}/re-diagnose     # 复诊（学习后再次诊断）
POST /api/learner/{id}/verify-outcome  # 对比并生成学习成果报告
```

## 七、与下游的衔接

学习成果检验报告输出给「交互导学 Agent」，用于：
- **决定是否进入下一章节**（提升达标 → 进阶）
- **决定是否需要回溯复习**（提升不足 → 回溯到薄弱知识点）
- **动态更新学习路径**（报告驱动下一轮规划）

这形成了完整的学习闭环：**诊断 → 学习 → 检验 → 再诊断 → ...**
