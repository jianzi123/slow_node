#!/usr/bin/env python3
"""
MPI NCCL Test Wrapper
Provides a Python wrapper for running NCCL tests with detailed logging and analysis
"""

import subprocess
import json
import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict, Any


class NCCLTest:
    """NCCL bandwidth test runner"""

    def __init__(self, hostfile: str, gpus_per_node: int = 8, output_dir: str = "./results"):
        self.hostfile = hostfile
        self.gpus_per_node = gpus_per_node
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        os.makedirs(output_dir, exist_ok=True)

        # Read hostfile
        self.hosts = self._parse_hostfile()
        self.node_count = len(self.hosts)
        self.total_procs = self.node_count * self.gpus_per_node

    def _parse_hostfile(self) -> List[str]:
        """Parse MPI hostfile"""
        hosts = []
        with open(self.hostfile, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    host = line.split()[0]
                    hosts.append(host)
        return hosts

    def _build_mpi_command(self, test_binary: str, test_args: List[str]) -> List[str]:
        """Build MPI command"""
        cmd = [
            "mpirun",
            "--allow-run-as-root",
            "--hostfile", self.hostfile,
            "-np", str(self.total_procs),
            "--bind-to", "none",
            "--map-by", "slot",
            "-mca", "pml", "ob1",
            "-mca", "btl", "^openib",
            "-mca", "btl_tcp_if_include", "eth0",
            "--mca", "plm_rsh_no_tree_spawn", "1",
            "-x", "NCCL_DEBUG=INFO",
            "-x", "NCCL_IB_DISABLE=0",
            "-x", "NCCL_SOCKET_IFNAME=eth0",
            "-x", "NCCL_IB_HCA=mlx5",
            "-x", "NCCL_NET_GDR_LEVEL=5",
            "-x", "NCCL_IB_GID_INDEX=3",
            "-x", "LD_LIBRARY_PATH",
            test_binary,
        ]
        cmd.extend(test_args)
        return cmd

    def run_test(self, test_name: str, test_binary: str, test_args: List[str]) -> Dict[str, Any]:
        """Run a single NCCL test"""
        print(f"\n{'='*60}")
        print(f"Running {test_name}...")
        print(f"{'='*60}\n")

        output_file = os.path.join(self.output_dir, f"{test_name}_{self.timestamp}.txt")

        cmd = self._build_mpi_command(test_binary, test_args)

        print(f"Command: {' '.join(cmd)}\n")

        result = {
            "test_name": test_name,
            "command": ' '.join(cmd),
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "output_file": output_file,
        }

        try:
            with open(output_file, 'w') as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Stream output
                for line in process.stdout:
                    print(line, end='')
                    f.write(line)

                process.wait()

                result["success"] = process.returncode == 0
                result["return_code"] = process.returncode

                if result["success"]:
                    print(f"\n✓ {test_name} completed successfully")
                else:
                    print(f"\n✗ {test_name} failed with return code {process.returncode}")

        except Exception as e:
            result["error"] = str(e)
            print(f"\n✗ Error running {test_name}: {e}")

        return result

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all NCCL tests"""
        print(f"\nNCCL Distributed Bandwidth Test")
        print(f"Timestamp: {self.timestamp}")
        print(f"Nodes: {self.node_count}")
        print(f"GPUs per node: {self.gpus_per_node}")
        print(f"Total processes: {self.total_procs}")
        print(f"Output directory: {self.output_dir}\n")

        tests = [
            {
                "name": "all_reduce_perf",
                "binary": "/usr/local/bin/all_reduce_perf",
                "args": ["-b", "8", "-e", "8G", "-f", "2", "-g", "1", "-c", "1", "-n", "100"]
            },
            {
                "name": "all_gather_perf",
                "binary": "/usr/local/bin/all_gather_perf",
                "args": ["-b", "8", "-e", "1G", "-f", "2", "-g", "1", "-c", "1", "-n", "100"]
            },
            {
                "name": "broadcast_perf",
                "binary": "/usr/local/bin/broadcast_perf",
                "args": ["-b", "8", "-e", "1G", "-f", "2", "-g", "1", "-c", "1", "-n", "100"]
            },
            {
                "name": "reduce_scatter_perf",
                "binary": "/usr/local/bin/reduce_scatter_perf",
                "args": ["-b", "8", "-e", "1G", "-f", "2", "-g", "1", "-c", "1", "-n", "100"]
            },
        ]

        results = {
            "timestamp": self.timestamp,
            "hostfile": self.hostfile,
            "hosts": self.hosts,
            "node_count": self.node_count,
            "gpus_per_node": self.gpus_per_node,
            "total_processes": self.total_procs,
            "tests": []
        }

        for test in tests:
            result = self.run_test(test["name"], test["binary"], test["args"])
            results["tests"].append(result)

        # Save summary
        summary_file = os.path.join(self.output_dir, f"test_summary_{self.timestamp}.json")
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"All tests completed!")
        print(f"Summary saved to: {summary_file}")
        print(f"{'='*60}\n")

        return results


def main():
    parser = argparse.ArgumentParser(description="Run distributed NCCL bandwidth tests")
    parser.add_argument("--hostfile", required=True, help="MPI hostfile")
    parser.add_argument("--gpus-per-node", type=int, default=8, help="Number of GPUs per node")
    parser.add_argument("--output-dir", default="./results", help="Output directory")

    args = parser.parse_args()

    if not os.path.exists(args.hostfile):
        print(f"Error: Hostfile not found: {args.hostfile}")
        sys.exit(1)

    tester = NCCLTest(
        hostfile=args.hostfile,
        gpus_per_node=args.gpus_per_node,
        output_dir=args.output_dir
    )

    results = tester.run_all_tests()

    # Print summary
    print("\nSummary:")
    print(f"  Total tests: {len(results['tests'])}")
    passed = sum(1 for t in results['tests'] if t['success'])
    print(f"  Passed: {passed}")
    print(f"  Failed: {len(results['tests']) - passed}")

    sys.exit(0 if passed == len(results['tests']) else 1)


if __name__ == "__main__":
    main()
