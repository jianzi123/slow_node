# NCCL 性能基准和标准数据范围

## 概述

本文档提供各种GPU集群配置的标准性能基准，用于判断您的集群是否达到预期性能。

## GPU间通讯带宽基准

### 1. 单机内GPU通讯（NVLink）

#### NVIDIA A100 (80GB, NVLink 3.0)

**硬件规格**:
- NVLink 带宽: 600 GB/s (双向)
- NVLink 连接: 12条 × 50 GB/s

**NCCL All-Reduce 性能基准**:

| 消息大小 | 预期算法带宽 (AlgBW) | 预期总线带宽 (BusBW) | 备注 |
|---------|---------------------|---------------------|------|
| 8 B     | 0.5-1 GB/s          | 0.5-1 GB/s          | 延迟占主导 |
| 1 KB    | 8-12 GB/s           | 8-12 GB/s           | 小消息 |
| 128 KB  | 80-100 GB/s         | 140-175 GB/s        | 中等消息 |
| 1 MB    | 150-180 GB/s        | 260-315 GB/s        | 大消息 |
| 128 MB  | 180-200 GB/s        | 315-350 GB/s        | 最优性能 |
| 1 GB    | 190-210 GB/s        | 330-370 GB/s        | 峰值性能 |
| 4 GB+   | 195-215 GB/s        | 340-375 GB/s        | 稳定峰值 |

**性能判断标准**:
- ✅ **优秀**: BusBW > 320 GB/s (>85% 理论峰值)
- ✅ **良好**: BusBW > 280 GB/s (>75% 理论峰值)
- ⚠️ **一般**: BusBW > 240 GB/s (>65% 理论峰值)
- ❌ **差**: BusBW < 240 GB/s (<65% 理论峰值)

#### NVIDIA H100 (80GB, NVLink 4.0)

**硬件规格**:
- NVLink 带宽: 900 GB/s (双向)
- NVLink 连接: 18条 × 50 GB/s

**NCCL All-Reduce 性能基准**:

| 消息大小 | 预期算法带宽 (AlgBW) | 预期总线带宽 (BusBW) | 备注 |
|---------|---------------------|---------------------|------|
| 128 MB  | 250-280 GB/s        | 440-490 GB/s        | 最优性能 |
| 1 GB    | 270-300 GB/s        | 470-525 GB/s        | 峰值性能 |
| 4 GB+   | 280-310 GB/s        | 490-540 GB/s        | 稳定峰值 |

**性能判断标准**:
- ✅ **优秀**: BusBW > 480 GB/s (>85% 理论峰值)
- ✅ **良好**: BusBW > 420 GB/s (>75% 理论峰值)
- ⚠️ **一般**: BusBW > 360 GB/s (>65% 理论峰值)
- ❌ **差**: BusBW < 360 GB/s (<65% 理论峰值)

#### NVIDIA V100 (32GB, NVLink 2.0)

**硬件规格**:
- NVLink 带宽: 300 GB/s (双向)
- NVLink 连接: 6条 × 25 GB/s

**NCCL All-Reduce 性能基准**:

| 消息大小 | 预期算法带宽 (AlgBW) | 预期总线带宽 (BusBW) |
|---------|---------------------|---------------------|
| 128 MB  | 80-100 GB/s         | 140-175 GB/s        |
| 1 GB    | 90-110 GB/s         | 160-190 GB/s        |
| 4 GB+   | 95-115 GB/s         | 165-200 GB/s        |

**性能判断标准**:
- ✅ **优秀**: BusBW > 170 GB/s (>85% 理论峰值)
- ✅ **良好**: BusBW > 150 GB/s (>75% 理论峰值)

### 2. 跨节点通讯（InfiniBand）

#### InfiniBand HDR (200 Gbps)

**硬件规格**:
- 单端口带宽: 200 Gbps = 25 GB/s
- 双端口聚合: 50 GB/s
- GPU Direct RDMA: 支持

**NCCL All-Reduce 性能基准 (2节点, 每节点8xA100)**:

| 消息大小 | 预期算法带宽 (AlgBW) | 预期总线带宽 (BusBW) | 备注 |
|---------|---------------------|---------------------|------|
| 128 MB  | 18-22 GB/s          | 32-38 GB/s          | IB限制开始 |
| 1 GB    | 20-24 GB/s          | 35-42 GB/s          | 接近IB峰值 |
| 4 GB+   | 21-25 GB/s          | 37-44 GB/s          | IB峰值 |

