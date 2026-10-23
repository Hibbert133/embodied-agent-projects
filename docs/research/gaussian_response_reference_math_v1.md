# 高斯参考的可复核数学口径

本文解释早期测量实验中已经冻结的标准参考，不调整其实现、参数或执行。
[范围与原始文献](gaussian_reference_prior_art_v1.md)中的 GAUGE 是相关方法，
本二维瞬态响应实现不是其完整复现，也没有继承其验证停止或硬件结论。

令当前命令为 $u\in[-1,1]^2$，$x=(u_1,u_2,1)^\top$，点参数按
$\theta=(A_{11},A_{12},b_1,A_{21},A_{22},b_2)^\top$ 排列。
固定名义 LINEAR_ARX 模型在已观察历史上的响应为

$$\widehat y_\theta=c(h)+B\,\operatorname{clip}(Au+b,-1,1),$$

实现将每行三个系数直接乘 $x$。$B$ 来自固定名义模型的命令
系数与训练尺度，$c(h)$ 由已经完成的位移历史和其余当前命令坐标确定。
真实执行噪声标准差 0.05 是执行输入的单位；下式 $s$ 是旧 CALIBRATION
初始六步可见位移的经验 RMS（米），二者不是同一噪声量。

均值 $\widehat\theta$ 来自相同可见样本的有界预测误差点拟合。令每个
实际样本的局部 Jacobian 为 $J_i$，固定先验方差
$D=\operatorname{diag}(1,1,.09,1,1,.09)$，定义参考矩

$$\Sigma=(D^{-1}+\textstyle\sum_i J_i^\top J_i/s^2)^{-1}.$$

这是点拟合均值加局部信息矩，不是已验证的真实 Bayesian 后验。
在候选命令 $q$ 上，令 $r=Aq+b$，代码使用

$$J(q)=B\operatorname{diag}(\mathbf1_{-1<r_j<1})
\begin{bmatrix}q_1&q_2&1&0&0&0\\0&0&0&q_1&q_2&1\end{bmatrix}.$$

每个候选四步程序只更新参考协方差：

$$\Sigma^+=\Sigma-\Sigma J^\top(s^2I+J\Sigma J^\top)^{-1}J\Sigma.$$

程序内沿用当前均值，不生成假想标签；实际完成四步后，用新真实历史
重新点拟合、重新建立信息矩。固定查询测度 $(q_k,w_k)$ 的评分是

$$\operatorname{IVR}=\sum_k w_k\operatorname{tr}
\big[J(q_k)(\Sigma-\Sigma^+)J(q_k)^\top\big].$$

GLOBAL 为九点等权测度；TASK 为旧 TRAIN/POLICY_ONLY 原政策命令的
冻结频率网格。它没有预测实际探测后的任务状态或成功概率，也没有显式
求探测运动的任务损失。不能把 IVR 命名为预计任务收益。

对于固定政策当前要求的二维命令 $d$，有界控制参考最小化未饱和仿射矩
的二次代理

$$\mathbb E_{\rm reference}\|Au+b-d\|^2+.01\|u-d\|^2,
\qquad u\in[-1,1]^2.$$

令 $R=\Sigma_{0:2,0:2}+\Sigma_{3:5,3:5}$，
$r=\Sigma_{0:2,2}+\Sigma_{3:5,5}$，则与 $u$ 有关的部分为

$$u^\top H u+2g^\top u,\quad
H=\bar A^\top\bar A+.01I+R,\quad
g=\bar A^\top(\bar b-d)-.01d+r.$$

代码枚举两轴自由／下界／上界共九种活动集，解自由坐标的线性方程并在
合法解中取最小值。正则项使 $H$ 正定；测试分别核对内部、边和角的 KKT
条件。z 与 gripper 保持固定政策经过公共截断后的值。

点参数的逆不稳定不妨碍该正定二次目标有解，因此本参考可以在有限点
参数存在时执行；若没有有限点参数，仍停止并保留失败。这个数值事实
不能证明真实动力学的稳定、安全或任务成功。相关数据、状态依赖模型
误差、饱和尾部及实际输入噪声没有通过上述矩模型的物理似然检验。
