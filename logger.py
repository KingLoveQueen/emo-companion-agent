# -*- coding: utf-8 -*-
"""
JSONL 全量日志模块（评分项：可核对的运行记录）。
每轮对话的 路由结果 / 幽默抑制 / 记忆读写 / LLM延迟 全部落盘，
答辩时可以逐条指着日志说清"机制是否真的按设计运行"。
文件格式：每行一个 JSON 对象，按天分文件 data/logs/turn_YYYYMMDD.jsonl
危机事件会额外追加到 data/logs/crisis_events.jsonl（高危单独留痕）。
"""
import json
import os
import time

from config import LOG_DIR


def _today_file() -> str:
    """按天命名的日志文件路径。"""
    return os.path.join(LOG_DIR, time.strftime("turn_%Y%m%d.jsonl"))


def log_turn(record: dict) -> None:
    """记录一条事件。record 常用字段：user_id / type / skill / reason / reply ..."""
    record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **record}
    with open(_today_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # 危机事件单独高危落一条，方便事后检索与演示"安全边界留痕"
    if record.get("skill") == "crisis_guard":
        with open(os.path.join(LOG_DIR, "crisis_events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_recent(n: int = 50, user_id: str | None = None) -> list[dict]:
    """倒序读取最近 n 条日志（供前端日志面板展示），可按 user_id 过滤。"""
    path = _today_file()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # 半截行直接跳过，保证面板不崩
        if user_id and rec.get("user_id") != user_id:
            continue
        out.append(rec)
        if len(out) >= n:
            break
    return out