**性能判断标准 (双端口配置)**:
- ✅ **优秀**: BusBW > 40 GB/s (>80% 理论峰值)
- ✅ **良好**: BusBW > 35 GB/s (>70% 理论峰值)
- ⚠️ **一般**: BusBW > 30 GB/s (>60% 理论峰值)
- ❌ **差**: BusBW < 30 GB/s (<60% 理论峰值)

#### InfiniBand NDR (400 Gbps)

**硬件规格**:
- 单端口带宽: 400 Gbps = 50 GB/s
- 双端口聚合: 100 GB/s

**NCCL All-Reduce 性能基准 (2节点)**:

| 消息大小 | 预期算法带宽 (AlgBW) | 预期总线带宽 (BusBW) |
|---------|---------------------|---------------------|
| 128 MB  | 38-45 GB/s          | 66-79 GB/s          |
| 1 GB    | 42-50 GB/s          | 74-88 GB/s          |
| 4 GB+   | 44-52 GB/s          | 77-91 GB/s          |

**性能判断标准 (双端口配置)**:
- ✅ **优秀**: BusBW > 80 GB/s (>80% 理论峰值)
- ✅ **良好**: BusBW > 70 GB/s (>70% 理论峰值)

#### InfiniBand EDR (100 Gbps)

**硬件规格**:
- 单端口带宽: 100 Gbps = 12.5 GB/s
- 双端口聚合: 25 GB/s

**NCCL All-Reduce 性能基准 (2节点)**:

| 消息大小 | 预期总线带宽 (BusBW) |
|---------|---------------------|
| 1 GB    | 18-22 GB/s          |
| 4 GB+   | 19-23 GB/s          |

**性能判断标准**:
- ✅ **优秀**: BusBW > 20 GB/s (>80%)
- ✅ **良好**: BusBW > 17 GB/s (>68%)

### 3. GPU P2P (PCIe)

#### PCIe Gen4 x16

**硬件规格**:
- 理论带宽: 64 GB/s (双向)
- 实际可用: ~25-28 GB/s (单向)

**GPU-to-GPU P2P 带宽基准**:

| 拓扑结构 | 预期带宽 | 备注 |
|---------|---------|------|
| 同一PCIe switch | 22-26 GB/s | 最优 |
| 同一CPU socket | 18-22 GB/s | 经过CPU |
| 跨CPU socket | 12-16 GB/s | 经过QPI/UPI |

**性能判断标准 (同一switch)**:
- ✅ **优秀**: > 24 GB/s
- ✅ **良好**: > 20 GB/s
- ⚠️ **一般**: > 16 GB/s
- ❌ **差**: < 16 GB/s

#### PCIe Gen3 x16

**硬件规格**:
- 理论带宽: 32 GB/s (双向)
- 实际可用: ~12-14 GB/s (单向)

**GPU-to-GPU P2P 带宽基准**:

| 拓扑结构 | 预期带宽 |
|---------|---------|
| 同一PCIe switch | 11-13 GB/s |
| 同一CPU socket | 9-11 GB/s |
| 跨CPU socket | 6-8 GB/s |

## 常见配置性能矩阵

### DGX A100 (8x A100 80GB)

```
拓扑: 8个GPU全NVLink互联
网络: 8x 200Gb/s InfiniBand HDR

单机All-Reduce:
- 1GB消息: 330-370 GB/s (BusBW)
- 判断标准: >320 GB/s为优秀

多机All-Reduce (2节点):
- 1GB消息: 35-42 GB/s (BusBW)
- 判断标准: >40 GB/s为优秀
```

### DGX H100 (8x H100 80GB)

```
拓扑: 8个GPU全NVLink互联
网络: 8x 400Gb/s InfiniBand NDR

单机All-Reduce:
- 1GB消息: 470-525 GB/s (BusBW)
- 判断标准: >480 GB/s为优秀

多机All-Reduce (2节点):
- 1GB消息: 74-88 GB/s (BusBW)
- 判断标准: >80 GB/s为优秀
```

