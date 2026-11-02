# -*- coding: utf-8 -*-
"""
音乐类 Skill 的领域实现（两套，职责分离）：

1) search_bilibili  —— 点歌（music_song）：调 B 站公开搜索接口，返回「播放量最高」的视频链接+封面。
   不依赖任何付费 API Key：B 站 search/all/v2 免签名、封面走公开 CDN。
   仅课堂作业演示：视频 / 音频版权归原作者与 B 站所有。

2) 本地私藏曲库（local_jukebox）：扫描 music/ 文件夹 + data/music_index.json 元数据，
   支持歌名模糊匹配；播放走三级降级：
     Folia Stage API（全屏沉浸歌词播放器，本地回环） -> os.startfile 系统默认播放器 -> 失败兜底。
   Folia 是开源播放器（github.com/chthollyphile/folia-major，AGPL-3.0），
   Stage Mode 需在其设置中手动开启并复制 token 到 config.FOLIA_TOKEN。
"""
import base64
import json
import os
import re

import requests

from config import MUSIC_DIR, MUSIC_INDEX

# ---------------- 内嵌媒体缓存（封面/歌词/时长，懒提取，供前端播放器使用） ----------------

COVER_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "covers")
LYRICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lyrics_cache")
os.makedirs(COVER_DIR, exist_ok=True)
os.makedirs(LYRICS_DIR, exist_ok=True)


