#!/bin/bash
# Advanced Slow Node Detection Runner
# Combines binary search and pairwise testing for comprehensive node validation

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
MODE="${MODE:-bisection}"  # bisection, pairwise, or both
THRESHOLD="${THRESHOLD:-}"  # Optional: bandwidth threshold in GB/s

# Print banner
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Advanced Slow Node Detection                          ║${NC}"
echo -e "${BLUE}║     Binary Search + Pairwise Testing                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Validate hostfile
if [ ! -f "$HOSTFILE" ]; then
    echo -e "${RED}Error: Hostfile not found: $HOSTFILE${NC}"
    echo "Please create a hostfile or set HOSTFILE environment variable"
    exit 1
fi

# Count nodes
NODE_COUNT=$(grep -v '^#' "$HOSTFILE" | grep -v '^$' | wc -l)

echo -e "${YELLOW}Configuration:${NC}"
echo "  Hostfile: $HOSTFILE"
echo "  Nodes: $NODE_COUNT"
echo "  GPUs per node: $GPUS_PER_NODE"
echo "  Detection mode: $MODE"
echo "  Output directory: $OUTPUT_DIR"
if [ -n "$THRESHOLD" ]; then
    echo "  Bandwidth threshold: $THRESHOLD GB/s"
else
    echo "  Bandwidth threshold: Auto-detect"
fi
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build command
CMD="$(dirname "$0")/bisection_detection.py"
CMD="$CMD --hostfile $HOSTFILE"
CMD="$CMD --mode $MODE"
CMD="$CMD --gpus-per-node $GPUS_PER_NODE"
CMD="$CMD --output-dir $OUTPUT_DIR"

if [ -n "$THRESHOLD" ]; then
    CMD="$CMD --threshold $THRESHOLD"
fi

# For large clusters, limit pairwise testing
if [ $NODE_COUNT -gt 10 ] && [ "$MODE" != "bisection" ]; then
    MAX_PAIRS=$((NODE_COUNT * 3))  # Test ~3x the number of nodes
    echo -e "${YELLOW}Large cluster detected ($NODE_COUNT nodes)${NC}"
    echo "  Limiting pairwise tests to $MAX_PAIRS pairs"
    CMD="$CMD --max-pairs $MAX_PAIRS"
fi

echo -e "${YELLOW}Starting detection...${NC}"
echo ""

# Run detection
if $CMD; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ Detection Complete - No Issues Found                   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    EXIT_CODE=$?
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ Slow Nodes Detected - Action Required                  ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Review the detailed report in $OUTPUT_DIR"
    echo "  2. Isolate the identified nodes from your cluster"
    echo "  3. Run diagnostics on the bad nodes:"
    echo "     - Check InfiniBand: ibstat, ibv_devinfo"
    echo "     - Check GPU: nvidia-smi, nvidia-smi topo -m"
    echo "     - Check network: ping, iperf3"
    echo "  4. Re-run detection after fixes"
    echo ""
    exit $EXIT_CODE
fi
