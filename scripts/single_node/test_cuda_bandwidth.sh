#!/bin/bash
# CUDA Bandwidth Testing Script
# Tests GPU memory bandwidth and GPU-to-GPU transfer speeds

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

OUTPUT_DIR="${OUTPUT_DIR:-./results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="${OUTPUT_DIR}/cuda_bandwidth_${TIMESTAMP}.json"

mkdir -p "$OUTPUT_DIR"

echo -e "${GREEN}=== CUDA Bandwidth Test ===${NC}"
echo "Output directory: $OUTPUT_DIR"
echo "Result file: $RESULT_FILE"
echo ""

# Check if CUDA is available
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}Error: nvidia-smi not found. CUDA not available.${NC}"
    exit 1
fi

# Get GPU information
echo -e "${YELLOW}Detecting GPUs...${NC}"
GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -1)
echo "Found $GPU_COUNT GPU(s)"
echo ""

nvidia-smi --query-gpu=index,name,memory.total,memory.free,temperature.gpu,power.draw \
    --format=csv,noheader

echo ""

# Create CUDA bandwidth test program
CUDA_TEST_DIR="/tmp/cuda_bandwidth_test_$$"
mkdir -p "$CUDA_TEST_DIR"
cd "$CUDA_TEST_DIR"

cat > bandwidth_test.cu << 'EOF'
#include <cuda_runtime.h>
#include <stdio.h>
#include <stdlib.h>

#define CHECK_CUDA(call) \
    do { \
        cudaError_t err = call; \
        if (err != cudaSuccess) { \
            fprintf(stderr, "CUDA error at %s:%d: %s\n", __FILE__, __LINE__, \
                    cudaGetErrorString(err)); \
            exit(EXIT_FAILURE); \
        } \
    } while(0)

void testDeviceMemoryBandwidth(int device, size_t size) {
    CHECK_CUDA(cudaSetDevice(device));

    void *d_ptr;
    CHECK_CUDA(cudaMalloc(&d_ptr, size));

    cudaEvent_t start, stop;
    CHECK_CUDA(cudaEventCreate(&start));
    CHECK_CUDA(cudaEventCreate(&stop));

    // Warm up
    CHECK_CUDA(cudaMemset(d_ptr, 0, size));
    CHECK_CUDA(cudaDeviceSynchronize());

    // Test
    CHECK_CUDA(cudaEventRecord(start));
    for (int i = 0; i < 10; i++) {
        CHECK_CUDA(cudaMemset(d_ptr, i, size));
    }
    CHECK_CUDA(cudaEventRecord(stop));
    CHECK_CUDA(cudaEventSynchronize(stop));

    float milliseconds = 0;
    CHECK_CUDA(cudaEventElapsedTime(&milliseconds, start, stop));

    double bandwidth = (size * 10.0) / (milliseconds / 1000.0) / 1e9;

    printf("GPU %d: Device memory bandwidth: %.2f GB/s\n", device, bandwidth);

    CHECK_CUDA(cudaFree(d_ptr));
    CHECK_CUDA(cudaEventDestroy(start));
    CHECK_CUDA(cudaEventDestroy(stop));
}

