#!/bin/bash
# Sequential batch: 2x abundant (7B) + 2x no-cooperation (7B)
set -e
cd "$(dirname "$0")"

echo "=== BATCH START: $(date) ==="

echo ""
echo "=== [1/4] 7B Abundant v1 ==="
python run.py --config configs/abundant.yaml --mode llm --model Qwen/Qwen2.5-7B-Instruct-AWQ --game-id llm_7b_abundant_001

echo ""
echo "=== [2/4] 7B Abundant v2 ==="
python run.py --config configs/abundant.yaml --mode llm --model Qwen/Qwen2.5-7B-Instruct-AWQ --game-id llm_7b_abundant_002

echo ""
echo "=== [3/4] 7B No-Cooperation v1 ==="
python run.py --config configs/no_cooperation.yaml --mode llm --model Qwen/Qwen2.5-7B-Instruct-AWQ --game-id llm_7b_nocoop_001

echo ""
echo "=== [4/4] 7B No-Cooperation v2 ==="
python run.py --config configs/no_cooperation.yaml --mode llm --model Qwen/Qwen2.5-7B-Instruct-AWQ --game-id llm_7b_nocoop_002

echo ""
echo "=== BATCH COMPLETE: $(date) ==="
