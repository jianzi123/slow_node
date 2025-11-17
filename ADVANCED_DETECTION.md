# 高级慢节点检测指南

## 概述

本工具实现了基于业界最佳实践的慢节点检测算法，比传统统计分析更准确、更高效。

## 为什么需要高级检测？

传统方法的局限性：
- **统计分析**: 依赖事后分析，需要先运行完整集群测试
- **全量测试**: 必须测试所有N个节点，耗时长
- **误判风险**: 仅基于统计推断，可能漏检或误报

高级检测的优势：
- **主动测试**: 动态组合节点进行测试，直接定位问题
- **高效算法**: 二分法O(N log N)，大幅减少测试次数
- **准确定位**: 通过多次测试交叉验证，准确识别慢节点

## 检测方法

### 1. 二分法检测 (Binary Search Detection)

**适用场景**: 快速定位少数慢节点

**原理**:
```
测试8个节点的例子:

第1轮: 测试全部8个节点 [1,2,3,4,5,6,7,8] → 发现慢
  ├─ 第2轮: 测试左半 [1,2,3,4] → 正常
  └─ 第2轮: 测试右半 [5,6,7,8] → 发现慢
      ├─ 第3轮: 测试 [5,6] → 正常
      └─ 第3轮: 测试 [7,8] → 发现慢
          ├─ 第4轮: 测试 [7] → 慢节点！
          └─ 第4轮: 测试 [8] → 正常

结果: 节点7是慢节点，仅需4轮测试
```

**使用方法**:
```bash
# 最简单
make detect-bisection

# 手动指定参数
./scripts/analysis/bisection_detection.py \
    --hostfile hostfile \
    --mode bisection \
    --threshold 200  # GB/s
```

**性能**:
- 4节点: ~3轮测试
- 8节点: ~4轮测试
- 16节点: ~5轮测试
- 64节点: ~7轮测试

### 2. 成对测试 (Pairwise Testing)

**适用场景**: 全面检测所有节点间通信问题

**原理**:
```
测试4个节点的例子:

测试所有节点对: C(4,2) = 6对
1. 节点1 ↔ 节点2: 250 GB/s ✓
2. 节点1 ↔ 节点3: 245 GB/s ✓
3. 节点1 ↔ 节点4: 195 GB/s ✗
4. 节点2 ↔ 节点3: 248 GB/s ✓
5. 节点2 ↔ 节点4: 198 GB/s ✗
6. 节点3 ↔ 节点4: 192 GB/s ✗

统计分析:
- 节点1: 平均 247.5 GB/s (2次测试)
- 节点2: 平均 249.0 GB/s (2次测试)
- 节点3: 平均 246.5 GB/s (2次测试)
- 节点4: 平均 195.0 GB/s (3次测试) ← 慢节点

结论: 节点4在所有配对中都表现差 → 确认为慢节点
```

**使用方法**:
```bash
# 测试所有节点对
make detect-pairwise

# 大集群限制测试对数
MAX_PAIRS=100 make detect-pairwise

# 或手动
./scripts/analysis/bisection_detection.py \
    --hostfile hostfile \
    --mode pairwise \
    --max-pairs 100
```

**注意事项**:
- 小集群(<10节点): 测试所有组合
- 大集群(>10节点): 自动限制测试对数，随机采样

### 3. 综合检测 (Combined Detection)

**最推荐的方法**: 结合二分法和成对测试

```bash
make detect-advanced
```

工作流程:
1. 先用二分法快速定位可疑节点
2. 再用成对测试验证和补充
3. 交叉验证结果，提高准确性

## 节点隔离

检测到慢节点后，自动更新配置排除它们：

```bash
make isolate
```

这会：
1. 更新hostfile（注释掉坏节点）
2. 生成Kubernetes nodeAffinity配置
3. 生成SLURM exclude指令
4. 创建隔离报告

### 手动隔离

```bash
# 从检测报告自动隔离
./scripts/analysis/node_isolation_helper.py \
    --report results/bisection_report_*.json \
    --hostfile hostfile

# 手动指定坏节点
./scripts/analysis/node_isolation_helper.py \
    --nodes node1,node2,node3 \
    --hostfile hostfile

# 生成K8s配置
./scripts/analysis/node_isolation_helper.py \
    --report report.json \
    --k8s-config

# 生成SLURM配置
./scripts/analysis/node_isolation_helper.py \
    --report report.json \
    --slurm-config
```

