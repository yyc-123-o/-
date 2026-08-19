# 卷积神经网络（CNN）：PyTorch Conv2d 实操工作簿

这是一份边预测、边运行、边记录的实验工作簿。每个实验先在纸上写预测结果，再运行代码；如果预测与结果不同，按调试表定位原因。

## 0. 本实操的目标与边界

本实操不是直接训练大型 CNN，而是把“张量 → Conv2d 参数 → 输出 shape → 参数量”这条链跑通。每段代码不超过一个概念：先预测，再运行，再解释差异。

本学生的代码支架策略：代码能力可用但框架经验有限：提供可运行最小示例，要求一次只修改一个参数并用断言验证。

## 1. 环境与输入检查

使用 Python、PyTorch 与 Jupyter。先执行：

~~~python
import torch
from torch import nn
x = torch.randn(2, 3, 32, 32)
print(tuple(x.shape))  # 预期 (2, 3, 32, 32)
~~~

如果第二维不是 3，不要先改 Conv2d；先检查数据是否被错误地组织成 NHWC。

## 2. 工作示例 A：保持空间尺寸

~~~python
layer = nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1)
y = layer(x)
assert y.shape == (2, 8, 32, 32)
print(tuple(y.shape))
~~~

解释：padding=1 抵消 3×3 卷积核带来的边界缩小；out_channels=8 只改变通道数。

## 3. 工作示例 B：使用 stride 下采样

~~~python
layer = nn.Conv2d(3, 8, kernel_size=3, stride=2, padding=1)
y = layer(x)
assert y.shape == (2, 8, 16, 16)
~~~

请在运行前写下 floor((32+2×1-3)/2)+1=16，再用断言验证。

## 4. 工作示例 C：核对参数量

~~~python
weight_params = layer.weight.numel()
bias_params = 0 if layer.bias is None else layer.bias.numel()
print(weight_params, bias_params, weight_params + bias_params)
assert weight_params == 3 * 8 * 3 * 3
~~~

这一步专门防止把 8 个输出通道误当成 8×8 的空间尺寸。

## 4.5 先看图，再改代码

请先打开资源包中的 01_nchw_tensor_layout.svg、02_convolution_window.svg 和03_shape_reasoning_flow.svg：前两张用于建立视觉直觉，最后一张用于每次运行前手动预测 shape。图示偏好不会改变课程深度，只改变解释与练习方式。

## 5. 工作示例 D：卷积后接池化

~~~python
pool = nn.MaxPool2d(kernel_size=2, stride=2)
z = pool(y)
assert z.shape == (2, 8, 8, 8)
print('conv:', tuple(y.shape), 'pool:', tuple(z.shape))
~~~

池化没有可训练卷积核；它是在每个通道内做局部汇聚。不要把池化的尺寸变化归因于 out_channels。

## 6. 形状调试清单

| 现象 | 首先检查 | 修复动作 |
|---|---|---|
| expected input to have 3 channels | x.shape 的第二维 | 调整数据到 NCHW 或修改 in_channels |
| 输出宽高和手算不一致 | kernel、padding、stride | 逐项代入公式，不凭直觉 |
| 参数量对不上 | weight 与 bias | 分开计算 3×8×3×3 和 8 |
| 代码能跑但解释不出 | 没有记录中间 shape | 每层都打印输入与输出 |

## 7. 四个引导练习

1. 将 padding 从 1 改为 0，先预测输出为 15×15，再运行验证。
2. 将 stride 从 2 改为 1，解释为什么输出回到 32×32。
3. 将 out_channels 从 8 改为 16，列出变化与不变的维度。
4. 创建形状为 (2, 32, 32, 3) 的张量，解释为什么不能直接送入 Conv2d。

## 8. 连接到后续项目

当课程规划解除前置阻塞后，这些 shape 与参数量检查会直接迁移到 CIFAR-10：真实数据加载、训练/验证划分、损失曲线、特征图可视化与模型保存。现在先把每一层的输入输出说清楚，后续训练才不会被维度错误掩盖。

## 候选证据来源

- definition：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_a3dde521400f，candidate_only）
- definition：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_5e2a9735ace2，candidate_only）
- code：DeepLearning Chapter 9 Convolutional Networks（dl_ch09_cnn_51551ccb3ced，candidate_only）
- code：Derived PyTorch candidate from DeepLearning Chapter 9 Convolutional Networks（derived_dl_ch09_cnn_pytorch_conv2d_0804，candidate_only）
- exercise：Derived exercise candidate from DeepLearning Chapter 9 Convolutional Networks（derived_dl_ch09_cnn_exercise_0804，candidate_only）

> 资源状态：candidate_draft。这是可学习、可审核的候选草稿；正式教学发布前仍需完成证据审核与课程门禁。
