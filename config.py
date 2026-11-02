# -*- coding: utf-8 -*-
"""
全局配置：LLM 接口、记忆参数、路径。
设计原则（与作业要求一致）：
- 零 SDK 依赖：只用 requests 直连 OpenAI 兼容接口
- 机制透明：所有可调参数集中在这一处，方便答辩时解释
"""
import os

# ---------- LLM 接口配置（OpenAI 兼容格式，可换任何兼容服务） ----------
# 优先读环境变量，避免把 Key 写死进代码；也可以直接把 Key 填在下面的默认值里
API_KEY     = os.environ.get("LLM_API_KEY", "")  # 优先读环境变量；留空则自动进入【离线演示模式】（全链路仍可演示）
BASE_URL    = os.environ.get("LLM_BASE_URL", "https://apihub.agnes-ai.cn/v1")
MODEL       = os.environ.get("LLM_MODEL", "agnes-3.0-flash")   # 国际节点用 apihub.agnes-ai.com/v1
TEMPERATURE = 0.9        # 陪聊场景温度调高，回复更活泼（危机模板不走 LLM，不受影响）
TIMEOUT     = 30         # 单次请求超时（秒）

# ---------- 记忆参数 ----------
SHORT_TERM_TURNS  = 8    # 短期窗口保留最近多少条消息（约 4 轮对话）
SUMMARY_THRESHOLD = 6    # 被挤出窗口的消息攒够多少条时，压缩成会话摘要

# ---------- 路径 ----------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
PROFILE_DIR = os.path.join(DATA_DIR, "long_term")   # 长期记忆（按 user_id 分文件）
LOG_DIR     = os.path.join(DATA_DIR, "logs")        # JSONL 运行日志
TESTCASES   = os.path.join(DATA_DIR, "testcases.yaml")
MUSIC_INDEX = os.path.join(DATA_DIR, "music_index.json")  # 歌单元数据（情绪标签/注解）

# ---------- 本地私藏曲库 + Folia 播放器（local_jukebox Skill） ----------
# 播放链路三级降级：Folia Stage 在线 -> 系统默认播放器 -> 文案兜底
MUSIC_DIR       = os.path.join(BASE_DIR, "music")                       # 歌曲文件夹（往里放歌即可，无需改代码）
IMAGE_DIR       = os.path.join(BASE_DIR, "image")                       # 封面插画文件夹（music_index.json 的 cover 字段引用）
FOLIA_STAGE_URL = os.environ.get("FOLIA_STAGE_URL", "http://127.0.0.1:32107")  # Folia 桌面端 Stage API 地址
FOLIA_TOKEN     = os.environ.get("FOLIA_TOKEN", "")                     # Folia 设置里开启 Stage Mode 后复制的 Bearer token
FOLIA_EXE       = r"D:\folia\Folia.exe"                                 # Folia 播放器路径（已安装）；未启动时小狐可自动拉起

for d in (DATA_DIR, PROFILE_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)
