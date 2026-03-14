#!/bin/bash
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""
for s in kwyre-train kwyre-train-2 kwyre-train-3 kwyre-train-4 kwyre-train-5 kwyre-train-6 kwyre-train-7; do
    LINE=$(tmux capture-pane -t "$s" -p -S -3 2>/dev/null | grep "it\]" | tail -1)
    if [ -z "$LINE" ]; then
        LINE=$(tmux capture-pane -t "$s" -p -S -3 2>/dev/null | grep -v "^\s*$" | tail -1)
    fi
    echo "$s: $LINE"
done
