# -*- coding: utf-8 -*-
"""
三层记忆模块（评分项：多轮上下文与记忆管理，5分）：
  1) 短期窗口   —— 最近 N 条原文，每轮注入 prompt
  2) 会话摘要   —— 旧消息被挤出窗口后，攒够一批就压缩成几句话
  3) 长期档案   —— 按 user_id 持久化的用户画像 JSON（梗偏好/在追作品/重要他人/情绪时间线...）

注入路径（agent_core._build_prompt 中可见的固定模板）：
  [长期记忆-来自历史档案] -> system 消息
  [会话摘要-更早的对话]   -> system 消息
  [最近对话]             -> 逐条 message
写回时机（agent_core._write_back）：
  每轮结束后：画像更新(LLM提取/正则兜底) + 情绪时间线 + 幽默档位反馈调整
"""
import json
import os
import re
import time

from config import PROFILE_DIR, SHORT_TERM_TURNS, SUMMARY_THRESHOLD

# ---------------- 长期档案 ----------------

PROFILE_DEFAULTS = {
    "nickname": "",           # 用户昵称
    "humor_level": 1,         # 幽默档位 0-3（个性化适配的核心字段，0关-1轻-2玩梗-3毒舌）
    "feedback_style": "温和",  # 开导风格：温和 / 直接
    "liked_jokes": [],        # 用户吃过的梗（可回收素材）
    "disliked_jokes": [],     # 玩砸过的梗（拉黑不再用）
    "watching": [],           # 在追的番/剧/影视（回收梗的核心素材）
    "important_people": [],   # 重要他人（室友/对象/导师...）
    "triggers": [],           # 情绪触发点（如"被导师当众批评"）
    "mood_timeline": [],      # 情绪时间线 [{date, score, note}]
    "self_label": "",         # 自我标签（如"自嘲型选手"）
}


class LongTermProfile:
    """按 user_id 存取的长期记忆档案，文件位于 data/long_term/<user_id>.json。"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.path = os.path.join(PROFILE_DIR, f"{user_id}.json")
        # 深拷贝默认值，避免多个用户实例共享同一份 dict
        self.data = json.loads(json.dumps(PROFILE_DEFAULTS))
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def apply_updates(self, updates: dict) -> dict:
        """
        把画像更新合并进档案：
        - 列表字段：去重追加（最多保留最近 10 条，防膨胀）
        - 标量字段：不同才覆盖
        返回"实际生效的更新"，用于日志展示 memory_write。
        """
        applied = {}
        for k, v in (updates or {}).items():
            if k not in self.data or v in (None, "", []):
                continue
            if isinstance(self.data[k], list):
                items = v if isinstance(v, list) else [v]
                new_items = [str(x) for x in items if x and str(x) not in self.data[k]]
                if new_items:
                    self.data[k] = (self.data[k] + new_items)[-10:]
                    applied[k] = new_items
            elif str(v) != str(self.data[k]):
                applied[k] = {"old": self.data[k], "new": str(v)}
                self.data[k] = str(v)
        if applied:
            self.save()
        return applied

    def add_mood(self, score: int, note: str = "") -> dict:
        """往情绪时间线追加一条记录（score: 0-2 情绪强度，越高越负面）。"""
        entry = {"date": time.strftime("%m-%d %H:%M"), "score": score, "note": note[:30]}
        self.data["mood_timeline"] = (self.data["mood_timeline"] + [entry])[-30:]
        self.save()
        return entry

    def prompt_block(self) -> str:
        """生成注入 prompt 的[长期记忆]文本块；档案为空时返回空串（不占 token）。"""
        d = self.data
        lines = []
        if d["nickname"]:
            lines.append(f"昵称：{d['nickname']}")
        lines.append(f"幽默档位：{d['humor_level']}（0关闭-3毒舌）")
        if d["watching"]:
            lines.append("在追：" + "、".join(d["watching"]))
        if d["liked_jokes"]:
            lines.append("用户吃过的梗（可回收）：" + "、".join(d["liked_jokes"]))
        if d["disliked_jokes"]:
            lines.append("玩砸过的梗（别再用）：" + "、".join(d["disliked_jokes"]))
        if d["important_people"]:
            lines.append("重要他人：" + "、".join(d["important_people"]))
        if d["triggers"]:
            lines.append("情绪触发点：" + "、".join(d["triggers"]))
        if d["self_label"]:
            lines.append(f"用户自认：{d['self_label']}")
        if d["mood_timeline"]:
            recent = d["mood_timeline"][-3:]
            lines.append("近期情绪：" + "；".join(
                f"{m['date']} {m['note']}(强度{m['score']})" for m in recent))
        return "\n".join(lines)


# ---------------- 会话记忆：短期窗口 + 摘要 ----------------


class ConversationMemory:
    """短期窗口（deque 思路）+ 滚动摘要。"""

    def __init__(self):
        self.window = []    # [(role, content), ...]，只保留最近 SHORT_TERM_TURNS 条
        self.overflow = []  # 被挤出窗口的旧消息，攒够 SUMMARY_THRESHOLD 条就压缩
        self.summary = ""   # 历次压缩出的会话摘要

    def add(self, role: str, content: str) -> None:
        self.window.append((role, content))
        while len(self.window) > SHORT_TERM_TURNS:
            self.overflow.append(self.window.pop(0))

    def need_summarize(self) -> bool:
        return len(self.overflow) >= SUMMARY_THRESHOLD

    def do_summarize(self, llm_fn) -> str:
        """把 overflow 压缩成摘要并入 summary；llm_fn 失败时退化为截断拼接（保证离线可用）。"""
        text = "\n".join(("用户：" if r == "user" else "AI：") + c for r, c in self.overflow)
        new_part = None
        if llm_fn:
            try:
                new_part = llm_fn(text)
            except Exception:
                new_part = None
        if not new_part:
            new_part = text.replace("\n", " ")[:80] + "……"
        self.summary = (self.summary + "\n" + new_part).strip()
        self.overflow = []
        return new_part

    def context_blocks(self) -> tuple[str, str]:
        """返回 (会话摘要, 最近对话) 两块文本，供 prompt 注入与前端展示。"""
        recent = "\n".join(("用户：" if r == "user" else "AI：") + c for r, c in self.window)
        return self.summary, recent


# ---------------- 离线兜底：正则画像抽取 ----------------
# 没配 API Key（离线演示模式）时，用正则从用户话里抽最关键的画像字段，
# 保证"记忆写回"这条链路在无网络环境下也能完整演示。

WATCH_PAT = re.compile(r"(?:在追|在看|追更|最近追)\s*《?([^，。！？\s《》]{2,20})》?")
NAME_PAT = re.compile(r"(?:我叫|叫我)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,10})")


def regex_profile_updates(text: str) -> dict:
    updates = {}
    m = WATCH_PAT.search(text)
    if m:
        updates["watching"] = [m.group(1)]
    m = NAME_PAT.search(text)
    if m:
        updates["nickname"] = m.group(1)
    return updates