def search_bilibili(keyword: str) -> dict | None:
    """按关键字搜 B 站视频，取播放量最高的一个。

    返回 {title, bvid, url, cover, author, play, duration}；找不到或请求失败返回 None。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return None
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/search/all/v2",
            params={"keyword": keyword},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"},
            timeout=8,
        )
        data = resp.json()
        if data.get("code") != 0:
            return None
        # 结果按类型分组：result_type == "video" 的项，其 data 才是视频数组
        videos = []
        for grp in data.get("data", {}).get("result", []):
            if grp.get("result_type") != "video":
                continue
            for v in grp.get("data", []):
                if v.get("bvid"):
                    videos.append(v)
        if not videos:
            return None
        # 播放量最高优先
        best = max(videos, key=lambda v: v.get("play", 0))
        title = re.sub(r"<[^>]+>", "", best.get("title", ""))  # 去掉 <em class="keyword"> 高亮标签
        cover = best.get("pic", "")
        if cover.startswith("//"):
            cover = "https:" + cover
        bvid = best.get("bvid", "")
        return {
            "title": title,
            "bvid": bvid,
            "url": "https://www.bilibili.com/video/" + bvid,
            "cover": cover,
            "author": best.get("author", ""),
            "play": int(best.get("play", 0)),
            "duration": best.get("duration", ""),
        }
    except Exception:
        return None


# ---------------- 本地私藏曲库（local_jukebox Skill 的领域实现） ----------------

# 歌曲文件名约定「歌手 - 歌名.扩展名」，扫描文件夹即可发现新歌，无需改代码
_FILE_PAT = re.compile(r"^(?P<artist>.+?)\s+-\s+(?P<title>.+?)\s*\.(mp3|flac|mp4|m4a|wav|ogg)$", re.I)
_FEAT_PAT = re.compile(r"\s*\((?:feat\.?|ft\.?)[^)]*\)", re.I)


def _norm(s: str) -> str:
    """匹配用归一化：小写 + 去空白和常见分隔符，让「一路向北」「一路 向 北」都能对上。"""
    return re.sub(r"[\s・·、,,.\-—()（）\[\]]", "", (s or "").lower())


def load_library() -> list[dict]:
    """扫描 music/ 文件夹得到曲库，并合并 music_index.json 里的人工标注（情绪标签/注解）。

    返回 [{file, artist, title, tags, note}]，文件名不合约定的条目跳过。
    """
    meta = {}
    try:
        with open(MUSIC_INDEX, encoding="utf-8") as f:
            # 按文件名主干（去扩展名）建索引：mp3/flac 换格式后标签不丢
            meta = {os.path.splitext(k)[0]: v
                    for k, v in json.load(f).get("songs", {}).items()}
    except Exception:
        pass  # 元数据缺失不致命：标签/注解为空也能正常点播

    songs = []
    try:
        names = sorted(os.listdir(MUSIC_DIR))
    except OSError:
        return []
    for name in names:
        m = _FILE_PAT.match(name)
        if not m:
            continue
        title_full = m.group("title")
        extra = meta.get(os.path.splitext(name)[0], {})
        songs.append({
            "file": name,
            "artist": m.group("artist").strip(),
            "title": _FEAT_PAT.sub("", title_full).strip(),  # 展示用标题去掉 (feat. xxx)
            "title_full": title_full.strip(),                # 匹配用原始标题
            "tags": extra.get("tags", []),
            "note": extra.get("note", ""),
            "cover": extra.get("cover", ""),  # 指定封面图片 URL（/image/xxx.jpg）；为空则尝试内嵌封面
        })
    return songs


def find_local_song(text: str) -> dict | None:
    """在私藏曲库里找用户提到的歌。匹配优先级：歌名 > 完整标题 > 歌手名（均归一化子串匹配）。"""
    q = _norm(text)
    if not q:
        return None
    lib = load_library()
    # 1) 歌名/完整标题命中（用户 intent 是点歌，歌名命中最可信）
    for s in lib:
        if _norm(s["title"]) and _norm(s["title"]) in q:
            return s
    for s in lib:
        if _norm(s["title_full"]) in q:
            return s
    # 2) 歌手名命中 -> 返回该歌手第一首（"放周杰伦的歌"也能接住）
    for s in lib:
        if _norm(s["artist"]) and _norm(s["artist"]) in q:
            return s
    return None


# ---------------- Folia Stage API（三级降级的第一级） ----------------

def folia_health(timeout: float = 1.5) -> bool:
    """探测 Folia Stage 是否在线（GET /stage/health 免鉴权，最轻量）。"""
    from config import FOLIA_STAGE_URL
    try:
        r = requests.get(f"{FOLIA_STAGE_URL}/stage/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def folia_play_file(file_path: str) -> bool:
    """把本地音频文件推给 Folia 播放（POST /stage/session，multipart 上传）。

    Folia 会自行读取文件内嵌的歌词/封面/元数据；成功返回 True。
    接口细节见 folia-major 仓库 test/manual/stage-client/API_SCHEMA.md。
    """
    from config import FOLIA_STAGE_URL, FOLIA_TOKEN
    if not FOLIA_TOKEN:
        return False
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{FOLIA_STAGE_URL}/stage/session",
                headers={"Authorization": f"Bearer {FOLIA_TOKEN}"},
                files={"file": (os.path.basename(file_path), f)},
                timeout=10,
            )
        return r.status_code in (200, 201)
    except Exception:
        return False


def launch_folia(wait_seconds: int = 12) -> bool:
    """Folia 没在运行时，尝试按 config.FOLIA_EXE 路径拉起它，等它把 Stage 服务起好。

    返回拉起后 Stage 是否就绪；未配置路径或启动失败返回 False（调用方走降级）。
    """
    from config import FOLIA_EXE
    import subprocess, time
    if not FOLIA_EXE or not os.path.isfile(FOLIA_EXE):
        return False
    try:
        subprocess.Popen([FOLIA_EXE], cwd=os.path.dirname(FOLIA_EXE))
    except Exception:
        return False
    # Electron 应用冷启动需要几秒，轮询等 Stage 服务上线
    for _ in range(wait_seconds * 2):
        time.sleep(0.5)
        if folia_health():
            return True
    return False


def play_local(song: dict) -> dict:
    """播放一首私藏歌，两级降级：Folia Stage 在线 -> 网页内播放器（前端 Lattice 面板接管）。"""
    path = os.path.join(MUSIC_DIR, song["file"])
    if folia_health() and folia_play_file(path):
        return {"ok": True, "via": "folia"}
    if not os.path.isfile(path):
        return {"ok": False, "via": "none"}
    return {"ok": True, "via": "web"}  # 前端收到 via=web 后用网页播放器播放


# ---------------- 网页播放器媒体提取（Lattice 队列拼贴 + 歌词浮现） ----------------

_LRC_TIME_PAT = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")

_LYRIC_TIMEOUT = 6  # 秒；失败不致命，下次播放会重试


def _fetch_lyric_online(title: str, artist: str) -> str:
    """在线歌词（纯文本，无需 Key）：QQ 音乐 LRC 为主，网易云兜底；均失败返回空串。"""
    q = f"{artist} {title}".strip()
    # 1) QQ 音乐：搜索拿 songmid -> 歌词接口返回 base64 编码的 LRC
    try:
        h = {"User-Agent": "Mozilla/5.0", "Referer": "https://y.qq.com/"}
        r = requests.get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
                         params={"w": q, "format": "json"}, timeout=_LYRIC_TIMEOUT, headers=h)
        lst = (((r.json().get("data") or {}).get("song") or {}).get("list")) or []
        if lst:
            r2 = requests.get("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg",
                              params={"songmid": lst[0]["songmid"], "g_tk": 5381, "format": "json"},
                              timeout=_LYRIC_TIMEOUT, headers=h)
            b64 = r2.json().get("lyric", "")
            if b64:
                return base64.b64decode(b64).decode("utf-8", "ignore")
    except Exception:
        pass
    # 2) 网易云兜底（部分网络环境会被风控拦截）
    try:
        r = requests.get("https://music.163.com/api/search/pc",
                         params={"s": q, "type": 1, "limit": 5}, timeout=_LYRIC_TIMEOUT)
        songs = (r.json().get("result") or {}).get("songs") or []
        if songs:
            r2 = requests.get("https://music.163.com/api/song/lyric",
                              params={"id": songs[0]["id"], "lv": 1, "kv": 1, "tv": -1},
                              timeout=_LYRIC_TIMEOUT)
            return (r2.json().get("lrc") or {}).get("lyric") or ""
    except Exception:
        pass
    return ""  # 离线/超时：返回空，歌词区回退到小狐私评


def _parse_lyric_text(raw: str) -> list[dict]:
    """解析歌词文本：带 [mm:ss.xx] 时间戳的按时间轴；纯文本行时间置 None（前端按曲长均分）。"""
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        stamps = _LRC_TIME_PAT.findall(ln)
        text = _LRC_TIME_PAT.sub("", ln).strip()
        if not text or text in ("纯音乐，请欣赏",):
            continue
        if stamps:
            for m, s, frac in stamps:
                ms = int((frac or "0").ljust(3, "0")[:3])
                lines.append({"t": int(m) * 60 + int(s) + ms / 1000, "text": text})
        else:
            lines.append({"t": None, "text": ln})
    lines.sort(key=lambda x: (x["t"] is not None, x["t"] if x["t"] is not None else 0))
    return lines


def extract_media(song: dict) -> dict:
    """从音频文件提取封面/歌词/时长，懒提取并缓存到 static/covers 与 data/lyrics_cache。

    返回 {cover, duration, lyrics}；cover 为可访问的 URL 前缀路径（无封面为 ""）。
    """
    stem = os.path.splitext(song["file"])[0]
    cover_rel = f"/static/covers/{stem}.jpg"
    cover_path = os.path.join(COVER_DIR, stem + ".jpg")
    lyric_path = os.path.join(LYRICS_DIR, stem + ".json")
    path = os.path.join(MUSIC_DIR, song["file"])

    out = {"cover": cover_rel if os.path.isfile(cover_path) else "",
           "lyrics": [], "duration": 0}
    if os.path.isfile(lyric_path):
        try:
            with open(lyric_path, encoding="utf-8") as f:
                cached = json.load(f)
            out["lyrics"] = cached.get("lyrics", [])
            out["duration"] = cached.get("duration", 0)
            return out
        except Exception:
            pass
    try:
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
        from mutagen.mp3 import MP3
        audio = None
        raw_lyric = ""
        # 歌词来源优先级：同名 .lrc 文件 > 音频内嵌歌词标签
        lrc_sidecar = os.path.join(MUSIC_DIR, stem + ".lrc")
        if os.path.isfile(lrc_sidecar):
            try:
                with open(lrc_sidecar, encoding="utf-8", errors="ignore") as f:
                    raw_lyric = f.read()
            except Exception:
                pass
        if song["file"].lower().endswith(".flac"):
            audio = FLAC(path)
            if audio.pictures:
                with open(cover_path, "wb") as f:
                    f.write(audio.pictures[0].data)
            raw_lyric = (audio.get("LYRICS") or audio.get("UNSYNCEDLYRICS") or [""])[0]
        elif song["file"].lower().endswith(".mp3"):
            audio = MP3(path)
            try:
                tags = ID3(path)
                for pic in tags.getall("APIC"):
                    with open(cover_path, "wb") as f:
                        f.write(pic.data)
                    break
                for ult in tags.getall("USLT"):
                    raw_lyric = ult.text or ""
                    break
            except Exception:
                pass
        if audio and audio.info:
            out["duration"] = round(audio.info.length, 1)
        out["lyrics"] = _parse_lyric_text(raw_lyric) if raw_lyric else []
        if not out["lyrics"]:
            # 本地与内嵌都没有 -> 在线取（网易云 LRC，带时间戳）
            online = _fetch_lyric_online(song["title"], song["artist"])
            out["lyrics"] = _parse_lyric_text(online) if online else []
    except Exception:
        pass  # 提取失败不致命：无封面/歌词也能正常播放
    if os.path.isfile(cover_path):
        out["cover"] = cover_rel
    with open(lyric_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out