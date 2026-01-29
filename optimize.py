#!/usr/bin/env python3
"""
LLM Context Optimizer - Intelligently manage context windows
Maximize useful token usage by keeping important info and dropping noise.
"""

import argparse
import json
import sys
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib


@dataclass
class Message:
    """Represents a conversation message"""
    role: str
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    priority: float = 5.0
    tokens: int = 0
    
    def __post_init__(self):
        if self.tokens == 0:
            self.tokens = estimate_tokens(self.content)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 chars for English)"""
    return len(text) // 4 + len(text.split()) // 2


def calculate_priority(msg: Message) -> float:
    """
    Calculate message importance (1-10 scale)
    Higher priority for:
    - Decisions and commitments
    - Questions and answers
    - Important facts and data
    - User preferences
    Lower priority for:
    - Greetings and farewells
    - Acknowledgments
    - Redundant confirmations
    """
    content = msg.content.lower()
    priority = 5.0
    
    # High priority indicators
    if any(word in content for word in ['decide', 'important', 'remember', 'prefer', 'always', 'never']):
        priority += 2.0
    if re.search(r'\?$', msg.content.strip()):  # Questions
        priority += 1.5
    if any(word in content for word in ['data', 'fact', 'result', 'conclusion']):
        priority += 1.5
    if any(word in content for word in ['error', 'bug', 'fix', 'issue', 'problem']):
        priority += 1.0
    if re.search(r'\d+', content):  # Contains numbers/data
        priority += 0.5
    
    # Low priority indicators
    if any(word in content for word in ['hello', 'hi ', 'bye', 'thanks', 'thank you']):
        priority -= 2.0
    if content in ['ok', 'okay', 'yes', 'no', 'sure', 'got it', 'understood']:
        priority -= 2.5
    if len(content) < 20:  # Very short messages
        priority -= 1.0
    if content.count('!') > 2:  # Excessive excitement
        priority -= 0.5
    
    # Role adjustments
    if msg.role == 'system':
        priority += 1.0
    
    return max(1.0, min(10.0, priority))


def semantic_hash(text: str) -> str:
    """Create a semantic fingerprint for deduplication"""
    # Normalize: lowercase, remove punctuation, sort words
    words = re.findall(r'\w+', text.lower())
    normalized = ' '.join(sorted(set(words)))
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def deduplicate_messages(messages: List[Message], threshold: float = 0.8) -> List[Message]:
    """
    Remove semantically similar/duplicate messages
    Returns unique messages with highest priority
    """
    hash_groups = defaultdict(list)
    
    for msg in messages:
        shash = semantic_hash(msg.content)
        hash_groups[shash].append(msg)
    
    unique = []
    for group in hash_groups.values():
        # Keep the highest priority message from each semantic group
        best = max(group, key=lambda m: m.priority)
        unique.append(best)
    
    return unique


def summarize_messages(messages: List[Message], max_summary_tokens: int = 500) -> Message:
    """
    Create a summary message from a group of messages
    Preserves key points and critical information
    """
    # Extract key information
    decisions = []
    facts = []
    questions = []
    
    for msg in messages:
        content = msg.content
        if any(word in content.lower() for word in ['decide', 'will', 'going to']):
            decisions.append(content)
        elif '?' in content:
            questions.append(content)
        elif any(word in content.lower() for word in ['fact', 'data', 'result']):
            facts.append(content)
    
    summary_parts = []
    if decisions:
        summary_parts.append("**Decisions:** " + "; ".join(decisions[:3]))
    if facts:
        summary_parts.append("**Key facts:** " + "; ".join(facts[:3]))
    if questions:
        summary_parts.append("**Questions:** " + "; ".join(questions[:2]))
    
    summary_text = "\n".join(summary_parts) if summary_parts else "General conversation summary."
    
    return Message(
        role="system",
        content=f"[SUMMARY] {summary_text}",
        priority=8.0,
        metadata={"type": "summary", "source_count": len(messages)}
    )


def optimize_context(
    messages: List[Message],
    target_tokens: int,
    preserve_recent: int = 10,
    min_priority: float = 5.0
) -> List[Message]:
    """
    Optimize conversation to fit within token budget
    
    Args:
        messages: List of conversation messages
        target_tokens: Target token count
        preserve_recent: Number of recent messages to keep at full fidelity
        min_priority: Minimum priority threshold for old messages
    
    Returns:
        Optimized message list
    """
    if not messages:
        return []
    
    # Calculate priorities
    for msg in messages:
        msg.priority = calculate_priority(msg)
    
    # Split into recent and old
    recent = messages[-preserve_recent:] if preserve_recent > 0 else []
    old = messages[:-preserve_recent] if preserve_recent > 0 else messages
    
    # Deduplicate old messages
    old_unique = deduplicate_messages(old)
    
    # Filter by priority
    old_filtered = [msg for msg in old_unique if msg.priority >= min_priority]
    
    # Sort by priority (keep highest)
    old_filtered.sort(key=lambda m: m.priority, reverse=True)
    
    # Build optimized list
    current_tokens = sum(msg.tokens for msg in recent)
    optimized_old = []
    
    for msg in old_filtered:
        if current_tokens + msg.tokens <= target_tokens:
            optimized_old.append(msg)
            current_tokens += msg.tokens
        else:
            break
    
    # If we still have too many tokens in old messages, create summary
    if old and len(optimized_old) < len(old_filtered) // 2:
        summary = summarize_messages(old_filtered[:20])
        if current_tokens + summary.tokens <= target_tokens:
            optimized_old = [summary] + optimized_old[:10]
    
    # Combine and sort by original order (approximately)
    result = optimized_old + recent
    
    return result


def analyze_conversation(messages: List[Message]) -> Dict[str, Any]:
    """Generate statistics about conversation"""
    total_tokens = sum(msg.tokens for msg in messages)
    
    priorities = [calculate_priority(msg) for msg in messages]
    
    role_dist = defaultdict(int)
    for msg in messages:
        role_dist[msg.role] += 1
    
    return {
        "total_messages": len(messages),
        "total_tokens": total_tokens,
        "avg_tokens_per_message": total_tokens // len(messages) if messages else 0,
        "priority_avg": sum(priorities) / len(priorities) if priorities else 0,
        "priority_high_count": sum(1 for p in priorities if p >= 7.0),
        "priority_low_count": sum(1 for p in priorities if p < 4.0),
        "role_distribution": dict(role_dist),
        "unique_semantic_groups": len(set(semantic_hash(msg.content) for msg in messages))
    }


def extract_facts(messages: List[Message]) -> List[Dict[str, Any]]:
    """Extract key facts and important information"""
    facts = []
    
    for i, msg in enumerate(messages):
        priority = calculate_priority(msg)
        
        # Extract high-priority content
        if priority >= 7.0:
            facts.append({
                "content": msg.content,
                "role": msg.role,
                "priority": priority,
                "timestamp": msg.timestamp,
                "position": i
            })
    
    return facts


def load_jsonl(filepath: Path) -> List[Message]:
    """Load conversation from JSONL file"""
    messages = []
    with open(filepath, 'r') as f:
        for line in f:
            data = json.loads(line.strip())
            messages.append(Message(**data))
    return messages


def save_jsonl(messages: List[Message], filepath: Path):
    """Save conversation to JSONL file"""
    with open(filepath, 'w') as f:
        for msg in messages:
            f.write(json.dumps(asdict(msg)) + '\n')


def main():
    # Check if first arg is a subcommand
    if len(sys.argv) > 1 and sys.argv[1] in ['analyze', 'extract-facts']:
        # Subcommand mode
        parser = argparse.ArgumentParser(
            description="LLM Context Optimizer - Manage context windows intelligently"
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Commands', required=True)
        
        # Analyze command
        analyze_parser = subparsers.add_parser('analyze', help='Show conversation statistics')
        analyze_parser.add_argument('input', type=str, help='Input JSONL file')
        
        # Extract facts command
        facts_parser = subparsers.add_parser('extract-facts', help='Extract key facts')
        facts_parser.add_argument('input', type=str, help='Input JSONL file')
        
        args = parser.parse_args()
        
        # Handle subcommands
        if args.command == 'analyze':
            messages = load_jsonl(Path(args.input))
            stats = analyze_conversation(messages)
            print(json.dumps(stats, indent=2))
            return
        
        if args.command == 'extract-facts':
            messages = load_jsonl(Path(args.input))
            facts = extract_facts(messages)
            print(json.dumps(facts, indent=2))
            return
    else:
        # Default optimize mode
        parser = argparse.ArgumentParser(
            description="LLM Context Optimizer - Manage context windows intelligently",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Optimize a conversation to 50k tokens
  %(prog)s conversation.jsonl --target 50000 --output optimized.jsonl
  
  # Analyze conversation statistics
  %(prog)s analyze conversation.jsonl
  
  # Extract key facts
  %(prog)s extract-facts conversation.jsonl > facts.json
  
  # Optimize with custom settings
  %(prog)s conversation.jsonl --target 30000 --preserve-recent 20 --min-priority 6.0
            """
        )
        
        parser.add_argument('input', type=str, help='Input JSONL file')
        parser.add_argument('--target', type=int, default=50000,
                            help='Target token count (default: 50000)')
        parser.add_argument('--output', type=str, help='Output JSONL file (default: stdout)')
        parser.add_argument('--preserve-recent', type=int, default=10,
                            help='Number of recent messages to preserve (default: 10)')
        parser.add_argument('--min-priority', type=float, default=5.0,
                            help='Minimum priority threshold (default: 5.0)')
        
        args = parser.parse_args()
    
    # Main optimization flow
    try:
        messages = load_jsonl(Path(args.input))
    except FileNotFoundError:
        print(f"Error: File '{args.input}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.input}': {e}", file=sys.stderr)
        sys.exit(1)
    
    # Optimize
    optimized = optimize_context(
        messages,
        target_tokens=args.target,
        preserve_recent=args.preserve_recent,
        min_priority=args.min_priority
    )
    
    # Output
    if args.output:
        save_jsonl(optimized, Path(args.output))
        
        # Print stats
        original_tokens = sum(msg.tokens for msg in messages)
        optimized_tokens = sum(msg.tokens for msg in optimized)
        compression = (1 - optimized_tokens / original_tokens) * 100
        
        print(f"Optimization complete:", file=sys.stderr)
        print(f"  Original: {len(messages)} messages, {original_tokens:,} tokens", file=sys.stderr)
        print(f"  Optimized: {len(optimized)} messages, {optimized_tokens:,} tokens", file=sys.stderr)
        print(f"  Compression: {compression:.1f}%", file=sys.stderr)
        print(f"  Output: {args.output}", file=sys.stderr)
    else:
        # Output to stdout
        for msg in optimized:
            print(json.dumps(asdict(msg)))


if __name__ == '__main__':
    main()
