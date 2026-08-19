# 卷积神经网络（CNN）：分层测验答案与反馈卷

此文件用于教师审核或系统自动批改，不与学生卷同时发放。

## 参考答案与评分点

### Q1（概念混淆）

答：Conv2d 通常实现互相关，卷积核不做数学卷积的翻转；工程命名仍沿用卷积层。写出“核不翻转”和“工程命名”各得分。

### Q2（逻辑跳跃）

答：局部连接只看邻近像素；参数共享让同一卷积核在不同位置复用。只写“参数少”但无原因，不给满分。

### Q3（概念混淆）

答：只有 Conv2d 有可学习的卷积核和 bias；padding、stride 是超参数，MaxPool2d 是无参数汇聚操作。

### Q4

floor((32+2×1-3)/1)+1=32。评分必须检查是否写出 2×padding。

### Q5

floor((32+2×1-3)/2)+1=16。若得到 15，通常漏掉最后的 +1；若得到 14 或更小，检查是否遗漏 padding。

### Q6

weight=3×8×3×3=216，bias=8，总计 224。输出宽高不影响该层参数量。

### Q7

stride=2，padding=1；并用 Q5 的公式验证输出为 16×16。

### Q8

Conv2d 将第二维解释为通道，当前第二维为 32 而不是 3；可使用 x.permute(0, 3, 1, 2) 转换为 NCHW。

## 错题回流表

| 错题 | 错误类型 | 下一步资源 |
|---|---|---|
| Q1/Q3 | 概念混淆 | 讲义第 4、7 节 + 对比图 |
| Q4/Q5/Q6 | 计算错误 | Notebook 公式与参数量单元 |
| Q7/Q8 | 代码 shape 错误 | Notebook NCHW 与调试单元 |

## 证据来源

- definition：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_a3dde521400f，candidate_only）
- definition：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_5e2a9735ace2，candidate_only）
- code：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_51551ccb3ced，candidate_only）
- code：Derived PyTorch candidate from DeepLearning Chapter 9 Convolutional Networks（derived_dl_ch09_cnn_pytorch_conv2d_0804，candidate_only）
- exercise：Derived exercise candidate from DeepLearning Chapter 9 Convolutional Networks（derived_dl_ch09_cnn_exercise_0804，candidate_only）

> 资源状态：candidate_draft。这是可学习、可审核的候选草稿；正式教学发布前仍需完成证据审核与课程门禁。
