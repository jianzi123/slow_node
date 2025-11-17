# NCCL 慢节点检测工具 - 完整执行指南

## 目录

1. [环境准备](#环境准备)
2. [快速开始](#快速开始)
3. [详细执行步骤](#详细执行步骤)
4. [结果解读](#结果解读)
5. [常见问题](#常见问题)
6. [完整示例](#完整示例)

---

## 环境准备

### 前置要求

#### 硬件要求
- ✅ NVIDIA GPU (建议: A100, H100, V100)
- ✅ InfiniBand 网卡 (可选，用于跨节点测试)
- ✅ NVLink 连接 (可选，用于单机高速互联)

#### 软件要求
- ✅ NVIDIA驱动 (推荐: >= 525.x)
- ✅ CUDA Toolkit (推荐: >= 12.0)
- ✅ Docker (可选，用于容器化部署)
- ✅ Kubernetes (可选，用于K8s部署)
- ✅ OpenMPI (包含在Docker镜像中)

### 检查清单

在开始之前，运行以下命令检查环境:

```bash
# 1. 检查GPU
nvidia-smi

# 2. 检查CUDA
nvcc --version

# 3. 检查InfiniBand (如果有)
ibstat

# 4. 检查网络
ping <其他节点IP>

# 5. 检查SSH (用于MPI)
ssh <其他节点> hostname
```

**预期输出**:
- `nvidia-smi`: 显示所有GPU信息
- `ibstat`: 显示IB卡状态为 "Active"
- SSH连接成功无需密码

---

## 快速开始

### 5分钟快速体验

```bash
# 1. 克隆或下载项目
cd /path/to/slow_node

# 2. 设置环境
make setup

# 3. 配置节点列表
cp configs/hostfile.template hostfile
vim hostfile  # 添加你的节点，格式: node1 slots=8

# 4. 运行检测（推荐方法）
make detect-bisection

# 5. 查看结果
cat results/bisection_report_*.json
```

---

## 详细执行步骤

### 步骤1: 环境配置

#### 1.1 设置项目环境

```bash
# 进入项目目录
cd /path/to/slow_node

# 运行setup创建必要目录和设置权限
make setup
```

**这会做什么**:
- 创建 `results/` 和 `visualizations/` 目录
- 为所有脚本添加执行权限

#### 1.2 配置hostfile

hostfile是MPI使用的节点列表文件。

```bash
# 复制模板
cp configs/hostfile.template hostfile

# 编辑hostfile
vim hostfile
```

**hostfile格式**:
```bash
# 格式: 主机名或IP  slots=GPU数量
node-gpu-01 slots=8
node-gpu-02 slots=8
node-gpu-03 slots=8
node-gpu-04 slots=8
```

**注意事项**:
- `slots` 应该等于每个节点的GPU数量
- 确保所有节点之间可以无密码SSH访问
- 可以使用主机名或IP地址

#### 1.3 配置SSH免密登录 (如果需要)

```bash
# 在主节点生成SSH密钥
ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa

# 复制公钥到所有节点
for node in node-gpu-01 node-gpu-02 node-gpu-03 node-gpu-04; do
    ssh-copy-id $node
done

# 测试连接
for node in node-gpu-01 node-gpu-02 node-gpu-03 node-gpu-04; do
    ssh $node hostname
done
```

### 步骤2: 单机测试（可选但推荐）

在进行分布式测试前，先验证单机配置。

#### 2.1 InfiniBand测试

```bash
# 运行IB带宽测试
OUTPUT_DIR=./results ./scripts/single_node/test_ib_bandwidth.sh

# 查看结果
cat results/ib_bandwidth_*.json
```

**预期结果**:
- 看到IB设备状态为 "Active"
- 显示连接速率 (如 "200 Gb/sec" for HDR)

#### 2.2 CUDA测试

```bash
# 运行CUDA带宽测试
OUTPUT_DIR=./results ./scripts/single_node/test_cuda_bandwidth.sh

# 查看结果
cat results/cuda_bandwidth_*.json
```

**预期结果**:
- 显示GPU内存带宽
- 显示GPU-to-GPU P2P带宽

#### 2.3 GPU P2P测试

```bash
# 运行GPU P2P测试
OUTPUT_DIR=./results ./scripts/single_node/test_gpu_p2p.sh

# 查看结果
nvidia-smi topo -m
```

**预期结果**:
- 看到GPU间的连接类型: NV12 (NVLink) 或 PHB (PCIe)

#### 2.4 一键运行所有单机测试

```bash
make test-single
```

### 步骤3: 慢节点检测

有三种检测方法，**推荐使用二分法或综合检测**。

#### 方法A: 二分法检测（推荐，快速）

**适用场景**: 日常检查，快速定位少数慢节点

```bash
# 运行二分法检测
make detect-bisection
```

**执行流程**:
```
1. 测试所有节点
2. 如果发现问题，拆分成两组分别测试
3. 递归检测有问题的组
4. 最终识别所有慢节点
```

**预期时间**:
- 4节点: ~5-10分钟
- 8节点: ~10-15分钟
- 16节点: ~15-20分钟
- 64节点: ~25-35分钟

#### 方法B: 成对测试（全面）

**适用场景**: 深度分析，检测节点间通信问题

```bash
# 运行成对测试
make detect-pairwise
```

**执行流程**:
```
1. 测试所有节点对组合: C(N,2)
2. 统计每个节点在不同配对中的平均性能
3. 识别系统性表现差的节点
```

**预期时间**:
- 4节点 (6对): ~10-15分钟
- 8节点 (28对): ~30-45分钟
- 大集群会自动限制测试对数

#### 方法C: 综合检测（最准确，推荐）

**适用场景**: 生产环境检查，要求最高准确度

```bash
# 运行综合检测（二分法 + 成对测试）
make detect-advanced
```

**这会做什么**:
1. 先用二分法快速定位可疑节点
2. 再用成对测试验证
3. 交叉验证结果

**预期时间**: 二分法时间 + 成对测试时间

### 步骤4: 结果分析

#### 4.1 查看检测报告

```bash
# 二分法报告
cat results/bisection_report_*.json | jq '.'

# 成对测试报告
cat results/pairwise_report_*.json | jq '.'
```

**报告内容**:
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

#### 4.2 对比性能基准

打开 `PERFORMANCE_BENCHMARKS.md` 查找您的硬件配置对应的基准值。

**示例**: DGX A100
- 单机1GB消息预期BusBW: 330-370 GB/s
- 跨节点1GB消息预期BusBW: 35-42 GB/s

**判断标准**:
```
实际BusBW >= 基准最大值: ✅ 优秀
实际BusBW >= 基准最小值: ✅ 良好
实际BusBW < 基准最小值的80%: ⚠️ 需要检查
实际BusBW < 基准最小值的60%: ❌ 严重问题
```

### 步骤5: 节点隔离

如果检测到慢节点，自动更新配置排除它们。

```bash
# 自动隔离检测到的慢节点
make isolate
```

**这会做什么**:
1. **更新hostfile**: 注释掉坏节点
   ```bash
   node-gpu-01 slots=8
   node-gpu-02 slots=8
   # ISOLATED: node-gpu-07 slots=8  ← 自动注释
   node-gpu-08 slots=8
   ```

2. **生成K8s配置**: 创建nodeAffinity规则
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

3. **生成SLURM配置**: 创建排除指令
   ```bash
   #SBATCH --exclude=node-gpu-07
   ```

4. **创建隔离报告**: `isolation_report_*.json`

### 步骤6: 验证修复

隔离坏节点后，重新运行检测验证集群健康。

```bash
# 使用更新后的hostfile重新检测
make detect-bisection

# 如果没有发现问题，说明隔离成功
```

---

## 结果解读

### NCCL测试输出解释

NCCL测试会输出类似这样的表格:

```
       size         count      type   redop    root     time   algbw   busbw #wrong     time   algbw   busbw #wrong
        (B)    (elements)                               (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)
     8388608       2097152     float     sum      -1   1234.5   6.80   11.89      0   1230.1   6.82   11.93      0
  1073741824     268435456     float     sum      -1   5432.1 197.60  345.80      0   5420.3 198.01  346.52      0
```

**关键列说明**:

1. **size (B)**: 消息大小（字节）
   - 8388608 = 8MB
   - 1073741824 = 1GB

2. **time (us)**: 测试耗时（微秒）
   - 越低越好

3. **algbw (GB/s)**: 算法带宽
   - 实际传输的数据量 / 时间

4. **busbw (GB/s)**: 总线带宽 ⭐ **最重要的指标**
   - 考虑了集合通讯的通信模式
   - 用于与基准值对比

5. **#wrong**: 错误数量
   - 应该始终为0
   - 非0表示数据错误

### 性能等级判断

根据 `PERFORMANCE_BENCHMARKS.md`:

#### 单机NVLink (A100)
| BusBW范围 | 性能等级 | 说明 |
|----------|---------|------|
| > 340 GB/s | ✅ 优秀 | 超过85%理论峰值 |
| 280-340 GB/s | ✅ 良好 | 75-85%理论峰值 |
| 240-280 GB/s | ⚠️ 一般 | 65-75%理论峰值，可能需要优化 |
| < 240 GB/s | ❌ 差 | <65%理论峰值，需要检查 |

#### 跨节点IB HDR (200Gb/s)
| BusBW范围 | 性能等级 | 说明 |
|----------|---------|------|
| > 40 GB/s | ✅ 优秀 | 超过80%理论峰值 |
| 35-40 GB/s | ✅ 良好 | 70-80%理论峰值 |
| 30-35 GB/s | ⚠️ 一般 | 60-70%理论峰值 |
| < 30 GB/s | ❌ 差 | <60%理论峰值 |

### 检测报告解读

#### 二分法报告示例

```json
{
  "bad_nodes": ["node-gpu-03", "node-gpu-07"],
  "good_nodes": ["node-gpu-01", "node-gpu-02", "node-gpu-04", ...],
  "total_tests": 6,
  "duration_seconds": 180.5
}
```

**解读**:
- 在6轮测试后（而不是8轮全量测试）
- 识别出2个慢节点: node-gpu-03 和 node-gpu-07
- 耗时约3分钟

#### 成对测试报告示例

```json
{
  "analysis": {
    "node_statistics": {
      "node-gpu-01": {
        "average_bandwidth_gb_s": 245.5,
        "failure_count": 0,
        "total_tests": 3
      },
      "node-gpu-07": {
        "average_bandwidth_gb_s": 185.2,
        "failure_count": 2,
        "total_tests": 3
      }
    },
    "problematic_nodes": [
      {
        "node": "node-gpu-07",
        "average_bandwidth_gb_s": 185.2,
        "failure_rate": 0.67,
        "reason": "Low bandwidth"
      }
    ]
  }
}
```

**解读**:
- node-gpu-07 在所有配对中平均带宽都低
- 失败率67% (3次测试中2次失败)
- 确认为慢节点

---

## 常见问题

### Q1: "Error: hostfile not found"

**问题**: 没有配置hostfile

**解决**:
```bash
cp configs/hostfile.template hostfile
vim hostfile  # 添加你的节点
```

### Q2: SSH连接失败

**问题**: MPI无法连接到其他节点

**解决**:
```bash
# 1. 测试SSH连接
ssh node-gpu-01 hostname

# 2. 如果需要密码，配置免密登录
ssh-keygen
ssh-copy-id node-gpu-01

# 3. 确保StrictHostKeyChecking关闭
echo "StrictHostKeyChecking no" >> ~/.ssh/config
```

### Q3: NCCL测试超时

**问题**: 测试卡住或超时

**可能原因**:
- IB网络配置问题
- NCCL环境变量设置错误
- GPU挂起

**解决**:
```bash
# 1. 检查NCCL配置
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,NET

# 2. 检查IB状态
ibstat

# 3. 重启GPU
sudo nvidia-smi --gpu-reset

# 4. 增加超时时间（编辑bisection_detection.py）
timeout=600  # 从300增加到600秒
```

### Q4: 带宽远低于预期

**诊断步骤**:

1. **检查NVLink（单机）**:
```bash
nvidia-smi nvlink --status
# 预期: 所有链路 "Active"
```

2. **检查GPU拓扑**:
```bash
nvidia-smi topo -m
# 预期: 看到 NV12 (NVLink) 而不是 PHB (PCIe)
```

3. **检查NCCL配置**:
```bash
# 确保这些环境变量正确
export NCCL_IB_DISABLE=0      # 启用IB
export NCCL_NET_GDR_LEVEL=5   # 启用GPU Direct RDMA
export NCCL_P2P_LEVEL=NVL     # 使用NVLink
```

4. **检查IB连接（跨节点）**:
```bash
ibstat
# 预期: State: Active, Rate: 200 Gb/sec
```

### Q5: 误判了好节点

**问题**: 检测报告将正常节点标记为慢节点

**可能原因**:
- 阈值设置过严格
- 测试期间网络拥塞
- 其他负载影响

**解决**:
```bash
# 1. 手动指定更宽松的阈值
./scripts/analysis/bisection_detection.py \
    --hostfile hostfile \
    --threshold 180  # 降低阈值

# 2. 重新测试可疑节点
# 创建只包含可疑节点的hostfile
echo "node-gpu-07 slots=8" > test_hostfile
echo "node-gpu-01 slots=8" >> test_hostfile

# 单独测试
MODE=bisection HOSTFILE=test_hostfile ./scripts/analysis/run_advanced_detection.sh
```

### Q6: 如何恢复被隔离的节点

**问题**: 节点修复后需要重新加入集群

**解决**:
```bash
# 1. 手动编辑hostfile
vim hostfile

# 找到被注释的行:
# # ISOLATED: node-gpu-07 slots=8

# 取消注释:
node-gpu-07 slots=8

# 2. 重新运行检测验证
make detect-bisection
```

---

## 完整示例

### 示例1: 新集群首次检查

```bash
#!/bin/bash
# 新集群健康检查脚本

echo "=== 集群健康检查开始 ==="

# 1. 环境准备
echo "1. 设置环境..."
make setup

# 2. 配置节点
echo "2. 配置hostfile..."
cat > hostfile << EOF
node-gpu-01 slots=8
node-gpu-02 slots=8
node-gpu-03 slots=8
node-gpu-04 slots=8
EOF

# 3. 测试SSH连接
echo "3. 测试SSH连接..."
for node in node-gpu-01 node-gpu-02 node-gpu-03 node-gpu-04; do
    if ! ssh -o ConnectTimeout=5 $node hostname &>/dev/null; then
        echo "错误: 无法连接到 $node"
        exit 1
    fi
    echo "  ✓ $node 连接正常"
done

# 4. 运行单机测试（可选）
echo "4. 运行单机测试..."
make test-single

# 5. 运行综合检测
echo "5. 运行慢节点检测..."
make detect-advanced

# 6. 检查结果
echo "6. 检查检测结果..."
LATEST_REPORT=$(ls -t results/bisection_report_*.json 2>/dev/null | head -1)

if [ -f "$LATEST_REPORT" ]; then
    BAD_NODES=$(jq -r '.bad_nodes[]' "$LATEST_REPORT" 2>/dev/null)

    if [ -n "$BAD_NODES" ]; then
        echo "⚠️  发现慢节点:"
        echo "$BAD_NODES"

        # 7. 自动隔离
        echo "7. 自动隔离慢节点..."
        make isolate

        echo "集群检查完成 - 发现并隔离了慢节点"
        exit 1
    else
        echo "✓ 所有节点性能正常"
        echo "集群检查完成 - 集群健康"
        exit 0
    fi
else
    echo "错误: 未找到检测报告"
    exit 1
fi
```

### 示例2: 生产环境定期检查

```bash
#!/bin/bash
# 定期健康检查（可用于cron job）
# 每周运行: 0 2 * * 0 /path/to/weekly_check.sh

cd /path/to/slow_node

echo "[$(date)] 开始定期健康检查"

# 快速二分法检测
make detect-bisection

LATEST_REPORT=$(ls -t results/bisection_report_*.json | head -1)
BAD_NODES=$(jq -r '.bad_nodes[]' "$LATEST_REPORT" 2>/dev/null)

if [ -n "$BAD_NODES" ]; then
    # 发现问题，发送告警
    echo "发现慢节点: $BAD_NODES" | \
        mail -s "集群告警: 检测到慢节点" admin@company.com

    # 自动隔离
    make isolate

    echo "[$(date)] 检测到慢节点并已隔离"
else
    echo "[$(date)] 集群正常"
fi
```

### 示例3: 故障排查流程

```bash
#!/bin/bash
# 训练作业性能下降排查

echo "=== 性能下降排查 ==="

# 1. 快速检测
echo "Step 1: 运行快速检测..."
make detect-bisection

# 2. 查看结果
LATEST_REPORT=$(ls -t results/bisection_report_*.json | head -1)
BAD_NODES=$(jq -r '.bad_nodes[]' "$LATEST_REPORT")

if [ -z "$BAD_NODES" ]; then
    echo "未检测到慢节点，可能是其他问题"
    echo "建议检查:"
    echo "  - 网络拥塞"
    echo "  - 存储IO"
    echo "  - 代码优化"
    exit 0
fi

echo "发现慢节点: $BAD_NODES"

# 3. 详细诊断
echo "Step 2: 详细诊断慢节点..."
for node in $BAD_NODES; do
    echo ""
    echo "诊断 $node:"

    # SSH到该节点运行诊断
    ssh $node << 'DIAG'
    echo "  GPU状态:"
    nvidia-smi --query-gpu=index,name,temperature.gpu,power.draw,pcie.link.gen.current,pcie.link.width.current --format=csv

    echo "  NVLink状态:"
    nvidia-smi nvlink --status

    echo "  IB状态:"
    ibstat | grep -A 5 "State:"

    echo "  系统负载:"
    uptime

    echo "  内存:"
    free -h
DIAG
done

# 4. 隔离慢节点
echo "Step 3: 隔离慢节点..."
make isolate

echo "排查完成，慢节点已隔离"
echo "请运维团队检查被隔离的节点"
```

---

## 最佳实践

### 1. 定期检查

建议每周运行一次快速检测:

```bash
# 添加到crontab
0 2 * * 0 cd /path/to/slow_node && make detect-bisection
```

### 2. 性能基准记录

首次部署时记录性能基准:

```bash
# 在集群状态最佳时运行
make test-distributed

# 保存结果作为基准
cp results/nccl_test_*.json baseline/cluster_baseline.json
```

### 3. 渐进式检测

对于大集群，采用渐进策略:

```bash
# 1. 先快速检测
make detect-bisection

# 2. 如果发现问题，再用成对测试验证
make detect-pairwise

# 3. 确认后隔离
make isolate
```

### 4. 文档化

记录每次检测结果:

```bash
# 创建检测日志
echo "[$(date)] 检测完成" >> detection_log.txt
cat results/bisection_report_*.json | jq '.bad_nodes' >> detection_log.txt
```

---

## 下一步

完成首次检测后:

1. 📊 查看 `PERFORMANCE_BENCHMARKS.md` 了解性能基准
2. 🔧 根据检测结果优化配置
3. 📈 设置定期检查任务
4. 📝 建立集群健康监控体系

如有问题，请查看 `ADVANCED_DETECTION.md` 获取更多技术细节。
