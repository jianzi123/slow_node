#!/usr/bin/env python3
"""
NCCL Test Results Visualization Tool
Creates charts and graphs to visualize bandwidth test results and identify slow nodes
"""

import json
import argparse
import sys
import os
from typing import Dict, List, Any
import numpy as np

# Try to import visualization libraries
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("Warning: matplotlib/seaborn not available. Install with: pip install matplotlib seaborn")


class NCCLVisualizer:
    """Visualize NCCL test results"""

    def __init__(self, output_dir: str = "./visualizations"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        if HAS_PLOT:
            sns.set_style("whitegrid")
            sns.set_palette("husl")

    def plot_bandwidth_by_size(self, results: Dict[str, Any], filename: str = "bandwidth_by_size.png"):
        """Plot bandwidth vs message size"""
        if not HAS_PLOT:
            print("Plotting not available")
            return

        fig, ax = plt.subplots(figsize=(12, 6))

        for test in results.get('tests', []):
            if 'results' in test and test['results']:
                sizes = [r['size_bytes'] for r in test['results']]
                bandwidths = [r['busbw_GB/s'] for r in test['results']]

                ax.plot(sizes, bandwidths, marker='o', label=test['test_type'], linewidth=2)

        ax.set_xlabel('Message Size (bytes)', fontsize=12)
        ax.set_ylabel('Bus Bandwidth (GB/s)', fontsize=12)
        ax.set_title('NCCL Bandwidth vs Message Size', fontsize=14, fontweight='bold')
        ax.set_xscale('log')
        ax.grid(True, alpha=0.3)
        ax.legend()

        output_path = os.path.join(self.output_dir, filename)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"Saved plot: {output_path}")

    def plot_node_comparison(self, node_stats: Dict[str, List[float]], filename: str = "node_comparison.png"):
        """Plot comparison of node performance"""
        if not HAS_PLOT:
            print("Plotting not available")
            return

        fig, ax = plt.subplots(figsize=(12, 6))

        nodes = list(node_stats.keys())
        bandwidths = [np.mean(stats) for stats in node_stats.values()]
        errors = [np.std(stats) for stats in node_stats.values()]

        x = np.arange(len(nodes))
        bars = ax.bar(x, bandwidths, yerr=errors, capsize=5, alpha=0.7)

        # Color bars based on performance
        mean_bw = np.mean(bandwidths)
        std_bw = np.std(bandwidths)
        threshold = mean_bw - 2 * std_bw

        for i, (bar, bw) in enumerate(zip(bars, bandwidths)):
            if bw < threshold:
                bar.set_color('red')
                bar.set_alpha(0.8)

        ax.set_xlabel('Node', fontsize=12)
        ax.set_ylabel('Average Bandwidth (GB/s)', fontsize=12)
        ax.set_title('Node Performance Comparison', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(nodes, rotation=45, ha='right')
        ax.axhline(y=threshold, color='r', linestyle='--', label=f'Slow threshold: {threshold:.2f} GB/s')
        ax.legend()

        output_path = os.path.join(self.output_dir, filename)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"Saved plot: {output_path}")

    def plot_heatmap(self, matrix_data: np.ndarray, labels: List[str], filename: str = "bandwidth_heatmap.png"):
        """Plot bandwidth heatmap"""
        if not HAS_PLOT:
            print("Plotting not available")
            return

        fig, ax = plt.subplots(figsize=(10, 8))

        sns.heatmap(matrix_data, annot=True, fmt='.2f', cmap='RdYlGn',
                   xticklabels=labels, yticklabels=labels,
                   ax=ax, cbar_kws={'label': 'Bandwidth (GB/s)'})

        ax.set_title('Node-to-Node Bandwidth Matrix', fontsize=14, fontweight='bold')

        output_path = os.path.join(self.output_dir, filename)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"Saved plot: {output_path}")

    def create_summary_dashboard(self, results: Dict[str, Any]):
        """Create a summary dashboard with multiple plots"""
        if not HAS_PLOT:
            print("Dashboard creation not available")
            return

        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

        # Plot 1: Bandwidth by size
        ax1 = fig.add_subplot(gs[0, :])
        for test in results.get('tests', []):
            if 'results' in test and test['results']:
                sizes = [r['size_bytes'] for r in test['results']]
                bandwidths = [r['busbw_GB/s'] for r in test['results']]
                ax1.plot(sizes, bandwidths, marker='o', label=test['test_type'], linewidth=2)

        ax1.set_xlabel('Message Size (bytes)')
        ax1.set_ylabel('Bus Bandwidth (GB/s)')
        ax1.set_title('Bandwidth vs Message Size', fontweight='bold')
        ax1.set_xscale('log')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Statistics
        ax2 = fig.add_subplot(gs[1, 0])
        if 'tests' in results and results['tests']:
            all_bw = []
            for test in results['tests']:
                if 'results' in test:
                    all_bw.extend([r['busbw_GB/s'] for r in test['results']])

            if all_bw:
                ax2.hist(all_bw, bins=30, alpha=0.7, edgecolor='black')
                ax2.axvline(np.mean(all_bw), color='r', linestyle='--', linewidth=2, label=f'Mean: {np.mean(all_bw):.2f}')
                ax2.set_xlabel('Bandwidth (GB/s)')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Bandwidth Distribution', fontweight='bold')
                ax2.legend()

        # Plot 3: Summary statistics table
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.axis('tight')
        ax3.axis('off')

        stats_data = []
        if 'tests' in results:
            for test in results['tests'][:5]:  # Limit to 5 tests
                if 'results' in test and test['results']:
                    max_bw = max(r['busbw_GB/s'] for r in test['results'])
                    min_bw = min(r['busbw_GB/s'] for r in test['results'])
                    avg_bw = np.mean([r['busbw_GB/s'] for r in test['results']])
                    stats_data.append([test['test_type'], f'{min_bw:.2f}', f'{avg_bw:.2f}', f'{max_bw:.2f}'])

        if stats_data:
            table = ax3.table(cellText=stats_data,
                            colLabels=['Test', 'Min (GB/s)', 'Avg (GB/s)', 'Max (GB/s)'],
                            cellLoc='center',
                            loc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 2)

        ax3.set_title('Performance Summary', fontweight='bold', pad=20)

        output_path = os.path.join(self.output_dir, 'dashboard.png')
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"Saved dashboard: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize NCCL test results")
    parser.add_argument("input", help="Input JSON results file")
    parser.add_argument("--output-dir", "-o", default="./visualizations", help="Output directory for plots")
    parser.add_argument("--dashboard", action="store_true", help="Create summary dashboard")

    args = parser.parse_args()

    if not HAS_PLOT:
        print("Error: Visualization libraries not installed")
        print("Install with: pip install matplotlib seaborn")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    try:
        with open(args.input, 'r') as f:
            results = json.load(f)

        visualizer = NCCLVisualizer(output_dir=args.output_dir)

        print(f"Creating visualizations in {args.output_dir}...")

        # Create plots
        visualizer.plot_bandwidth_by_size(results)

        if args.dashboard:
            visualizer.create_summary_dashboard(results)

        print("\nVisualization complete!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
