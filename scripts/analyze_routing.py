#!/usr/bin/env python3
"""Analyze routing telemetry logs.

Usage:
    python scripts/analyze_routing.py [--log-dir ./routing_logs] [--days 7]
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


def load_routing_logs(log_dir: Path, days: int = 7) -> List[Dict]:
    """Load routing decision logs from the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = []

    for log_file in sorted(log_dir.glob("routing_*.jsonl")):
        with open(log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if timestamp >= cutoff:
                        entries.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"Skipping invalid entry in {log_file}: {e}")

    return entries


def analyze_routing_accuracy(entries: List[Dict]) -> Dict:
    """Analyze routing accuracy metrics."""
    total = len(entries)
    if total == 0:
        return {"total_queries": 0}

    # Confidence distribution
    confidence_counts = Counter(e["confidence_level"] for e in entries)

    # Selection method distribution
    method_counts = Counter(e["selection_method"] for e in entries)

    # Tool usage
    tool_usage = Counter()
    for entry in entries:
        for tool in entry["selected_tools"]:
            tool_usage[tool] += 1

    # Prerequisite chain usage
    prereq_usage = sum(
        1 for e in entries
        if e.get("prerequisite_injection") and len(e["prerequisite_injection"]) > 0
    )

    # Average scores
    scores = []
    for entry in entries:
        if entry.get("candidates"):
            top_score = entry["candidates"][0].get("final_score", 0)
            scores.append(top_score)

    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "total_queries": total,
        "confidence_distribution": dict(confidence_counts),
        "selection_methods": dict(method_counts),
        "top_10_tools": dict(tool_usage.most_common(10)),
        "prerequisite_chain_usage": prereq_usage,
        "prerequisite_chain_pct": (prereq_usage / total * 100) if total > 0 else 0,
        "average_top_score": avg_score,
    }


def analyze_query_patterns(entries: List[Dict]) -> Dict:
    """Analyze common query patterns."""
    queries = [e["query"] for e in entries]

    # Most common queries
    query_counts = Counter(queries)

    # Query length distribution
    lengths = [len(q.split()) for q in queries]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    return {
        "unique_queries": len(set(queries)),
        "top_10_queries": dict(query_counts.most_common(10)),
        "avg_query_length_words": avg_length,
    }


def analyze_low_confidence_queries(entries: List[Dict], limit: int = 10) -> List[Dict]:
    """Find queries with lowest confidence scores."""
    low_confidence = []

    for entry in entries:
        if not entry.get("candidates"):
            continue

        top_candidate = entry["candidates"][0]
        score = top_candidate.get("final_score", 0)

        if score < 2.0:  # Below "high" threshold
            low_confidence.append({
                "query": entry["query"],
                "score": score,
                "selected_tool": entry["selected_tools"][0] if entry["selected_tools"] else None,
                "confidence_level": entry["confidence_level"],
            })

    # Sort by score (lowest first)
    low_confidence.sort(key=lambda x: x["score"])

    return low_confidence[:limit]


def print_report(log_dir: Path, days: int):
    """Print comprehensive routing analysis report."""
    entries = load_routing_logs(log_dir, days)

    print("=" * 80)
    print(f"ROUTING TELEMETRY ANALYSIS ({days} days)")
    print("=" * 80)
    print(f"Log directory: {log_dir}")
    print(f"Time range: Last {days} days")
    print()

    # Overall metrics
    accuracy = analyze_routing_accuracy(entries)
    print("── Overall Metrics ──")
    print(f"Total queries processed: {accuracy['total_queries']}")
    print(f"Average top score: {accuracy['average_top_score']:.2f}")
    print(f"Prerequisite chain usage: {accuracy['prerequisite_chain_usage']} ({accuracy['prerequisite_chain_pct']:.1f}%)")
    print()

    # Confidence distribution
    print("── Confidence Distribution ──")
    for level, count in accuracy['confidence_distribution'].items():
        pct = count / accuracy['total_queries'] * 100
        print(f"  {level:8s}: {count:4d} ({pct:5.1f}%)")
    print()

    # Selection methods
    print("── Selection Methods ──")
    for method, count in accuracy['selection_methods'].items():
        pct = count / accuracy['total_queries'] * 100
        print(f"  {method:20s}: {count:4d} ({pct:5.1f}%)")
    print()

    # Top tools
    print("── Top 10 Tools Used ──")
    for tool, count in accuracy['top_10_tools'].items():
        print(f"  {tool:40s}: {count:4d}")
    print()

    # Query patterns
    patterns = analyze_query_patterns(entries)
    print("── Query Patterns ──")
    print(f"Unique queries: {patterns['unique_queries']}")
    print(f"Average query length: {patterns['avg_query_length_words']:.1f} words")
    print()

    print("Top 10 Most Common Queries:")
    for query, count in patterns['top_10_queries'].items():
        print(f"  [{count:3d}x] {query}")
    print()

    # Low confidence queries
    low_conf = analyze_low_confidence_queries(entries, limit=10)
    if low_conf:
        print("── Low Confidence Queries (Bottom 10) ──")
        for item in low_conf:
            print(f"  Score {item['score']:.2f} ({item['confidence_level']}): {item['query']}")
            print(f"    → Selected: {item['selected_tool']}")
        print()

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Analyze routing telemetry logs")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("./routing_logs"),
        help="Directory containing routing log files"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )

    args = parser.parse_args()

    if not args.log_dir.exists():
        print(f"Error: Log directory not found: {args.log_dir}")
        return 1

    print_report(args.log_dir, args.days)
    return 0


if __name__ == "__main__":
    exit(main())
