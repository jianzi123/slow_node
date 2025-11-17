# NCCL Slow Node Detection Tool

分布式NCCL带宽测试和慢节点检测工具。支持多机器部署、Kubernetes集成，以及单机IB/CUDA测试。

## 功能特性

1. **分布式NCCL测试** - 使用MPI在多个节点上运行NCCL通讯测试
2. **Kubernetes支持** - 提供完整的K8s部署配置
3. **单机带宽测试** - 测试InfiniBand、CUDA和GPU P2P性能
4. **🔥 智能慢节点检测** - 使用二分法和成对测试精确定位问题节点（基于业界最佳实践）
5. **自动节点隔离** - 自动更新配置排除慢节点
6. **结果可视化** - 生成带宽性能图表和报告

## 项目结构

```
slow_node/
├── docker/                    # Docker镜像
│   └── Dockerfile.nccl-mpi   # 包含NCCL、MPI、CUDA的镜像
├── k8s/                       # Kubernetes配置
│   ├── nccl-test-job.yaml    # StatefulSet部署配置
│   └── mpi-operator.yaml     # MPI Operator配置
├── scripts/
│   ├── single_node/          # 单机测试脚本
│   │   ├── test_ib_bandwidth.sh     # InfiniBand带宽测试
│   │   ├── test_cuda_bandwidth.sh   # CUDA带宽测试
│   │   └── test_gpu_p2p.sh          # GPU P2P测试
│   ├── distributed/          # 分布式测试脚本
│   │   ├── run_nccl_test.sh         # NCCL测试运行器
│   │   └── mpi_nccl_test.py         # Python MPI测试包装器
│   └── analysis/             # 分析工具
│       ├── detect_slow_nodes.py           # 统计分析慢节点检测
│       ├── bisection_detection.py         # 二分法+成对测试检测（推荐）
│       ├── run_advanced_detection.sh      # 高级检测运行器
│       ├── node_isolation_helper.py       # 节点隔离辅助工具
│       └── visualize_results.py           # 结果可视化
├── configs/                   # 配置文件
│   ├── hostfile.template     # MPI主机文件模板
│   └── nccl_env.conf         # NCCL环境变量配置
├── Makefile                  # 自动化构建和测试
└── Readme.md                 # 本文件
```

## 快速开始

### 1. 构建Docker镜像

```bash
# 本地构建
cd docker
docker build -f Dockerfile.nccl-mpi -t nccl-mpi:latest .

# 或使用Makefile
make build IMAGE_NAME=nccl-mpi IMAGE_TAG=latest
```

### 2. 单机测试

```bash
# 设置权限
make setup

# 运行单机测试
make test-single

# 或手动运行
./scripts/single_node/test_ib_bandwidth.sh
./scripts/single_node/test_cuda_bandwidth.sh
./scripts/single_node/test_gpu_p2p.sh
```

### 3. 分布式测试

#### 方法A: 使用MPI直接运行

```bash
# 1. 创建hostfile
cp configs/hostfile.template hostfile
# 编辑hostfile，添加你的节点信息
vim hostfile

# 2. 运行测试
make test-distributed

# 或手动运行
HOSTFILE=./hostfile ./scripts/distributed/run_nccl_test.sh
```

#### 方法B: 使用Kubernetes

```bash
# 1. 修改k8s配置文件
vim k8s/nccl-test-job.yaml
# 更新镜像地址和节点数量

# 2. 部署
kubectl apply -f k8s/nccl-test-job.yaml

# 3. 查看状态
kubectl get pods -l app=nccl-test

# 4. 查看日志
kubectl logs -f nccl-test-worker-0
```

#### 方法C: 使用MPI Operator (推荐用于K8s)

```bash
# 1. 安装MPI Operator
kubectl apply -f https://raw.githubusercontent.com/kubeflow/mpi-operator/master/deploy/v2beta1/mpi-operator.yaml

# 2. 部署NCCL测试任务
kubectl apply -f k8s/mpi-operator.yaml

# 3. 查看状态
kubectl get mpijob
kubectl logs -f nccl-bandwidth-test-launcher-xxxxx
```

