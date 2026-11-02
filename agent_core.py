# -*- coding: utf-8 -*-
"""
Agent 内核：一轮对话的完整流水线（主循环）。

  用户输入
    -> 1. 危机检测（硬规则，最高优先级，命中进入守护态）
    -> 2. Skill 路由（纯规则：crisis > 共情 > 开导 > 关系 > 闲聊）
    -> 3. 幽默档位控制（共情/危机强制压档，体现"知道什么时候不开玩笑"）
    -> 4. 记忆注入（[长期记忆] + [会话摘要] + [短期窗口] 三段固定模板）
    -> 5. 生成回复（危机走固定模板；其余走 LLM；无 Key 时离线演示文案兜底）
    -> 6. 记忆写回（画像更新 + 情绪时间线 + 幽默档位反馈调整）
    -> 7. 窗口滚动 / 摘要压缩
    -> 8. JSONL 日志落盘，返回结构化结果给前端
"""
import json
import random
import re
import time

import requests

from config import API_KEY, BASE_URL, MODEL, TEMPERATURE, TIMEOUT
from logger import log_turn
from memory import ConversationMemory, LongTermProfile, regex_profile_updates
from music import (find_local_song, folia_health, load_library, play_local,
                   search_bilibili)
from skills import (CLARIFY_MUSIC, CLARIFY_VAGUE, CRISIS_PAT, CRISIS_REPLY,
                    HUMOR_LEVEL_DESC, MUSIC_TRIGGER, PERSONA, SKILLS,
                    emotion_detect, route_skill)


# ---------------- LLM 客户端（requests 直连 OpenAI 兼容接口，无 SDK） ----------------

def llm_chat(messages: list[dict], temperature: float = TEMPERATURE) -> str | None:
    """调用 OpenAI 兼容 /chat/completions；无 Key 或调用失败返回 None（调用方走兜底）。"""
    if not API_KEY:
        return None
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "messages": messages, "temperature": temperature},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # 网络/配额/格式等一切异常：降级到兜底，不让对话中断
        log_turn({"user_id": "system", "type": "error", "err": str(e)[:200]})
        return None


def _parse_json_maybe(text: str | None) -> dict | None:
    """从 LLM 返回里尽力抠出一个 JSON 对象（模型偶尔会带解释文字）。"""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------- 离线演示文案（无 API Key 时兜底，保证全链路可演示） ----------------

OFFLINE_REPLIES = {
    "humor_chat": "（离线演示模式）在呢在呢～说吧，今天是想听吐槽还是想听段子？",
    "empathetic_listen": "（离线演示模式）听你说。这事儿搁谁身上都不好受，具体发生什么了？",
    "comfort_reframe": "（离线演示模式）打住——'总是'是每一次吗？上次不也有挺顺利的时候？",
    "relationship_talk": "（离线演示模式）先别急着上头。他具体做了什么、你想要什么，咱们捋一捋？",
}

# 画像抽取器 prompt：只允许输出 JSON，字段与 PROFILE_DEFAULTS 对齐
EXTRACT_SYS = (
    "你是用户画像抽取器。从最新一轮用户发言里提取画像更新，只输出JSON（不要其他文字），"
    "可选字段：nickname(昵称), watching([]在追的番/剧), liked_jokes([]用户喜欢的梗), "
    "disliked_jokes([]用户反感的梗), important_people([]提到的重要他人), "
    "triggers([]情绪触发点), self_label(自我描述)。没有新信息就输出 {}"
)

# 幽默反馈规则：用户发笑 -> 升档；用户嫌尬 -> 降档（这就是"依据用户反应做个性化适配"）
LAUGH_PAT = re.compile(r"(哈哈|笑死|乐死|233|太好笑|可乐)")
FLOP_PAT = re.compile(r"(不好笑|好尬|有点尬|别贫|尬住了)")


