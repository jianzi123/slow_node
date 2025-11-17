#!/usr/bin/env python3
"""
Node Isolation Helper

Helps automatically update hostfiles and Kubernetes configurations
to exclude bad nodes identified by detection tools
"""

import json
import argparse
import sys
import os
import shutil
from datetime import datetime
from typing import List, Set


class NodeIsolator:
    """Helper to isolate bad nodes from cluster configuration"""

    def __init__(self, bad_nodes: List[str], backup: bool = True):
        self.bad_nodes = set(bad_nodes)
        self.backup = backup

    def update_hostfile(self, hostfile: str, output_file: str = None):
        """Update hostfile to exclude bad nodes"""
        if not os.path.exists(hostfile):
            print(f"Error: Hostfile not found: {hostfile}")
            return False

        # Backup original
        if self.backup:
            backup_file = f"{hostfile}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy(hostfile, backup_file)
            print(f"Backup created: {backup_file}")

        # Read and filter
        good_lines = []
        excluded_count = 0

        with open(hostfile, 'r') as f:
            for line in f:
                original_line = line
                line = line.strip()

                # Keep comments and empty lines
                if not line or line.startswith('#'):
                    good_lines.append(original_line)
                    continue

                # Extract hostname
                hostname = line.split()[0]

                # Check if this is a bad node
                if hostname in self.bad_nodes:
                    # Comment out this line
                    good_lines.append(f"# ISOLATED: {original_line}")
                    excluded_count += 1
                    print(f"  Excluding: {hostname}")
                else:
                    good_lines.append(original_line)

        # Write updated hostfile
        output_file = output_file or hostfile
        with open(output_file, 'w') as f:
            f.writelines(good_lines)

        print(f"\nUpdated hostfile: {output_file}")
        print(f"Excluded {excluded_count} nodes")

        return True

    def generate_k8s_node_selector(self) -> str:
        """Generate Kubernetes node selector to avoid bad nodes"""
        selector = {
            "nodeSelector": {
                "node-type": "gpu-compute"
            },
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [{
                            "matchExpressions": [{
                                "key": "kubernetes.io/hostname",
                                "operator": "NotIn",
                                "values": list(self.bad_nodes)
                            }]
                        }]
                    }
                }
            }
        }

        # Try to use yaml if available, otherwise use json
        try:
            import yaml
            return yaml.dump(selector, default_flow_style=False)
        except ImportError:
            return json.dumps(selector, indent=2)

    def generate_slurm_exclude(self) -> str:
        """Generate SLURM exclude directive"""
        return f"#SBATCH --exclude={','.join(sorted(self.bad_nodes))}"

    def generate_report(self, output_file: str):
        """Generate isolation report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "bad_nodes": list(self.bad_nodes),
            "count": len(self.bad_nodes),
            "actions": {
                "hostfile": "Updated to exclude bad nodes",
                "kubernetes": "Use nodeAffinity to avoid bad nodes",
                "slurm": f"Use --exclude={','.join(sorted(self.bad_nodes))}"
            }
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\nIsolation report saved to: {output_file}")


def load_bad_nodes_from_report(report_file: str) -> List[str]:
    """Load bad nodes from detection report"""
    with open(report_file, 'r') as f:
        data = json.load(f)

    bad_nodes = set()

    # Check different report formats
    if "bad_nodes" in data:
        bad_nodes.update(data["bad_nodes"])

    if "analysis" in data and "problematic_nodes" in data["analysis"]:
        for item in data["analysis"]["problematic_nodes"]:
            bad_nodes.add(item["node"])

    if "pairwise" in data and "analysis" in data["pairwise"]:
        for item in data["pairwise"]["analysis"].get("problematic_nodes", []):
            bad_nodes.add(item["node"])

    return list(bad_nodes)


def main():
    parser = argparse.ArgumentParser(
        description="Helper tool to isolate bad nodes from cluster configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update hostfile based on detection report
  %(prog)s --report bisection_report.json --hostfile hostfile

  # Manually specify bad nodes
  %(prog)s --nodes node1,node2,node3 --hostfile hostfile

  # Generate Kubernetes config snippet
  %(prog)s --report report.json --k8s-config

  # Generate SLURM exclude directive
  %(prog)s --report report.json --slurm-config
        """
    )

    parser.add_argument("--report", help="Detection report JSON file")
    parser.add_argument("--nodes", help="Comma-separated list of bad nodes")
    parser.add_argument("--hostfile", help="Hostfile to update")
    parser.add_argument("--output", help="Output file (default: update hostfile in-place)")
    parser.add_argument("--no-backup", action="store_true", help="Don't create backup")
    parser.add_argument("--k8s-config", action="store_true", help="Generate Kubernetes config")
    parser.add_argument("--slurm-config", action="store_true", help="Generate SLURM config")

    args = parser.parse_args()

    # Get bad nodes
    bad_nodes = []

    if args.report:
        if not os.path.exists(args.report):
            print(f"Error: Report file not found: {args.report}")
            sys.exit(1)
        bad_nodes = load_bad_nodes_from_report(args.report)
        print(f"Loaded {len(bad_nodes)} bad nodes from report")

    if args.nodes:
        bad_nodes.extend(args.nodes.split(','))

    if not bad_nodes:
        print("Error: No bad nodes specified")
        print("Use --report or --nodes to specify bad nodes")
        sys.exit(1)

    # Remove duplicates
    bad_nodes = list(set(bad_nodes))

    print(f"\nBad nodes to isolate ({len(bad_nodes)}):")
    for node in sorted(bad_nodes):
        print(f"  - {node}")
    print()

    isolator = NodeIsolator(bad_nodes, backup=not args.no_backup)

    # Update hostfile
    if args.hostfile:
        isolator.update_hostfile(args.hostfile, args.output)

    # Generate K8s config
    if args.k8s_config:
        print("\nKubernetes Node Affinity Configuration:")
        print("=" * 70)
        print(isolator.generate_k8s_node_selector())

    # Generate SLURM config
    if args.slurm_config:
        print("\nSLURM Exclude Directive:")
        print("=" * 70)
        print(isolator.generate_slurm_exclude())

    # Generate isolation report
    report_file = f"isolation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    isolator.generate_report(report_file)

    print("\n✓ Isolation complete!")


if __name__ == "__main__":
    main()