void testP2PBandwidth(int dev1, int dev2, size_t size) {
    int canAccessPeer = 0;
    CHECK_CUDA(cudaDeviceCanAccessPeer(&canAccessPeer, dev1, dev2));

    if (!canAccessPeer) {
        printf("GPU %d -> GPU %d: P2P not supported\n", dev1, dev2);
        return;
    }

    CHECK_CUDA(cudaSetDevice(dev1));
    CHECK_CUDA(cudaDeviceEnablePeerAccess(dev2, 0));

    void *d_src, *d_dst;
    CHECK_CUDA(cudaSetDevice(dev1));
    CHECK_CUDA(cudaMalloc(&d_src, size));
    CHECK_CUDA(cudaSetDevice(dev2));
    CHECK_CUDA(cudaMalloc(&d_dst, size));

    cudaEvent_t start, stop;
    CHECK_CUDA(cudaEventCreate(&start));
    CHECK_CUDA(cudaEventCreate(&stop));

    CHECK_CUDA(cudaSetDevice(dev1));

    // Warm up
    CHECK_CUDA(cudaMemcpy(d_dst, d_src, size, cudaMemcpyDeviceToDevice));
    CHECK_CUDA(cudaDeviceSynchronize());

    // Test
    CHECK_CUDA(cudaEventRecord(start));
    for (int i = 0; i < 10; i++) {
        CHECK_CUDA(cudaMemcpy(d_dst, d_src, size, cudaMemcpyDeviceToDevice));
    }
    CHECK_CUDA(cudaEventRecord(stop));
    CHECK_CUDA(cudaEventSynchronize(stop));

    float milliseconds = 0;
    CHECK_CUDA(cudaEventElapsedTime(&milliseconds, start, stop));

    double bandwidth = (size * 10.0) / (milliseconds / 1000.0) / 1e9;

    printf("GPU %d -> GPU %d: P2P bandwidth: %.2f GB/s\n", dev1, dev2, bandwidth);

    CHECK_CUDA(cudaSetDevice(dev1));
    CHECK_CUDA(cudaFree(d_src));
    CHECK_CUDA(cudaSetDevice(dev2));
    CHECK_CUDA(cudaFree(d_dst));
    CHECK_CUDA(cudaEventDestroy(start));
    CHECK_CUDA(cudaEventDestroy(stop));

    CHECK_CUDA(cudaSetDevice(dev1));
    CHECK_CUDA(cudaDeviceDisablePeerAccess(dev2));
}

int main() {
    int deviceCount;
    CHECK_CUDA(cudaGetDeviceCount(&deviceCount));

    printf("Testing %d GPU(s)\n\n", deviceCount);

    size_t testSize = 1024 * 1024 * 1024; // 1GB

    // Test device memory bandwidth
    printf("=== Device Memory Bandwidth ===\n");
    for (int i = 0; i < deviceCount; i++) {
        testDeviceMemoryBandwidth(i, testSize);
    }

    printf("\n=== P2P Bandwidth ===\n");
    // Test P2P bandwidth
    for (int i = 0; i < deviceCount; i++) {
        for (int j = 0; j < deviceCount; j++) {
            if (i != j) {
                testP2PBandwidth(i, j, testSize);
            }
        }
    }

    return 0;
}
EOF

# Compile CUDA test
echo -e "${YELLOW}Compiling CUDA bandwidth test...${NC}"
if command -v nvcc &> /dev/null; then
    nvcc -o bandwidth_test bandwidth_test.cu

    echo -e "${YELLOW}Running CUDA bandwidth test...${NC}"
    ./bandwidth_test | tee bandwidth_output.txt

    echo ""
else
    echo -e "${YELLOW}nvcc not found, using CUDA samples if available${NC}"

    # Try to find CUDA samples
    CUDA_SAMPLES_PATH="/usr/local/cuda/samples"
    if [ -d "$CUDA_SAMPLES_PATH/1_Utilities/bandwidthTest" ]; then
        cd "$CUDA_SAMPLES_PATH/1_Utilities/bandwidthTest"
        make
        ./bandwidthTest | tee "$CUDA_TEST_DIR/bandwidth_output.txt"
    else
        echo -e "${RED}CUDA samples not found${NC}"
    fi
fi

# Parse results and create JSON
cd "$OUTPUT_DIR"

cat > "$RESULT_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "test_type": "cuda_bandwidth",
  "gpu_count": $GPU_COUNT,
  "gpus": [
EOF

# Add GPU information
for ((i=0; i<GPU_COUNT; i++)); do
    if [ $i -gt 0 ]; then
        echo "," >> "$RESULT_FILE"
    fi

    name=$(nvidia-smi --query-gpu=name --format=csv,noheader -i $i)
    memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i $i)

    cat >> "$RESULT_FILE" << EOF
    {
      "index": $i,
      "name": "$name",
      "memory_mb": $memory
    }
EOF
done

cat >> "$RESULT_FILE" << EOF

  ],
  "test_output": "See bandwidth_output.txt for detailed results",
  "status": "completed"
}
EOF

# Cleanup
rm -rf "$CUDA_TEST_DIR"

echo ""
echo -e "${GREEN}CUDA bandwidth test completed!${NC}"
echo "Results saved to: $RESULT_FILE"

# Display summary
echo ""
echo -e "${YELLOW}=== Summary ===${NC}"
cat "$RESULT_FILE" | python3 -m json.tool 2>/dev/null || cat "$RESULT_FILE"
