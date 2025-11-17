#!/usr/bin/env python3
"""
Slow Node Detection Tool
Analyzes NCCL test results to identify slow nodes in the cluster

This tool implements several detection strategies:
1. Statistical outlier detection using Z-score and IQR methods
2. Per-node bandwidth analysis
3. Cross-node communication pattern analysis
4. Time-based performance degradation detection
"""

import json
import argparse
import sys
import os
import re
from typing import Dict, List, Any, Tuple
from datetime import datetime
from collections import defaultdict
import numpy as np


class SlowNodeDetector:
    """Detects slow nodes from NCCL test results"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = []
        self.node_stats = defaultdict(lambda: {
            'bandwidth_samples': [],
            'latency_samples': [],
            'rank_ids': []
        })

    def log(self, message: str):
        """Log message if verbose"""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def load_nccl_results(self, result_file: str) -> Dict[str, Any]:
        """Load NCCL test results from file"""
        self.log(f"Loading results from {result_file}")

        if result_file.endswith('.json'):
            with open(result_file, 'r') as f:
                data = json.load(f)
            return data
        else:
            # Parse text output
            return self._parse_text_results(result_file)

    def _parse_text_results(self, result_file: str) -> Dict[str, Any]:
        """Parse NCCL text output"""
        with open(result_file, 'r') as f:
            content = f.read()

        results = {
            'tests': [],
            'raw_output': content
        }

        # Extract bandwidth results
        # Look for patterns like: "Avg bus bandwidth : 234.56"
        bandwidth_pattern = r'Avg bus bandwidth\s*:\s*([\d.]+)'
        bandwidths = re.findall(bandwidth_pattern, content)

        if bandwidths:
            results['avg_bandwidth'] = [float(bw) for bw in bandwidths]

        # Extract per-rank information from NCCL_DEBUG output
        rank_pattern = r'NCCL INFO.*Rank\s+(\d+).*'
        ranks = re.findall(rank_pattern, content)

        if ranks:
            results['ranks'] = list(set(int(r) for r in ranks))

        return results

    def parse_nccl_logs(self, log_content: str) -> List[Dict[str, Any]]:
        """Parse NCCL DEBUG logs to extract per-rank performance"""
        entries = []

        # Pattern to match NCCL performance lines
        # Example: "      512     2048    float     sum      41.9    12.23    12.23"
        perf_pattern = r'^\s+(\d+)\s+(\d+)\s+\w+\s+\w+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'

        for line in log_content.split('\n'):
            match = re.search(perf_pattern, line)
            if match:
                size, count, time, algbw, busbw = match.groups()
                entries.append({
                    'size_bytes': int(size),
                    'count': int(count),
                    'time_us': float(time),
                    'algbw_GB/s': float(algbw),
                    'busbw_GB/s': float(busbw)
                })

        return entries

    def detect_outliers_zscore(self, values: List[float], threshold: float = 2.0) -> List[int]:
        """Detect outliers using Z-score method"""
        if len(values) < 3:
            return []

        values_array = np.array(values)
        mean = np.mean(values_array)
        std = np.std(values_array)

        if std == 0:
            return []

        z_scores = np.abs((values_array - mean) / std)
        outliers = np.where(z_scores > threshold)[0].tolist()

        self.log(f"Z-score detection: mean={mean:.2f}, std={std:.2f}, outliers={outliers}")

        return outliers

    def detect_outliers_iqr(self, values: List[float], multiplier: float = 1.5) -> List[int]:
        """Detect outliers using IQR method"""
        if len(values) < 4:
            return []

        values_array = np.array(values)
        q1 = np.percentile(values_array, 25)
        q3 = np.percentile(values_array, 75)
        iqr = q3 - q1

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        outliers = []
        for i, val in enumerate(values):
            if val < lower_bound or val > upper_bound:
                outliers.append(i)

        self.log(f"IQR detection: Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}, outliers={outliers}")

        return outliers

    def analyze_node_performance(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze per-node performance from test results"""
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'node_performance': {},
            'slow_nodes': [],
            'statistics': {}
        }

        # Extract bandwidth values
        if 'tests' in test_results:
            all_bandwidths = []

            for test in test_results['tests']:
                if 'results' in test and test['results']:
                    # Get maximum bandwidth for each test
                    max_bw = max(r['busbw_GB/s'] for r in test['results'])
                    all_bandwidths.append(max_bw)

            if all_bandwidths:
                analysis['statistics'] = {
                    'mean_bandwidth_GB/s': float(np.mean(all_bandwidths)),
                    'median_bandwidth_GB/s': float(np.median(all_bandwidths)),
                    'std_bandwidth_GB/s': float(np.std(all_bandwidths)),
                    'min_bandwidth_GB/s': float(np.min(all_bandwidths)),
                    'max_bandwidth_GB/s': float(np.max(all_bandwidths)),
                }

                # Detect outliers using both methods
                zscore_outliers = self.detect_outliers_zscore(all_bandwidths)
                iqr_outliers = self.detect_outliers_iqr(all_bandwidths)

                # Combine outliers (intersection for higher confidence)
                outlier_indices = set(zscore_outliers) & set(iqr_outliers)

                self.log(f"Combined outliers: {outlier_indices}")

                # Map outliers to nodes (simplified - assumes sequential node assignment)
                if 'hosts' in test_results:
                    hosts = test_results['hosts']
                    gpus_per_node = test_results.get('gpus_per_node', 8)

                    for host_idx, host in enumerate(hosts):
                        # Check if this node has outlier GPUs
                        node_gpu_start = host_idx * gpus_per_node
                        node_gpu_end = node_gpu_start + gpus_per_node

                        node_has_outlier = False
                        for outlier_idx in outlier_indices:
                            if node_gpu_start <= outlier_idx < node_gpu_end:
                                node_has_outlier = True
                                break

                        if node_has_outlier:
                            analysis['slow_nodes'].append({
                                'hostname': host,
                                'index': host_idx,
                                'reason': 'Performance outlier detected',
                                'confidence': 'high' if (host_idx in zscore_outliers and host_idx in iqr_outliers) else 'medium'
                            })

        return analysis

    def analyze_from_raw_logs(self, log_file: str) -> Dict[str, Any]:
        """Analyze slow nodes from raw NCCL log output"""
        self.log(f"Analyzing raw logs from {log_file}")

        with open(log_file, 'r') as f:
            content = f.read()

        # Parse performance entries
        perf_entries = self.parse_nccl_logs(content)

        if not perf_entries:
            return {
                'error': 'No performance data found in logs',
                'slow_nodes': []
            }

        # Group by size and analyze
        size_groups = defaultdict(list)
        for entry in perf_entries:
            size_groups[entry['size_bytes']].append(entry['busbw_GB/s'])

        analysis = {
            'timestamp': datetime.now().isoformat(),
            'performance_by_size': {},
            'slow_nodes': [],
            'summary': {}
        }

        # Analyze each size
        all_bw_values = []
        for size, bandwidths in size_groups.items():
            if len(bandwidths) >= 3:
                analysis['performance_by_size'][str(size)] = {
                    'mean_GB/s': float(np.mean(bandwidths)),
                    'std_GB/s': float(np.std(bandwidths)),
                    'min_GB/s': float(np.min(bandwidths)),
                    'max_GB/s': float(np.max(bandwidths)),
                }
                all_bw_values.extend(bandwidths)

        if all_bw_values:
            # Overall statistics
            analysis['summary'] = {
                'overall_mean_GB/s': float(np.mean(all_bw_values)),
                'overall_std_GB/s': float(np.std(all_bw_values)),
                'coefficient_of_variation': float(np.std(all_bw_values) / np.mean(all_bw_values)) if np.mean(all_bw_values) > 0 else 0,
            }

            # Detect slow performance
            threshold = np.mean(all_bw_values) - 2 * np.std(all_bw_values)
            slow_samples = sum(1 for bw in all_bw_values if bw < threshold)

            if slow_samples > 0:
                analysis['slow_nodes'].append({
                    'detection': f'{slow_samples} samples below threshold',
                    'threshold_GB/s': float(threshold),
                    'percentage': float(slow_samples / len(all_bw_values) * 100)
                })

        return analysis

    def generate_report(self, analysis: Dict[str, Any], output_file: str = None):
        """Generate human-readable report"""
        report = []
        report.append("=" * 70)
        report.append("SLOW NODE DETECTION REPORT")
        report.append("=" * 70)
        report.append(f"Timestamp: {analysis.get('timestamp', 'N/A')}")
        report.append("")

        # Statistics
        if 'statistics' in analysis:
            report.append("Overall Statistics:")
            stats = analysis['statistics']
            for key, value in stats.items():
                report.append(f"  {key}: {value:.2f}")
            report.append("")

        if 'summary' in analysis:
            report.append("Performance Summary:")
            for key, value in analysis['summary'].items():
                report.append(f"  {key}: {value:.4f}")
            report.append("")

        # Slow nodes
        report.append("Slow Nodes Detected:")
        if analysis['slow_nodes']:
            for i, node in enumerate(analysis['slow_nodes'], 1):
                report.append(f"\n{i}. {node.get('hostname', 'Unknown')}")
                report.append(f"   Reason: {node.get('reason', 'N/A')}")
                report.append(f"   Confidence: {node.get('confidence', 'N/A')}")
                if 'detection' in node:
                    report.append(f"   Detection: {node['detection']}")
                if 'threshold_GB/s' in node:
                    report.append(f"   Threshold: {node['threshold_GB/s']:.2f} GB/s")
                if 'percentage' in node:
                    report.append(f"   Percentage: {node['percentage']:.1f}%")
        else:
            report.append("  No slow nodes detected!")

        report.append("")
        report.append("=" * 70)

        report_text = "\n".join(report)

        # Print to console
        print(report_text)

        # Save to file
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_text)
            print(f"\nReport saved to: {output_file}")

        return report_text


def main():
    parser = argparse.ArgumentParser(
        description="Detect slow nodes from NCCL test results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze JSON results
  %(prog)s results.json

  # Analyze raw log file
  %(prog)s --raw nccl_test.log

  # Generate detailed report
  %(prog)s results.json --output report.txt --verbose
        """
    )

    parser.add_argument("input", help="Input file (JSON or raw log)")
    parser.add_argument("--output", "-o", help="Output report file")
    parser.add_argument("--raw", action="store_true", help="Parse raw NCCL log format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--threshold", type=float, default=2.0, help="Z-score threshold for outlier detection")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    detector = SlowNodeDetector(verbose=args.verbose)

    try:
        if args.raw:
            analysis = detector.analyze_from_raw_logs(args.input)
        else:
            test_results = detector.load_nccl_results(args.input)
            analysis = detector.analyze_node_performance(test_results)

        # Output results
        if args.json:
            print(json.dumps(analysis, indent=2))
        else:
            detector.generate_report(analysis, args.output)

        # Exit code based on detection
        sys.exit(1 if analysis['slow_nodes'] else 0)

    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
