#!/usr/bin/env python3
"""
Advanced Slow Node Detection with Binary Search and Pairwise Testing

This tool implements industry best practices from:
- Google Cloud Cluster Health Scanner: pairwise NCCL testing
- Microsoft Azure DGX: binary search to isolate underperforming nodes
- Together.AI: systematic validation from individual → pairs → groups → full cluster

Key Features:
1. Binary search algorithm to efficiently find slow nodes
2. Pairwise node testing to isolate problematic nodes
3. Incremental testing: 1 node → 2 nodes → N/2 nodes → N nodes
4. Automatic bad node isolation recommendations
"""

import subprocess
import json
import argparse
import sys
import os
import itertools
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime
from collections import defaultdict
import numpy as np


class BisectionNodeTester:
    """
    Binary search based node testing to identify slow nodes

    Algorithm:
    1. Test all nodes together - if good, exit
    2. If bad, split into two halves, test each half
    3. For bad half, recursively split and test
    4. Continue until individual bad nodes are identified
    """

    def __init__(self, hostfile: str, gpus_per_node: int = 8,
                 threshold_gb_s: float = None, output_dir: str = "./results"):
        self.hostfile = hostfile
        self.gpus_per_node = gpus_per_node
        self.threshold_gb_s = threshold_gb_s
        self.output_dir = output_dir
        self.hosts = self._parse_hostfile()
        self.test_history = []
        self.bad_nodes = set()
        self.good_nodes = set()

        os.makedirs(output_dir, exist_ok=True)

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

    def _create_temp_hostfile(self, nodes: List[str]) -> str:
        """Create temporary hostfile for subset of nodes"""
        temp_file = os.path.join(self.output_dir, f"hostfile_temp_{len(nodes)}nodes.txt")
        with open(temp_file, 'w') as f:
            for node in nodes:
                f.write(f"{node} slots={self.gpus_per_node}\n")
        return temp_file

    def _run_nccl_test(self, nodes: List[str], test_name: str = "bisection") -> Dict[str, Any]:
        """Run NCCL test on subset of nodes"""
        print(f"\n{'='*70}")
        print(f"Testing {len(nodes)} nodes: {', '.join(nodes[:3])}{'...' if len(nodes) > 3 else ''}")
        print(f"{'='*70}")

        temp_hostfile = self._create_temp_hostfile(nodes)
        total_procs = len(nodes) * self.gpus_per_node

        output_file = os.path.join(
            self.output_dir,
            f"nccl_{test_name}_{len(nodes)}nodes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        # Run NCCL all_reduce test
        cmd = [
            "mpirun",
            "--allow-run-as-root",
            "--hostfile", temp_hostfile,
            "-np", str(total_procs),
            "--bind-to", "none",
            "--map-by", "slot",
            "-mca", "pml", "ob1",
            "-mca", "btl", "^openib",
            "-x", "NCCL_DEBUG=WARN",  # Less verbose for bisection
            "-x", "NCCL_IB_DISABLE=0",
            "-x", "LD_LIBRARY_PATH",
            "/usr/local/bin/all_reduce_perf",
            "-b", "1G",  # Test with 1GB size for speed
            "-e", "1G",
            "-f", "2",
            "-g", "1",
            "-c", "1",
            "-n", "20",  # Fewer iterations for speed
        ]

        result = {
            "nodes": nodes,
            "node_count": len(nodes),
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "success": False,
        }

        try:
            print(f"Running: {' '.join(cmd[:10])}... (full command logged)")

            with open(output_file, 'w') as f:
                process = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=300,  # 5 min timeout
                    text=True
                )

                result["return_code"] = process.returncode
                result["success"] = (process.returncode == 0)

            # Parse bandwidth from output
            bandwidth = self._parse_bandwidth(output_file)
            result["bandwidth_gb_s"] = bandwidth

            # Determine if this is a "good" result
            if bandwidth and self.threshold_gb_s:
                result["is_good"] = bandwidth >= self.threshold_gb_s
            else:
                result["is_good"] = result["success"]

            status = "✓ GOOD" if result.get("is_good") else "✗ BAD"
            bw_str = f"{bandwidth:.2f} GB/s" if bandwidth else "N/A"
            print(f"{status} - Bandwidth: {bw_str}")

        except subprocess.TimeoutExpired:
            result["error"] = "Test timeout"
            result["is_good"] = False
            print("✗ TIMEOUT")
        except Exception as e:
            result["error"] = str(e)
            result["is_good"] = False
            print(f"✗ ERROR: {e}")

        self.test_history.append(result)

        # Cleanup temp hostfile
        if os.path.exists(temp_hostfile):
            os.remove(temp_hostfile)

        return result

    def _parse_bandwidth(self, output_file: str) -> float:
        """Parse bandwidth from NCCL test output"""
        try:
            with open(output_file, 'r') as f:
                content = f.read()

            # Look for "Avg bus bandwidth" line
            import re
            # Pattern: size count type redop time algbw busbw
            pattern = r'^\s*\d+\s+\d+\s+\w+\s+\w+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'

            bandwidths = []
            for line in content.split('\n'):
                match = re.search(pattern, line)
                if match:
                    busbw = float(match.group(3))
                    bandwidths.append(busbw)

            if bandwidths:
                # Return average of all measurements
                return np.mean(bandwidths)

        except Exception as e:
            print(f"Warning: Failed to parse bandwidth: {e}")

        return None

    def _bisect_test(self, nodes: List[str], depth: int = 0) -> Set[str]:
        """
        Recursively test node subsets using binary search
        Returns set of bad nodes
        """
        indent = "  " * depth

        if len(nodes) == 0:
            return set()

        # Base case: single node
        if len(nodes) == 1:
            result = self._run_nccl_test(nodes, f"single_node_depth{depth}")
            if not result.get("is_good"):
                print(f"{indent}→ Node {nodes[0]} is BAD")
                return {nodes[0]}
            else:
                print(f"{indent}→ Node {nodes[0]} is GOOD")
                return set()

        # Test current group
        result = self._run_nccl_test(nodes, f"group_depth{depth}")

        if result.get("is_good"):
            # All nodes in this group are good
            print(f"{indent}→ All {len(nodes)} nodes are GOOD")
            self.good_nodes.update(nodes)
            return set()

        # Group has issues - split and recurse
        print(f"{indent}→ Group of {len(nodes)} nodes has issues, splitting...")

        mid = len(nodes) // 2
        left_nodes = nodes[:mid]
        right_nodes = nodes[mid:]

        print(f"{indent}Testing left half ({len(left_nodes)} nodes)...")
        left_bad = self._bisect_test(left_nodes, depth + 1)

        print(f"{indent}Testing right half ({len(right_nodes)} nodes)...")
        right_bad = self._bisect_test(right_nodes, depth + 1)

        return left_bad | right_bad

    def run_bisection_detection(self) -> Dict[str, Any]:
        """
        Run binary search based slow node detection
        """
        print("\n" + "="*70)
        print("BINARY SEARCH SLOW NODE DETECTION")
        print("="*70)
        print(f"Total nodes: {len(self.hosts)}")
        print(f"GPUs per node: {self.gpus_per_node}")
        print(f"Threshold: {self.threshold_gb_s} GB/s" if self.threshold_gb_s else "Threshold: Auto")
        print("")

        # If no threshold set, run a quick baseline test to establish it
        if not self.threshold_gb_s:
            print("Running baseline test to establish threshold...")
            baseline = self._run_nccl_test(self.hosts[:2], "baseline")  # Test 2 nodes
            if baseline.get("bandwidth_gb_s"):
                # Set threshold to 80% of baseline
                self.threshold_gb_s = baseline["bandwidth_gb_s"] * 0.8
                print(f"Threshold set to: {self.threshold_gb_s:.2f} GB/s (80% of baseline)")

        # Start bisection
        start_time = datetime.now()
        bad_nodes = self._bisect_test(self.hosts)
        end_time = datetime.now()

        # Generate report
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_nodes": len(self.hosts),
            "total_tests": len(self.test_history),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "threshold_gb_s": self.threshold_gb_s,
            "bad_nodes": list(bad_nodes),
            "good_nodes": list(self.good_nodes),
            "test_history": self.test_history,
        }

        # Save report
        report_file = os.path.join(
            self.output_dir,
            f"bisection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print("\n" + "="*70)
        print("BISECTION DETECTION COMPLETE")
        print("="*70)
        print(f"Total tests run: {len(self.test_history)}")
        print(f"Duration: {report['duration_seconds']:.1f} seconds")
        print(f"Bad nodes found: {len(bad_nodes)}")
        if bad_nodes:
            for node in bad_nodes:
                print(f"  ✗ {node}")
        else:
            print("  ✓ No bad nodes detected!")
        print(f"\nReport saved to: {report_file}")

        return report


class PairwiseNodeTester:
    """
    Pairwise node testing to identify communication issues between specific node pairs
    Inspired by Google Cloud Cluster Health Scanner
    """

    def __init__(self, hostfile: str, gpus_per_node: int = 8, output_dir: str = "./results"):
        self.hostfile = hostfile
        self.gpus_per_node = gpus_per_node
        self.output_dir = output_dir
        self.hosts = self._parse_hostfile()
        self.pairwise_results = {}

        os.makedirs(output_dir, exist_ok=True)

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

    def run_pairwise_tests(self, max_pairs: int = None) -> Dict[str, Any]:
        """
        Run NCCL tests on all pairs of nodes
        """
        print("\n" + "="*70)
        print("PAIRWISE NODE TESTING")
        print("="*70)

        # Generate all pairs
        all_pairs = list(itertools.combinations(self.hosts, 2))

        if max_pairs and len(all_pairs) > max_pairs:
            print(f"Limiting to {max_pairs} pairs (out of {len(all_pairs)} total)")
            # Randomly sample pairs
            import random
            all_pairs = random.sample(all_pairs, max_pairs)
        else:
            print(f"Testing {len(all_pairs)} node pairs")

        tester = BisectionNodeTester(
            self.hostfile,
            self.gpus_per_node,
            output_dir=self.output_dir
        )

        for i, (node1, node2) in enumerate(all_pairs, 1):
            print(f"\n[{i}/{len(all_pairs)}] Testing pair: {node1} ↔ {node2}")

            result = tester._run_nccl_test([node1, node2], f"pair_{i}")

            pair_key = f"{node1}↔{node2}"
            self.pairwise_results[pair_key] = {
                "nodes": [node1, node2],
                "bandwidth_gb_s": result.get("bandwidth_gb_s"),
                "success": result.get("success"),
                "timestamp": result.get("timestamp"),
            }

        # Analyze results
        analysis = self._analyze_pairwise_results()

        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_pairs": len(all_pairs),
            "pairwise_results": self.pairwise_results,
            "analysis": analysis,
        }

        report_file = os.path.join(
            self.output_dir,
            f"pairwise_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print("\n" + "="*70)
        print("PAIRWISE TESTING COMPLETE")
        print("="*70)
        print(f"Report saved to: {report_file}")

        self._print_analysis(analysis)

        return report

    def _analyze_pairwise_results(self) -> Dict[str, Any]:
        """Analyze pairwise test results to find problematic nodes"""
        node_stats = defaultdict(lambda: {"bandwidths": [], "failures": 0, "tests": 0})

        for pair_key, result in self.pairwise_results.items():
            nodes = result["nodes"]
            bw = result.get("bandwidth_gb_s")
            success = result.get("success")

            for node in nodes:
                node_stats[node]["tests"] += 1
                if bw:
                    node_stats[node]["bandwidths"].append(bw)
                if not success:
                    node_stats[node]["failures"] += 1

        # Calculate statistics
        analysis = {
            "node_statistics": {},
            "problematic_nodes": [],
        }

        all_avg_bw = []
        for node, stats in node_stats.items():
            if stats["bandwidths"]:
                avg_bw = np.mean(stats["bandwidths"])
                std_bw = np.std(stats["bandwidths"])
                all_avg_bw.append(avg_bw)

                analysis["node_statistics"][node] = {
                    "average_bandwidth_gb_s": float(avg_bw),
                    "std_bandwidth_gb_s": float(std_bw),
                    "failure_count": stats["failures"],
                    "total_tests": stats["tests"],
                    "failure_rate": stats["failures"] / stats["tests"] if stats["tests"] > 0 else 0,
                }

        # Identify problematic nodes (those with below average performance)
        if all_avg_bw:
            mean_bw = np.mean(all_avg_bw)
            std_bw = np.std(all_avg_bw)
            threshold = mean_bw - 2 * std_bw  # 2 sigma

            analysis["overall_mean_bandwidth"] = float(mean_bw)
            analysis["overall_std_bandwidth"] = float(std_bw)
            analysis["threshold_bandwidth"] = float(threshold)

            for node, stats in analysis["node_statistics"].items():
                if stats["average_bandwidth_gb_s"] < threshold or stats["failure_rate"] > 0.2:
                    analysis["problematic_nodes"].append({
                        "node": node,
                        "average_bandwidth_gb_s": stats["average_bandwidth_gb_s"],
                        "failure_rate": stats["failure_rate"],
                        "reason": "Low bandwidth" if stats["average_bandwidth_gb_s"] < threshold else "High failure rate"
                    })

        return analysis

    def _print_analysis(self, analysis: Dict[str, Any]):
        """Print analysis results"""
        print("\nNode Performance Summary:")
        print("-" * 70)

        if "node_statistics" in analysis:
            for node, stats in sorted(analysis["node_statistics"].items()):
                bw = stats["average_bandwidth_gb_s"]
                failures = stats["failure_count"]
                total = stats["total_tests"]
                print(f"{node:30s} | BW: {bw:6.2f} GB/s | Failures: {failures}/{total}")

        if analysis.get("problematic_nodes"):
            print("\n⚠ Problematic Nodes Detected:")
            for item in analysis["problematic_nodes"]:
                print(f"  ✗ {item['node']}: {item['reason']} ({item['average_bandwidth_gb_s']:.2f} GB/s)")
        else:
            print("\n✓ No problematic nodes detected!")


def main():
    parser = argparse.ArgumentParser(
        description="Advanced slow node detection using binary search and pairwise testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Binary search detection
  %(prog)s --hostfile hostfile --mode bisection

  # Pairwise testing
  %(prog)s --hostfile hostfile --mode pairwise

  # Both methods
  %(prog)s --hostfile hostfile --mode both --threshold 200
        """
    )

    parser.add_argument("--hostfile", required=True, help="MPI hostfile")
    parser.add_argument("--mode", choices=["bisection", "pairwise", "both"],
                       default="bisection", help="Detection mode")
    parser.add_argument("--gpus-per-node", type=int, default=8,
                       help="Number of GPUs per node")
    parser.add_argument("--threshold", type=float, default=None,
                       help="Bandwidth threshold in GB/s (auto-detect if not specified)")
    parser.add_argument("--output-dir", default="./results",
                       help="Output directory")
    parser.add_argument("--max-pairs", type=int, default=None,
                       help="Maximum number of pairs to test (for large clusters)")

    args = parser.parse_args()

    if not os.path.exists(args.hostfile):
        print(f"Error: Hostfile not found: {args.hostfile}")
        sys.exit(1)

    results = {}

    # Run bisection detection
    if args.mode in ["bisection", "both"]:
        tester = BisectionNodeTester(
            args.hostfile,
            args.gpus_per_node,
            args.threshold,
            args.output_dir
        )
        results["bisection"] = tester.run_bisection_detection()

    # Run pairwise testing
    if args.mode in ["pairwise", "both"]:
        tester = PairwiseNodeTester(
            args.hostfile,
            args.gpus_per_node,
            args.output_dir
        )
        results["pairwise"] = tester.run_pairwise_tests(args.max_pairs)

    # Print final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)

    bad_nodes = set()

    if "bisection" in results:
        bisect_bad = results["bisection"].get("bad_nodes", [])
        if bisect_bad:
            print(f"\nBisection detected {len(bisect_bad)} bad nodes:")
            for node in bisect_bad:
                print(f"  ✗ {node}")
            bad_nodes.update(bisect_bad)

    if "pairwise" in results:
        pair_bad = results["pairwise"]["analysis"].get("problematic_nodes", [])
        if pair_bad:
            print(f"\nPairwise testing detected {len(pair_bad)} problematic nodes:")
            for item in pair_bad:
                print(f"  ✗ {item['node']}: {item['reason']}")
                bad_nodes.add(item['node'])

    if bad_nodes:
        print(f"\n⚠ ACTION REQUIRED: Isolate these nodes from the cluster:")
        for node in sorted(bad_nodes):
            print(f"  - {node}")
        sys.exit(1)
    else:
        print("\n✓ All nodes performing well!")
        sys.exit(0)


if __name__ == "__main__":
    main()