### 标准服务器 (8x A100/H100, PCIe)

```
拓扑: 通过PCIe连接，无NVLink
网络: 2x 200Gb/s InfiniBand HDR

单机All-Reduce:
- 1GB消息: 18-22 GB/s (BusBW) - PCIe限制
- 判断标准: >20 GB/s为优秀

多机All-Reduce (2节点):
- 1GB消息: 35-42 GB/s (BusBW)
- 判断标准: >40 GB/s为优秀
```

## 性能诊断指南

### 如何使用基准值

1. **运行NCCL测试**:
```bash
# 单机测试
./all_reduce_perf -b 8 -e 8G -f 2 -g 1

# 多机测试
make test-distributed
```

2. **查看Bus Bandwidth (BusBW)列**:
   - 这是衡量实际通讯性能的关键指标
   - 对比上表中对应消息大小的基准值

3. **性能判断**:
   - 如果 BusBW >= 基准值上限: 优秀 ✅
   - 如果 BusBW >= 基准值下限: 良好 ✅
   - 如果 BusBW < 基准值下限 20%: 需要检查 ⚠️
   - 如果 BusBW < 基准值下限 40%: 严重问题 ❌

### 常见性能问题诊断

#### 问题1: 单机性能远低于NVLink基准

**可能原因**:
- NVLink未正确连接: 检查 `nvidia-smi nvlink --status`
- GPU拓扑问题: 检查 `nvidia-smi topo -m`
- NCCL未使用NVLink: 设置 `NCCL_P2P_LEVEL=NVL`

**诊断命令**:
```bash
# 检查NVLink状态
nvidia-smi nvlink --status

# 检查GPU拓扑
nvidia-smi topo -m

# 预期看到: NV12 (NVLink) 而不是 PHB (PCIe)
```

#### 问题2: 跨节点性能远低于IB基准

**可能原因**:
- IB未启用: `NCCL_IB_DISABLE=1`
- GPU Direct RDMA未启用: `NCCL_NET_GDR_LEVEL=0`
- IB网卡问题: 检查 `ibstat`
- 网络拥塞或路由问题

**诊断命令**:
```bash
# 检查IB状态
ibstat

# 检查IB设备
ibv_devinfo

# 测试IB带宽
ib_write_bw

# 确保NCCL使用IB
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=NET
```

#### 问题3: PCIe带宽低

**可能原因**:
- PCIe链路降速: Gen3 instead of Gen4
- PCIe lane数减少: x8 instead of x16
- IOMMU问题

**诊断命令**:
```bash
# 检查PCIe速度和宽度
lspci -vvv | grep -i "lnksta:"

# 预期: Speed 16GT/s, Width x16
```

## 快速检查清单

使用以下命令快速验证您的集群配置:

```bash
# 1. GPU信息
nvidia-smi topo -m

# 2. NVLink状态 (如果有)
nvidia-smi nvlink --status

# 3. IB状态
ibstat

# 4. IB设备信息
ibv_devinfo

# 5. 运行单机NCCL测试
./all_reduce_perf -b 1G -e 1G -f 2 -g 1

# 6. 比较结果与本文档基准值
```

## 性能调优建议

### 优化NCCL参数

```bash
# 启用IB和GPU Direct RDMA
export NCCL_IB_DISABLE=0
export NCCL_NET_GDR_LEVEL=5

# 指定IB设备
export NCCL_IB_HCA=mlx5_0,mlx5_1

# 优化缓冲区大小
export NCCL_BUFFSIZE=8388608

# 增加NCCL线程数 (如果带宽仍未饱和)
export NCCL_NTHREADS=256
```

### 系统级优化

```bash
# 1. 禁用CPU频率调整
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 2. 设置IB参数
echo 1 > /sys/module/mlx5_core/parameters/prof_sel

# 3. 增大网络缓冲区
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
```

## 参考文档

- [NVIDIA NCCL Performance Guide](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/performance.html)
- [NVIDIA NVLink Specifications](https://www.nvidia.com/en-us/data-center/nvlink/)
- [InfiniBand Specifications](https://www.infinibandta.org/)
- [NCCL Tests Repository](https://github.com/NVIDIA/nccl-tests)

## 更新日志

- 2025-01-17: 初始版本，包含A100/H100/V100基准数据
