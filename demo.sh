#!/bin/bash
# Demo script - Shows all features of the LLM Context Optimizer

echo "🚀 LLM Context Optimizer - Demo"
echo "================================"
echo ""

# Make executable
chmod +x optimize.py

echo "📊 1. Analyzing example conversation..."
./optimize.py analyze example_conversation.jsonl
echo ""

echo "📉 2. Optimizing to 1000 tokens..."
./optimize.py example_conversation.jsonl --target 1000 --output optimized_demo.jsonl
echo ""

echo "🔍 3. Extracting key facts..."
./optimize.py extract-facts example_conversation.jsonl | head -20
echo ""

echo "✅ Demo complete! Files created:"
echo "  - optimized_demo.jsonl (optimized conversation)"
echo ""
echo "Try running:"
echo "  ./optimize.py --help"
echo "  ./optimize.py example_conversation.jsonl --target 2000"
