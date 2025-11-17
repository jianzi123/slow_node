#!/bin/bash
# Distributed NCCL Bandwidth Test Runner
# Runs NCCL tests across multiple nodes using MPI

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
HOSTFILE="${HOSTFILE:-./hostfile}"
GPUS_PER_NODE="${GPUS_PER_NODE:-8}"
OUTPUT_DIR="${OUTPUT_DIR:-./results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="${OUTPUT_DIR}/nccl_test_${TIMESTAMP}.txt"
JSON_FILE="${OUTPUT_DIR}/nccl_test_${TIMESTAMP}.json"

mkdir -p "$OUTPUT_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Distributed NCCL Bandwidth Test                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Validate hostfile
if [ ! -f "$HOSTFILE" ]; then
    echo -e "${RED}Error: Hostfile not found: $HOSTFILE${NC}"
    echo "Please create a hostfile with the following format:"
    echo "  node1 slots=8"
    echo "  node2 slots=8"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Hostfile: $HOSTFILE"
echo "  GPUs per node: $GPUS_PER_NODE"
echo "  Output directory: $OUTPUT_DIR"
echo "  Result file: $RESULT_FILE"
echo ""

# Display hostfile
echo -e "${YELLOW}Hosts:${NC}"
cat "$HOSTFILE"
echo ""

# Calculate total number of processes
NODE_COUNT=$(grep -v '^#' "$HOSTFILE" | grep -v '^$' | wc -l)
TOTAL_PROCS=$((NODE_COUNT * GPUS_PER_NODE))

echo -e "${YELLOW}Test parameters:${NC}"
echo "  Number of nodes: $NODE_COUNT"
echo "  Total processes: $TOTAL_PROCS"
echo ""

# Check connectivity to all nodes
echo -e "${YELLOW}Checking node connectivity...${NC}"
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue

    host=$(echo "$line" | awk '{print $1}')
    echo -n "  Checking $host... "

    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$host" "echo OK" &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo -e "${RED}Error: Cannot connect to $host${NC}"
        exit 1
    fi
done < "$HOSTFILE"
echo ""

# Test 1: All-Reduce Performance
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Test 1: All-Reduce Performance                           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Running all_reduce_perf test...${NC}"
mpirun --allow-run-as-root \
       --hostfile "$HOSTFILE" \
       -np "$TOTAL_PROCS" \
       --bind-to none \
       --map-by slot \
       -mca pml ob1 \
       -mca btl ^openib \
       -mca btl_tcp_if_include eth0 \
       --mca plm_rsh_no_tree_spawn 1 \
       -x NCCL_DEBUG=INFO \
       -x NCCL_IB_DISABLE=0 \
       -x NCCL_SOCKET_IFNAME=eth0 \
       -x NCCL_IB_HCA=mlx5 \
       -x NCCL_NET_GDR_LEVEL=5 \
       -x NCCL_IB_GID_INDEX=3 \
       -x LD_LIBRARY_PATH \
       /usr/local/bin/all_reduce_perf \
       -b 8 -e 8G -f 2 -g 1 -c 1 -n 100 \
       2>&1 | tee "$RESULT_FILE"

echo ""
echo -e "${GREEN}✓ All-Reduce test completed${NC}"
echo ""

# Test 2: All-Gather Performance
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Test 2: All-Gather Performance                           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Running all_gather_perf test...${NC}"
mpirun --allow-run-as-root \
       --hostfile "$HOSTFILE" \
       -np "$TOTAL_PROCS" \
       --bind-to none \
       --map-by slot \
       -mca pml ob1 \
       -mca btl ^openib \
       -x NCCL_DEBUG=INFO \
       -x NCCL_IB_DISABLE=0 \
       -x LD_LIBRARY_PATH \
       /usr/local/bin/all_gather_perf \
       -b 8 -e 1G -f 2 -g 1 -c 1 -n 100 \
       2>&1 | tee -a "$RESULT_FILE"

echo ""
echo -e "${GREEN}✓ All-Gather test completed${NC}"
echo ""

# Test 3: Broadcast Performance
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Test 3: Broadcast Performance                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Running broadcast_perf test...${NC}"
mpirun --allow-run-as-root \
       --hostfile "$HOSTFILE" \
       -np "$TOTAL_PROCS" \
       --bind-to none \
       --map-by slot \
       -mca pml ob1 \
       -mca btl ^openib \
       -x NCCL_DEBUG=INFO \
       -x NCCL_IB_DISABLE=0 \
       -x LD_LIBRARY_PATH \
       /usr/local/bin/broadcast_perf \
       -b 8 -e 1G -f 2 -g 1 -c 1 -n 100 \
       2>&1 | tee -a "$RESULT_FILE"

echo ""
echo -e "${GREEN}✓ Broadcast test completed${NC}"
echo ""

# Parse results and create summary JSON
echo -e "${YELLOW}Parsing results...${NC}"

python3 << PYEOF > "$JSON_FILE"
import re
import json
from datetime import datetime

def parse_nccl_results(filename):
    results = {
        "timestamp": datetime.now().isoformat(),
        "hostfile": "$HOSTFILE",
        "node_count": $NODE_COUNT,
        "gpus_per_node": $GPUS_PER_NODE,
        "total_processes": $TOTAL_PROCS,
        "tests": []
    }

    try:
        with open(filename, 'r') as f:
            content = f.read()

        # Parse different test sections
        test_types = ['all_reduce_perf', 'all_gather_perf', 'broadcast_perf']

        for test_type in test_types:
            # Find the test output section
            pattern = rf'{test_type}.*?out-of-place.*?Avg bus bandwidth.*?#\s*\n(.*?)(?=\n\n|\Z)'
            match = re.search(pattern, content, re.DOTALL)

            if match:
                test_data = {
                    "test_type": test_type,
                    "results": []
                }

                # Parse result lines
                lines = match.group(1).strip().split('\n')
                for line in lines:
                    # Match result line format: size, count, type, time, algbw, busbw
                    parts = line.split()
                    if len(parts) >= 6 and parts[0].isdigit():
                        test_data["results"].append({
                            "size_bytes": int(parts[0]),
                            "count": int(parts[1]),
                            "avg_time_us": float(parts[3]),
                            "algbw_GB/s": float(parts[4]),
                            "busbw_GB/s": float(parts[5])
                        })

                if test_data["results"]:
                    results["tests"].append(test_data)

    except Exception as e:
        results["error"] = str(e)

    return results

results = parse_nccl_results("$RESULT_FILE")
print(json.dumps(results, indent=2))
PYEOF

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  All tests completed successfully!                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Results saved to:${NC}"
echo "  Raw output: $RESULT_FILE"
echo "  JSON summary: $JSON_FILE"
echo ""

# Display quick summary
echo -e "${YELLOW}Quick Summary:${NC}"
python3 << PYEOF
import json

try:
    with open("$JSON_FILE", 'r') as f:
        data = json.load(f)

    print(f"  Nodes: {data['node_count']}")
    print(f"  Total GPUs: {data['total_processes']}")
    print(f"  Tests run: {len(data['tests'])}")

    for test in data['tests']:
        if test['results']:
            max_bw = max(r['busbw_GB/s'] for r in test['results'])
            print(f"  {test['test_type']}: Max bus BW = {max_bw:.2f} GB/s")

except Exception as e:
    print(f"  Error parsing summary: {e}")
PYEOF

echo ""
echo -e "${BLUE}Next step: Run slow node detection analysis${NC}"
echo -e "  ./scripts/analysis/detect_slow_nodes.py $JSON_FILE"
echo ""
