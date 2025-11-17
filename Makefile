# Makefile for NCCL Slow Node Detection Tool

.PHONY: help build push test clean

# Configuration
IMAGE_NAME ?= nccl-mpi
IMAGE_TAG ?= latest
REGISTRY ?= your-registry.com
FULL_IMAGE = $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# Paths
SCRIPTS_DIR = scripts
DOCKER_DIR = docker
K8S_DIR = k8s

help:
	@echo "NCCL Slow Node Detection Tool"
	@echo ""
	@echo "Available targets:"
	@echo "  build         - Build Docker image"
	@echo "  push          - Push Docker image to registry"
	@echo "  test-single   - Run single node tests"
	@echo "  test-distributed - Run distributed NCCL tests"
	@echo "  detect        - Run slow node detection analysis"
	@echo "  clean         - Clean up results and temp files"
	@echo "  deploy-k8s    - Deploy to Kubernetes"
	@echo "  setup         - Setup environment and permissions"
	@echo ""
	@echo "Configuration:"
	@echo "  IMAGE_NAME=$(IMAGE_NAME)"
	@echo "  IMAGE_TAG=$(IMAGE_TAG)"
	@echo "  REGISTRY=$(REGISTRY)"

build:
	@echo "Building Docker image..."
	docker build -f $(DOCKER_DIR)/Dockerfile.nccl-mpi \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		-t $(FULL_IMAGE) \
		.
	@echo "Build complete: $(IMAGE_NAME):$(IMAGE_TAG)"

push: build
	@echo "Pushing image to registry..."
	docker push $(FULL_IMAGE)
	@echo "Push complete"

setup:
	@echo "Setting up environment..."
	mkdir -p results visualizations
	chmod +x $(SCRIPTS_DIR)/single_node/*.sh
	chmod +x $(SCRIPTS_DIR)/distributed/*.sh
	chmod +x $(SCRIPTS_DIR)/analysis/*.py
	@echo "Setup complete"

test-single:
	@echo "Running single node tests..."
	@if [ ! -d "results" ]; then mkdir -p results; fi
	OUTPUT_DIR=./results $(SCRIPTS_DIR)/single_node/test_ib_bandwidth.sh
	OUTPUT_DIR=./results $(SCRIPTS_DIR)/single_node/test_cuda_bandwidth.sh
	OUTPUT_DIR=./results $(SCRIPTS_DIR)/single_node/test_gpu_p2p.sh
	@echo "Single node tests complete"

test-distributed:
	@echo "Running distributed NCCL tests..."
	@if [ ! -f "hostfile" ]; then \
		echo "Error: hostfile not found. Copy from configs/hostfile.template"; \
		exit 1; \
	fi
	HOSTFILE=./hostfile OUTPUT_DIR=./results $(SCRIPTS_DIR)/distributed/run_nccl_test.sh
	@echo "Distributed tests complete"

detect:
	@echo "Running slow node detection..."
	@LATEST=$$(ls -t results/nccl_test_*.json 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "Error: No test results found. Run 'make test-distributed' first"; \
		exit 1; \
	fi; \
	$(SCRIPTS_DIR)/analysis/detect_slow_nodes.py $$LATEST --output results/slow_node_report.txt --verbose
	@echo "Detection complete"

visualize:
	@echo "Creating visualizations..."
	@LATEST=$$(ls -t results/nccl_test_*.json 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "Error: No test results found"; \
		exit 1; \
	fi; \
	$(SCRIPTS_DIR)/analysis/visualize_results.py $$LATEST --output-dir visualizations --dashboard
	@echo "Visualizations created in visualizations/"

deploy-k8s:
	@echo "Deploying to Kubernetes..."
	kubectl apply -f $(K8S_DIR)/nccl-test-job.yaml
	@echo "Deployment complete. Check status with: kubectl get pods"

clean:
	@echo "Cleaning up..."
	rm -rf results/* visualizations/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete"

.DEFAULT_GOAL := help