### 4. 慢节点检测

#### 方法A: 高级检测（推荐） - 二分法 + 成对测试

基于业界最佳实践（Google Cloud Cluster Health Scanner、Microsoft Azure DGX）的智能检测方法：

```bash
# 二分法检测（快速，推荐）
# 使用二分搜索算法快速定位慢节点
make detect-bisection

# 成对测试（全面）
# 测试所有节点对，识别通信问题
make detect-pairwise

# 综合检测（最彻底）
# 同时使用两种方法，最高准确度
make detect-advanced

# 自动隔离检测到的慢节点
make isolate
```

**工作原理**：
1. **二分法**: 递归分组测试节点，快速缩小问题范围（类似二分查找）
2. **成对测试**: 测试所有节点配对，找出系统性表现差的节点
3. **自动隔离**: 更新hostfile，注释掉坏节点，生成K8s/SLURM排除配置

#### 方法B: 传统统计分析

基于已完成的测试结果进行统计分析：

```bash
# 自动检测最新的测试结果
make detect

# 或手动指定结果文件
./scripts/analysis/detect_slow_nodes.py results/nccl_test_20250117_120000.json \
    --output report.txt \
    --verbose

# JSON格式输出
./scripts/analysis/detect_slow_nodes.py results/nccl_test_20250117_120000.json --json
```

### 5. 结果可视化

```bash
# 生成可视化图表
make visualize

# 或手动运行
./scripts/analysis/visualize_results.py results/nccl_test_20250117_120000.json \
    --output-dir ./visualizations \
    --dashboard
```

## 慢节点检测原理

### 🔥 高级检测方法（推荐）

基于业界最佳实践的智能检测算法：

#### 1. 二分法检测 (Binary Search Detection)

灵感来源：**Microsoft Azure DGX** - "binary search and pairwise NCCL tests were performed to isolate underperforming nodes"

**算法流程**：
```
开始: 测试所有N个节点
  ├─ 如果正常 → 结束 ✓
  └─ 如果异常 → 拆分为两组
      ├─ 测试左半部分 (N/2个节点)
      │   ├─ 如果正常 → 标记为好节点
      │   └─ 如果异常 → 继续递归拆分
      └─ 测试右半部分 (N/2个节点)
          ├─ 如果正常 → 标记为好节点
          └─ 如果异常 → 继续递归拆分
最终: 识别所有慢节点
```

**优势**：
- **效率高**: O(N·log N) 复杂度，远优于全量测试
- **准确性高**: 直接测试节点组合，而非依赖统计推断
- **适合大规模集群**: 64节点集群只需约6轮测试

#### 2. 成对测试 (Pairwise Testing)

灵感来源：**Google Cloud Cluster Health Scanner** - "runs a pairwise NCCL bandwidth test on the cluster"

**方法**：
- 测试所有节点对组合: C(N,2) = N×(N-1)/2
- 统计每个节点在不同配对中的平均性能
- 识别系统性表现差的节点（在多个配对中都慢）

**优势**：
- **全面性**: 测试所有节点间通信
- **可识别通信问题**: 发现特定节点对之间的连接问题
- **减少误判**: 基于多次测试的统计平均

#### 3. 组合策略

```bash
# 推荐流程
make detect-advanced  # 二分法 + 成对测试
make isolate          # 自动隔离坏节点
```

### 传统统计检测方法

适用于已有测试结果的事后分析：

1. **Z-Score分析**
   - 计算每个节点带宽的Z分数
   - 阈值：默认为2个标准差
   - 适合正态分布的数据

2. **IQR (四分位距) 方法**
   - 使用四分位数检测异常值
   - 更鲁棒，不受极端值影响
   - 阈值：Q1 - 1.5×IQR 和 Q3 + 1.5×IQR