class EmotionalAgent:
    """一个用户一个实例：持有长期档案 + 会话记忆 + 会话内状态。"""

    def __init__(self, user_id: str = "demo", force_offline: bool = False):
        self.user_id = user_id
        self.profile = LongTermProfile(user_id)   # 第三层：长期档案（持久化）
        self.conv = ConversationMemory()          # 第一/二层：短期窗口 + 会话摘要
        self.crisis_mode = False                  # 守护态：激活后会话内持续
        self.empathy_streak = 0                   # 连续共情轮数（开导的前置条件）
        self.last_skill = ""                      # 上一轮命中的 Skill
        # 离线判定：显式指定，或没配 API Key
        self.force_offline = force_offline or not API_KEY

    # ---------- 主入口 ----------
    def handle(self, user_text: str) -> dict:
        t0 = time.time()

        # 1) 危机检测：硬规则最高优先级，命中即进入守护态（会话内保持）
        if CRISIS_PAT.search(user_text):
            self.crisis_mode = True

        # 2) Skill 路由（纯规则，结果可解释）
        skill, reason = route_skill(user_text, self.empathy_streak, self.crisis_mode)

        # 3) 幽默档位控制：按 Skill 场景决定"本轮实际生效的幽默档"
        profile_level = int(self.profile.data["humor_level"])
        if skill in ("crisis_guard", "empathetic_listen"):
            eff_level = 0                                   # 共情/危机：玩笑锁死
        elif skill in ("comfort_reframe", "relationship_talk"):
            eff_level = min(profile_level, 1)               # 开导/关系：最多轻幽默
        else:
            eff_level = profile_level                       # 闲聊：完全按画像
        humor_suppressed = eff_level < profile_level        # 是否发生了"压档"

        # 4) 记忆注入 + 5) 生成回复
        memory_read = []
        long_block = self.profile.prompt_block()
        if long_block:
            memory_read.append("长期档案")
        if self.conv.summary:
            memory_read.append("会话摘要")
        memory_read.append(f"短期窗口{len(self.conv.window)}条")

        music = None
        if skill == "crisis_guard":
            reply, offline = CRISIS_REPLY, False            # 固定模板，不依赖 LLM
        elif skill == "clarify_ask":
            # 主动澄清：固定反问模板（与危机守护同理——澄清话术固定化，稳定可复现）
            reply = CLARIFY_MUSIC if MUSIC_TRIGGER.search(user_text) else CLARIFY_VAGUE
            offline = False
        elif skill == "local_jukebox":
            # 私藏电台：探测 Folia -> 列出歌单卡片（具体曲目由前端展示，对话里只口语化报数）
            lib = load_library()
            online = folia_health()
            if re.search(r"(随机|随便)", user_text) and lib:
                # "随便来一首/随机来"：直接抽一首播放，不啰嗦
                local = random.choice(lib)
                play = play_local(local)
                via_txt = {"folia": "已经在播放器里为你放上了",
                           "web": "小狐电台这就为你放",
                           "none": "不过本地播放好像出了点问题，先看卡片吧"}[play["via"]]
                music = {"type": "local", "title": local["title"],
                         "artist": local["artist"], "tags": local["tags"],
                         "note": local["note"], "via": play["via"]}
                note = f"小狐私评：{local['note']}" if local["note"] else ""
                reply = f"那就来首《{local['title']}》吧，小狐私藏里的～\n{via_txt}。{note}"
            else:
                music = {"type": "playlist", "online": online,
                         "items": [{"title": s["title"], "artist": s["artist"],
                                    "tags": s["tags"]} for s in lib]}
                if not lib:
                    reply = "私藏歌单还空着呢……小狐攒歌是需要时间的，你先帮我把歌丢进 music 文件夹？"
                elif online:
                    reply = (f"私藏电台开机！小狐攒了 {len(lib)} 首压箱底的歌，播放器我也替你热好了。\n"
                             "点歌单卡片直接听，或者报歌名，这就为你端上来～")
                else:
                    reply = (f"私藏电台开机！小狐攒了 {len(lib)} 首压箱底的歌。\n"
                             "点歌单卡片或直接报歌名，这就用小狐电台为你放～")
            offline = False
        elif skill == "music_song":
            # 点歌：先查小狐私藏歌单（本地优先）-> 没有再转 B 站兜底（不依赖 LLM Key）
            keyword = MUSIC_TRIGGER.sub("", user_text).strip()
            keyword = keyword.replace("吧", "").replace("呗", "").replace("哈", "").replace("一下", "").strip()
            local = find_local_song(keyword or user_text)
            if local:
                play = play_local(local)
                via_txt = {"folia": "已经在播放器里为你放上了",
                           "web": "小狐电台这就为你放",
                           "none": "不过本地播放好像出了点问题，先看卡片吧"}[play["via"]]
                music = {"type": "local", "title": local["title"],
                         "artist": local["artist"], "tags": local["tags"],
                         "note": local["note"], "via": play["via"]}
                note = f"小狐私评：{local['note']}" if local["note"] else ""
                reply = f"找到了！《{local['title']}》就在小狐私藏歌单里，这就为您端上来～\n{via_txt}。{note}"
                offline = False
            else:
                found = search_bilibili(keyword)
                if found:
                    music = {**found, "type": "bili"}
                    reply = (f"抱歉呀，小狐私藏歌单里还没收录「{keyword}」……\n"
                             f"不过这难不倒我：给你找到 B 站播放量最高的一版——\n"
                             f"《{found['title']}》· {found['author']}\n"
                             f"播放 {found['play']:,}，点下面卡片就能去听～")
                else:
                    reply = f"私藏歌单里没有「{keyword}」，B 站也没搜到……换个更具体的歌名我再试试？"
                offline = False
        else:
            reply = llm_chat(self._build_prompt(skill, eff_level)) \
                if not self.force_offline else None
            offline = reply is None
            if offline:
                reply = OFFLINE_REPLIES[skill]

        # 6) 记忆写回（画像 / 情绪时间线 / 幽默档位适配）
        memory_write = self._write_back(user_text)

        # 7) 会话记忆更新 + 摘要压缩
        self.conv.add("user", user_text)
        self.conv.add("assistant", reply)
        if self.conv.need_summarize():
            self.conv.do_summarize(self._summarize)

        # 会话内状态推进：共情连击数只在"本轮确实在共情"时累加
        if skill == "empathetic_listen":
            self.empathy_streak += 1
        else:
            self.empathy_streak = 0
        self.last_skill = skill

        # 8) 结构化结果 + 日志落盘
        result = {
            "reply": reply,
            "skill": skill,
            "skill_title": SKILLS[skill]["title"],
            "reason": reason,
            "humor_level": eff_level,             # 本轮实际生效档位
            "profile_humor_level": profile_level, # 画像里的档位
            "humor_suppressed": humor_suppressed,
            "memory_read": memory_read,
            "memory_write": memory_write,
            "offline": offline,
            "music": music,
            "latency_ms": int((time.time() - t0) * 1000),
        }
        log_turn({"user_id": self.user_id, "type": "turn", "text": user_text, **result})
        return result

    # ---------- prompt 组装：注入路径固定成模板，答辩时可直接展示 ----------
    def _build_prompt(self, skill: str, humor_level: int) -> list[dict]:
        system = (
            PERSONA + "\n"
            + HUMOR_LEVEL_DESC[humor_level] + "\n\n"
            + f"【当前技能：{SKILLS[skill]['title']}】\n"
            + "【技能要点】" + SKILLS[skill]["knowledge"]
        )
        long_block = self.profile.prompt_block()
        if long_block:
            system += "\n\n[长期记忆-来自历史档案]\n" + long_block

        msgs = [{"role": "system", "content": system}]
        summary, _ = self.conv.context_blocks()
        if summary:
            msgs.append({"role": "system", "content": "[会话摘要-更早的对话]\n" + summary})
        # 短期窗口逐条作为对话历史注入
        for role, content in self.conv.window:
            msgs.append({"role": role, "content": content})
        return msgs

    # ---------- 记忆写回 ----------
    def _write_back(self, user_text: str) -> dict:
        writes = {}

        # a) 画像更新：在线走 LLM 抽取，离线走正则兜底；两条路都写日志
        updates = None
        if not self.force_offline:
            raw = llm_chat(
                [{"role": "system", "content": EXTRACT_SYS},
                 {"role": "user", "content": user_text}],
                temperature=0.1,
            )
            updates = _parse_json_maybe(raw)
        if updates is None:
            updates = regex_profile_updates(user_text)
        applied = self.profile.apply_updates(updates)
        if applied:
            writes["profile"] = applied

        # b) 情绪时间线：强度 >=1 才记录，避免闲聊刷屏
        intensity = emotion_detect(user_text)
        if intensity >= 1:
            writes["mood"] = self.profile.add_mood(intensity, user_text)

        # c) 幽默档位个性化适配：上一轮是玩梗陪聊时，根据用户反应升降档
        if self.last_skill == "humor_chat":
            old = int(self.profile.data["humor_level"])
            if LAUGH_PAT.search(user_text) and old < 3:
                self.profile.data["humor_level"] = old + 1
                self.profile.save()
                writes["humor_level"] = {"old": old, "new": old + 1, "why": "用户发笑，升档"}
            elif FLOP_PAT.search(user_text) and old > 0:
                self.profile.data["humor_level"] = old - 1
                self.profile.save()
                writes["humor_level"] = {"old": old, "new": old - 1, "why": "用户嫌尬，降档"}
        return writes

    # ---------- 摘要压缩回调 ----------
    def _summarize(self, text: str) -> str | None:
        return llm_chat(
            [{"role": "system",
              "content": "把下面的对话压缩成不超过3句话的摘要，保留关键事实和情绪事件：\n" + text}],
            temperature=0.3,
        )

    # ---------- 前端状态面板数据 ----------
    def get_state(self) -> dict:
        return {
            "user_id": self.user_id,
            "profile": self.profile.data,
            "profile_block": self.profile.prompt_block(),
            "summary": self.conv.summary,
            "window_len": len(self.conv.window),
            "overflow_len": len(self.conv.overflow),
            "crisis_mode": self.crisis_mode,
            "empathy_streak": self.empathy_streak,
            "last_skill": SKILLS.get(self.last_skill, {}).get("title", "（尚未开始）"),
            "offline": self.force_offline,
        }
