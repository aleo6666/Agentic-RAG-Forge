"""RAG Forge Agentic Chat — 交互式对话 REPL。

用法：
    python scripts/chat.py            # 交互问答（Ctrl+C 或输入 exit 退出）
    echo "问题" | python scripts/chat.py   # 单次问答
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ragforge.agentic.agentic_pipeline import run_agentic_query


def ask(question: str) -> None:
    state = run_agentic_query(question)
    steps = [t["step"] for t in state.get("trace", [])]
    print(f"[决策] {' → '.join(steps)}")
    print(f"\n{state['answer']}\n")
    if state.get("citations"):
        print("来源:")
        for c in state["citations"]:
            print(f"  - {c['snippet'][:80]}")


def main() -> None:
    print("=" * 52)
    print("  RAG Forge — Agentic RAG 对话（DeepSeek 驱动）")
    print("  输入问题回车提问；输入 exit 退出")
    print("=" * 52)

    if not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                ask(line)
        return

    while True:
        try:
            q = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not q or q.lower() in ("exit", "quit", "q"):
            break
        try:
            ask(q)
        except Exception as e:  # 单问失败不中断会话
            print(f"[错误] {e}")


if __name__ == "__main__":
    main()