3. **交叉验证**
   - 两种方法的交集提供高置信度结果
   - 减少误报率

### 示例输出

```
======================================================================
SLOW NODE DETECTION REPORT
======================================================================
Timestamp: 2025-01-17T12:30:45

Overall Statistics:
  mean_bandwidth_GB/s: 245.67
  median_bandwidth_GB/s: 248.32
  std_bandwidth_GB/s: 12.45
  min_bandwidth_GB/s: 198.23
  max_bandwidth_GB/s: 256.78

Slow Nodes Detected:

1. node-gpu-03
   Reason: Performance outlier detected
   Confidence: high
   Threshold: 220.77 GB/s
   Current Performance: 198.23 GB/s

======================================================================
```

## NCCL环境变量配置

关键的NCCL环境变量（详见 `configs/nccl_env.conf`）：

```bash
# 调试级别
NCCL_DEBUG=INFO              # VERSION, WARN, INFO, TRACE

# InfiniBand配置
NCCL_IB_DISABLE=0            # 0=启用IB, 1=禁用IB
NCCL_IB_HCA=mlx5            # IB设备名称
NCCL_IB_GID_INDEX=3         # RoCE的GID索引
NCCL_NET_GDR_LEVEL=5        # GPU Direct RDMA级别

# 网络接口
NCCL_SOCKET_IFNAME=eth0     # 使用的网络接口

# 性能调优
NCCL_BUFFSIZE=8388608       # 缓冲区大小 (8MB)
NCCL_NTHREADS=256           # 每个rank的线程数
```

## 故障排查

### 问题: NCCL测试失败

```bash
# 1. 检查NCCL调试输出
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,ENV,NET

# 2. 验证GPU可见性
nvidia-smi

# 3. 检查IB状态
ibstat
ibv_devinfo

# 4. 测试节点间SSH连接
ssh node1 hostname
```

### 问题: 带宽异常低

可能原因：
- InfiniBand未正确配置 → 检查 `NCCL_IB_DISABLE`
- GPU Direct RDMA未启用 → 检查 `NCCL_NET_GDR_LEVEL`
- 网络拥塞 → 检查 `ibstat` 和网络拓扑
- PCIe带宽限制 → 运行 `nvidia-smi topo -m`

### 问题: K8s部署失败

```bash
# 检查Pod状态
kubectl describe pod nccl-test-worker-0

# 检查GPU资源
kubectl get nodes -o json | jq '.items[].status.allocatable'

# 检查RDMA设备
kubectl describe node | grep rdma
```

## 高级用法

### 自定义测试参数

编辑 `scripts/distributed/run_nccl_test.sh`：

```bash
# 修改测试参数
# -b: 起始大小 (8 bytes)
# -e: 结束大小 (8GB)
# -f: 增长因子 (2x)
# -g: 每个进程的GPU数 (1)
# -c: 检查结果 (1=启用)
# -n: 迭代次数 (100)

/usr/local/bin/all_reduce_perf -b 8 -e 8G -f 2 -g 1 -c 1 -n 100
```

### 定制检测阈值

```bash
# 使用更严格的阈值 (1.5个标准差)
./scripts/analysis/detect_slow_nodes.py results/test.json --threshold 1.5

# 或编辑脚本修改IQR倍数
```

### 持续监控

```bash
# 定期运行测试并检测
while true; do
    make test-distributed
    make detect
    sleep 3600  # 每小时运行一次
done
```

## 性能基准

典型的NCCL all-reduce带宽（8个A100 GPUs，NVLink + IB）：

| Message Size | Expected Bandwidth |
|--------------|-------------------|
| 1 KB         | ~10 GB/s          |
| 1 MB         | ~100 GB/s         |
| 1 GB         | ~230-250 GB/s     |
| 8 GB         | ~240-260 GB/s     |

如果你的结果显著低于这些值，可能存在配置问题或硬件故障。

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 联系方式

如有问题或建议，请创建Issue。