## 完整工作流示例

### 场景1: 新集群健康检查

```bash
# 1. 准备hostfile
cp configs/hostfile.template hostfile
vim hostfile  # 添加你的节点

# 2. 运行综合检测
make detect-advanced

# 3. 如果发现慢节点，自动隔离
make isolate

# 4. 验证修复后的集群
make detect-bisection
```

### 场景2: 生产环境故障排查

```bash
# 1. 快速检测（二分法，最快）
make detect-bisection

# 2. 检查检测报告
cat results/bisection_report_*.json | jq '.bad_nodes'

# 3. 隔离问题节点
make isolate

# 4. 通知运维团队
echo "坏节点已识别并隔离，请检查硬件"
```

### 场景3: 定期维护

```bash
# 每周定时任务
0 2 * * 0 cd /path/to/slow_node && make detect-bisection
```

## 输出说明

### 检测报告 (JSON)

```json
{
  "timestamp": "2025-01-17T12:30:45",
  "total_nodes": 8,
  "total_tests": 4,
  "duration_seconds": 245.6,
  "threshold_gb_s": 220.0,
  "bad_nodes": ["node-gpu-07"],
  "good_nodes": ["node-gpu-01", "node-gpu-02", ...],
  "test_history": [...]
}
```

### 隔离报告

更新后的hostfile示例:
```
node-gpu-01 slots=8
node-gpu-02 slots=8
node-gpu-03 slots=8
# ISOLATED: node-gpu-07 slots=8  ← 自动注释
node-gpu-08 slots=8
```

Kubernetes配置:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: NotIn
          values:
          - node-gpu-07
```

## 性能对比

| 节点数 | 传统全量测试 | 二分法 | 成对测试 | 综合检测 |
|--------|-------------|--------|----------|---------|
| 4      | 1次         | ~3次   | 6次      | ~9次    |
| 8      | 1次         | ~4次   | 28次     | ~32次   |
| 16     | 1次         | ~5次   | 120次    | ~125次  |
| 64     | 1次         | ~7次   | 采样200次 | ~207次  |

**建议**:
- **小集群(<8节点)**: 使用综合检测，最全面
- **中型集群(8-16节点)**: 使用二分法，速度和准确性平衡
- **大集群(>16节点)**: 先用二分法快速定位，必要时再成对验证

## 故障排查

### 问题: 检测超时

```bash
# 调整超时时间（默认5分钟）
# 编辑 bisection_detection.py 第154行
timeout=600  # 增加到10分钟
```

### 问题: 误判太多

```bash
# 放宽阈值
./scripts/analysis/bisection_detection.py \
    --hostfile hostfile \
    --threshold 180  # 降低阈值
```

### 问题: 没有检测到已知的坏节点

```bash
# 使用成对测试，更全面
make detect-pairwise

# 或手动测试特定节点对
mpirun --hostfile <(echo -e "node1 slots=8\nnode2 slots=8") \
       -np 16 /usr/local/bin/all_reduce_perf -b 1G -e 1G
```

## 参考资料

- [Google Cloud Cluster Health Scanner](https://github.com/GoogleCloudPlatform/cluster-health-scanner)
- [Microsoft Azure DGX Cloud Benchmarking](https://techcommunity.microsoft.com/blog/azurehighperformancecomputingblog/dgx-cloud-benchmarking-on-azure/4410826)
- [NVIDIA NCCL Tests](https://github.com/NVIDIA/nccl-tests)
- [Together.AI - Testing GPU Clusters](https://www.together.ai/blog/a-practitioners-guide-to-testing-and-running-large-gpu-clusters-for-training-generative-ai-models)

## 总结

高级慢节点检测提供了比传统方法更快、更准确的解决方案：

✅ **二分法**: 快速定位，适合日常检查
✅ **成对测试**: 全面验证，适合深度分析
✅ **自动隔离**: 一键排除坏节点
✅ **生产验证**: 基于业界最佳实践

推荐工作流: `make detect-advanced && make isolate`
