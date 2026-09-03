export interface CourseKnowledgeNode {
  id: string;
  title: string;
  chapterId: string;
  summary: string;
  prerequisites: string[];
  lectures: number;
  examples: number;
  exercises: number;
  assessments: number;
  estimatedMinutes: number;
}

export interface CourseChapter {
  id: string;
  order: number;
  title: string;
  subtitle: string;
  nodes: CourseKnowledgeNode[];
}

export const courseKnowledgeBase = {
  id: "course.ai-foundations-to-llm.v1",
  title: "人工智能基础课程",
  currentTrack: "卷积神经网络（CNN）",
  subtitle: "人工智能专业基础课",
  chapters: [
    {
      id: "chapter.01.math-foundations",
      order: 1,
      title: "基础准备",
      subtitle: "线性代数、微积分与概率基础",
      nodes: [
        { id: "math.linear-algebra.scalar", title: "标量基础", chapterId: "chapter.01.math-foundations", summary: "理解标量在张量计算中的角色。", prerequisites: [], lectures: 2, examples: 1, exercises: 4, assessments: 1, estimatedMinutes: 18 },
        { id: "math.linear-algebra.vector", title: "向量基础", chapterId: "chapter.01.math-foundations", summary: "掌握向量表示、运算与几何意义。", prerequisites: ["math.linear-algebra.scalar"], lectures: 2, examples: 1, exercises: 5, assessments: 1, estimatedMinutes: 22 },
        { id: "math.linear-algebra.matrix", title: "矩阵基础", chapterId: "chapter.01.math-foundations", summary: "理解矩阵表示和神经网络中的线性变换。", prerequisites: ["math.linear-algebra.vector"], lectures: 2, examples: 2, exercises: 5, assessments: 1, estimatedMinutes: 26 },
        { id: "math.calculus.derivative-gradient", title: "导数与梯度", chapterId: "chapter.01.math-foundations", summary: "理解梯度如何指导模型参数更新。", prerequisites: ["math.linear-algebra.vector"], lectures: 2, examples: 1, exercises: 5, assessments: 1, estimatedMinutes: 25 },
      ],
    },
    {
      id: "chapter.02.classical-machine-learning",
      order: 2,
      title: "卷积运算基础",
      subtitle: "从损失函数到梯度下降的先修链路",
      nodes: [
        { id: "ml.optimization.loss-function", title: "损失函数", chapterId: "chapter.02.classical-machine-learning", summary: "理解目标函数如何度量预测结果与真实结果的差距。", prerequisites: ["math.calculus.derivative-gradient"], lectures: 2, examples: 1, exercises: 6, assessments: 1, estimatedMinutes: 20 },
        { id: "ml.optimization.gradient-descent", title: "梯度下降", chapterId: "chapter.02.classical-machine-learning", summary: "掌握沿负梯度方向更新参数的基本思想。", prerequisites: ["ml.optimization.loss-function"], lectures: 3, examples: 2, exercises: 8, assessments: 1, estimatedMinutes: 30 },
        { id: "dl.vision.image-tensor", title: "图像张量", chapterId: "chapter.02.classical-machine-learning", summary: "理解图像如何以多维张量形式进入模型。", prerequisites: ["math.linear-algebra.matrix"], lectures: 2, examples: 1, exercises: 6, assessments: 1, estimatedMinutes: 24 },
        { id: "dl.cnn.convolution", title: "卷积核与特征图", chapterId: "chapter.02.classical-machine-learning", summary: "理解卷积核如何在输入上滑动并生成特征图。", prerequisites: ["dl.vision.image-tensor", "ml.optimization.gradient-descent"], lectures: 3, examples: 2, exercises: 8, assessments: 1, estimatedMinutes: 32 },
        { id: "dl.cnn.padding-stride", title: "步长与填充", chapterId: "chapter.02.classical-machine-learning", summary: "掌握步长、填充对输出尺寸和特征保留的影响。", prerequisites: ["dl.cnn.convolution"], lectures: 2, examples: 1, exercises: 6, assessments: 1, estimatedMinutes: 25 },
        { id: "dl.cnn.pooling", title: "多通道卷积", chapterId: "chapter.02.classical-machine-learning", summary: "理解多通道输入、多个卷积核和输出通道之间的关系。", prerequisites: ["dl.cnn.convolution"], lectures: 2, examples: 1, exercises: 6, assessments: 1, estimatedMinutes: 26 },
        { id: "dl.cnn.receptive-field", title: "感受野基础", chapterId: "chapter.02.classical-machine-learning", summary: "分析卷积网络中单个神经元能够看到的输入区域。", prerequisites: ["dl.cnn.padding-stride"], lectures: 1, examples: 1, exercises: 4, assessments: 1, estimatedMinutes: 18 },
        { id: "dl.cnn.cross-correlation", title: "互相关运算", chapterId: "chapter.02.classical-machine-learning", summary: "区分卷积与互相关在深度学习框架中的实现差异。", prerequisites: ["dl.cnn.convolution"], lectures: 1, examples: 1, exercises: 4, assessments: 1, estimatedMinutes: 16 },
      ],
    },
    {
      id: "chapter.03.neural-networks",
      order: 3,
      title: "卷积层与池化层",
      subtitle: "CNN 网络结构中的核心层",
      nodes: [
        { id: "dl.neuron.perceptron", title: "感知机", chapterId: "chapter.03.neural-networks", summary: "从单个神经元理解非线性分类。", prerequisites: ["math.linear-algebra.vector"], lectures: 2, examples: 1, exercises: 4, assessments: 1, estimatedMinutes: 20 },
        { id: "dl.activation.relu", title: "ReLU 激活函数", chapterId: "chapter.03.neural-networks", summary: "理解激活函数如何引入非线性表达能力。", prerequisites: ["dl.neuron.perceptron"], lectures: 2, examples: 1, exercises: 5, assessments: 1, estimatedMinutes: 20 },
      ],
    },
    { id: "chapter.04.training-and-regularization", order: 4, title: "CNN 网络结构", subtitle: "网络搭建、训练与正则化", nodes: [] },
    { id: "chapter.05.cnn-representation", order: 5, title: "模型训练与优化", subtitle: "训练循环、优化器与调参", nodes: [] },
    { id: "chapter.06.embeddings-and-sequences", order: 6, title: "综合实践", subtitle: "端到端视觉任务与结果分析", nodes: [] },
  ] satisfies CourseChapter[],
};
