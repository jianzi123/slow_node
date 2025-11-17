#!/bin/bash
# Quick Health Check Script
# 快速健康检查脚本 - 5分钟完成集群基本健康检查

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
HOSTFILE="${HOSTFILE:-./hostfile}"
RESULTS_DIR="./results"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              NCCL 集群快速健康检查                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: 环境检查
echo -e "${CYAN}[1/6] 检查环境...${NC}"

if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}✗ nvidia-smi 未找到${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ NVIDIA 驱动已安装${NC}"

if ! command -v mpirun &> /dev/null; then
    echo -e "${YELLOW}  ⚠ mpirun 未找到（Docker环境中应该有）${NC}"
else
    echo -e "${GREEN}  ✓ OpenMPI 已安装${NC}"
fi

# Step 2: GPU检查
echo ""
echo -e "${CYAN}[2/6] 检查GPU...${NC}"

GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -1)
echo -e "${GREEN}  ✓ 检测到 ${GPU_COUNT} 个GPU${NC}"

nvidia-smi --query-gpu=index,name,memory.total,temperature.gpu,power.draw \
    --format=csv,noheader | while IFS=',' read -r idx name mem temp power; do
    echo "    GPU $idx: $name | $mem | $temp | $power"
done

# Step 3: 网络检查
echo ""
echo -e "${CYAN}[3/6] 检查网络...${NC}"

# 检查IB
if command -v ibstat &> /dev/null; then
    IB_DEVICES=$(ibstat -l 2>/dev/null || echo "")
    if [ -n "$IB_DEVICES" ]; then
        echo -e "${GREEN}  ✓ 检测到 InfiniBand 设备${NC}"
        for dev in $IB_DEVICES; do
            state=$(ibstat $dev 2>/dev/null | grep "State:" | awk '{print $2}' || echo "Unknown")
            rate=$(ibstat $dev 2>/dev/null | grep "Rate:" | awk '{print $2" "$3}' || echo "Unknown")
            echo "    $dev: State=$state, Rate=$rate"
        done
    else
        echo -e "${YELLOW}  ⚠ 未检测到 InfiniBand 设备${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ ibstat 未安装（仅影响跨节点测试）${NC}"
fi

# Step 4: Hostfile检查
echo ""
echo -e "${CYAN}[4/6] 检查节点配置...${NC}"

if [ ! -f "$HOSTFILE" ]; then
    echo -e "${RED}  ✗ Hostfile 未找到: $HOSTFILE${NC}"
    echo -e "${YELLOW}  → 创建hostfile:${NC}"
    echo "      cp configs/hostfile.template hostfile"
    echo "      vim hostfile  # 添加你的节点"
    exit 1
fi

NODE_COUNT=$(grep -v '^#' "$HOSTFILE" | grep -v '^$' | wc -l)
echo -e "${GREEN}  ✓ 配置了 ${NODE_COUNT} 个节点${NC}"

grep -v '^#' "$HOSTFILE" | grep -v '^$' | head -5 | while read line; do
    echo "    $line"
done

if [ $NODE_COUNT -gt 5 ]; then
    echo "    ..."
fi

# Step 5: SSH连接检查
echo ""
echo -e "${CYAN}[5/6] 检查SSH连接...${NC}"

if [ $NODE_COUNT -gt 1 ]; then
    SSH_OK=true
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue

        host=$(echo "$line" | awk '{print $1}')

        if ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$host" "echo OK" &>/dev/null; then
            echo -e "${GREEN}  ✓ $host${NC}"
        else
            echo -e "${RED}  ✗ $host - 无法连接${NC}"
            SSH_OK=false
        fi
    done < "$HOSTFILE"

    if [ "$SSH_OK" = false ]; then
        echo ""
        echo -e "${YELLOW}  → 配置SSH免密登录:${NC}"
        echo "      ssh-keygen"
        echo "      ssh-copy-id <node>"
        exit 1
    fi
else
    echo -e "${YELLOW}  ⚠ 单节点模式，跳过SSH检查${NC}"
fi

# Step 6: 性能基准检查
echo ""
echo -e "${CYAN}[6/6] 性能基准提示...${NC}"

echo ""
echo -e "${YELLOW}根据您的硬件，预期性能基准:${NC}"
echo ""

# 检测GPU型号
GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)

case "$GPU_MODEL" in
    *"A100"*)
        echo -e "  GPU: ${GREEN}NVIDIA A100${NC}"
        echo "  单机 NVLink All-Reduce (1GB):"
        echo "    - 预期 Bus BW: 330-370 GB/s"
        echo "    - 优秀: > 340 GB/s"
        echo ""
        if [ $NODE_COUNT -gt 1 ]; then
            echo "  跨节点 IB HDR (1GB):"
            echo "    - 预期 Bus BW: 35-42 GB/s"
            echo "    - 优秀: > 40 GB/s"
        fi
        ;;
    *"H100"*)
        echo -e "  GPU: ${GREEN}NVIDIA H100${NC}"
        echo "  单机 NVLink All-Reduce (1GB):"
        echo "    - 预期 Bus BW: 470-525 GB/s"
        echo "    - 优秀: > 480 GB/s"
        echo ""
        if [ $NODE_COUNT -gt 1 ]; then
            echo "  跨节点 IB NDR (1GB):"
            echo "    - 预期 Bus BW: 74-88 GB/s"
            echo "    - 优秀: > 80 GB/s"
        fi
        ;;
    *"V100"*)
        echo -e "  GPU: ${GREEN}NVIDIA V100${NC}"
        echo "  单机 NVLink All-Reduce (1GB):"
        echo "    - 预期 Bus BW: 160-190 GB/s"
        echo "    - 优秀: > 170 GB/s"
        ;;
    *)
        echo -e "  GPU: ${YELLOW}${GPU_MODEL}${NC}"
        echo "  请查看 PERFORMANCE_BENCHMARKS.md 了解详细基准"
        ;;
esac

echo ""
echo -e "${YELLOW}详细基准请查看: ${CYAN}PERFORMANCE_BENCHMARKS.md${NC}"

# Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  健康检查完成                                                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${GREEN}✓ 环境检查通过${NC}"
echo ""
echo -e "${YELLOW}下一步操作:${NC}"
echo ""
echo "  1. 运行快速检测:"
echo -e "     ${CYAN}make detect-bisection${NC}"
echo ""
echo "  2. 运行全面检测:"
echo -e "     ${CYAN}make detect-advanced${NC}"
echo ""
echo "  3. 查看详细使用说明:"
echo -e "     ${CYAN}cat EXECUTION_GUIDE.md${NC}"
echo ""
echo "  4. 查看性能基准:"
echo -e "     ${CYAN}cat PERFORMANCE_BENCHMARKS.md${NC}"
echo ""
