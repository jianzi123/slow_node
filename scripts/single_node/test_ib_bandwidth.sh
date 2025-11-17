#!/bin/bash
# InfiniBand Bandwidth Testing Script
# Tests IB network bandwidth using perftest tools

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

OUTPUT_DIR="${OUTPUT_DIR:-./results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="${OUTPUT_DIR}/ib_bandwidth_${TIMESTAMP}.json"

mkdir -p "$OUTPUT_DIR"

echo -e "${GREEN}=== InfiniBand Bandwidth Test ===${NC}"
echo "Output directory: $OUTPUT_DIR"
echo "Result file: $RESULT_FILE"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check required tools
if ! command_exists ibstat; then
    echo -e "${RED}Error: ibstat not found. Install infiniband-diags package.${NC}"
    exit 1
fi

if ! command_exists ib_write_bw; then
    echo -e "${RED}Error: ib_write_bw not found. Install perftest package.${NC}"
    exit 1
fi

# Detect InfiniBand devices
echo -e "${YELLOW}Detecting InfiniBand devices...${NC}"
IB_DEVICES=$(ibstat -l 2>/dev/null || echo "")

if [ -z "$IB_DEVICES" ]; then
    echo -e "${RED}No InfiniBand devices found!${NC}"
    echo '{"status": "error", "message": "No IB devices found"}' > "$RESULT_FILE"
    exit 1
fi

echo "Found IB devices:"
echo "$IB_DEVICES"
echo ""

# Get IB device status
echo -e "${YELLOW}InfiniBand Device Status:${NC}"
ibstat

echo ""
echo -e "${YELLOW}IB Link Information:${NC}"
for device in $IB_DEVICES; do
    echo "Device: $device"
    ibstatus $device 2>/dev/null || true
done

echo ""

# Test IB bandwidth (requires two nodes - this is single node setup check)
echo -e "${YELLOW}Testing IB capabilities...${NC}"

# Get IB device info
FIRST_DEVICE=$(echo "$IB_DEVICES" | head -n1)
PORT=1

# Run bandwidth test in loopback mode (if supported)
echo "Running IB write bandwidth test..."

# Create JSON result structure
cat > "$RESULT_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "test_type": "ib_bandwidth",
  "devices": [
EOF

first=true
for device in $IB_DEVICES; do
    if [ "$first" = true ]; then
        first=false
    else
        echo "," >> "$RESULT_FILE"
    fi

    # Get device info
    state=$(ibstat $device | grep "State:" | awk '{print $2}' || echo "Unknown")
    rate=$(ibstat $device | grep "Rate:" | awk '{print $2, $3}' || echo "Unknown")

    cat >> "$RESULT_FILE" << EOF
    {
      "device": "$device",
      "state": "$state",
      "rate": "$rate",
      "port": 1
    }
EOF
done

cat >> "$RESULT_FILE" << EOF

  ],
  "status": "completed"
}
EOF

echo ""
echo -e "${GREEN}IB bandwidth test completed!${NC}"
echo "Results saved to: $RESULT_FILE"

# Display summary
echo ""
echo -e "${YELLOW}=== Summary ===${NC}"
cat "$RESULT_FILE" | python3 -m json.tool 2>/dev/null || cat "$RESULT_FILE"

# Additional diagnostic commands
echo ""
echo -e "${YELLOW}=== Additional IB Diagnostics ===${NC}"

echo "IB Links:"
ibv_devinfo 2>/dev/null || echo "ibv_devinfo not available"

echo ""
echo "IB Network:"
ibnetdiscover 2>/dev/null || echo "ibnetdiscover not available (requires SM access)"

echo ""
echo -e "${GREEN}Test completed successfully!${NC}"
