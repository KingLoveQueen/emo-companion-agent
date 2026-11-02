# -*- coding: utf-8 -*-
"""
Flask 轻量 Web 对话界面（零前端框架，单文件）：
  左侧：聊天窗口（每条 AI 回复下方带机制徽章：命中Skill/幽默档/记忆读写/延迟）
  右上：用户记忆档案面板（长期画像 + 会话摘要，实时刷新）
  右下：运行日志面板（最近 40 条 JSONL 日志，可核对每轮机制）
启动：python app.py  ->  打开 http://127.0.0.1:5000
"""
from flask import Flask, jsonify, request

from agent_core import EmotionalAgent
from logger import read_recent
from music import extract_media, load_library
from config import IMAGE_DIR, MUSIC_DIR

import os

app = Flask(__name__)
AGENTS: dict[str, EmotionalAgent] = {}  # user_id -> Agent 实例（进程内缓存）


def get_agent(user_id: str) -> EmotionalAgent:
    """同一 user_id 复用同一 Agent，保证会话记忆与档案连续。"""
    if user_id not in AGENTS:
        AGENTS[user_id] = EmotionalAgent(user_id)
    return AGENTS[user_id]


# ---------------- 页面（模板里不使用 Jinja 语法，纯静态字符串） ----------------
INDEX_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>小狐 · 情感陪伴 Agent</title>
<style>
  :root{--bg:#141414;--panel:#1d1d1b;--line:#3a3a33;--gold:#e8c832;--txt:#eaeae0;--dim:#9a9a8c}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font:14px/1.6 "Microsoft YaHei",sans-serif;height:100vh;display:flex;flex-direction:column}
  header{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  header h1{font-size:16px;color:var(--gold)}
  .tag{font-size:12px;border:1px solid var(--line);color:var(--dim);padding:1px 8px;border-radius:10px}
  .tag.gold{border-color:var(--gold);color:var(--gold)}
  .uid{margin-left:auto;font-size:12px;color:var(--dim)}
  .uid input{width:110px;background:#101010;border:1px solid var(--line);color:var(--txt);padding:3px 8px;border-radius:6px;outline:none}
  main{flex:1;display:flex;min-height:0}
  .chat{flex:1;display:flex;flex-direction:column;min-width:0;border-right:1px solid var(--line)}
  #msgs{flex:1;overflow-y:auto;padding:16px}
  .row{margin-bottom:14px;display:flex}
  .row.me{justify-content:flex-end}
  .bubble{max-width:72%;padding:9px 12px;border-radius:10px;white-space:pre-wrap}
  .me .bubble{background:#2e2a17;border:1px solid #5a4f1d}
  .ai .bubble{background:var(--panel);border:1px solid var(--line)}
  .meta{font-size:11px;color:var(--dim);margin-top:4px;display:flex;gap:6px;flex-wrap:wrap}
  .meta .tag.warn{border-color:#a33;color:#e77}
  .meta .tag.gold{border-color:var(--gold);color:var(--gold)}
  .inputbar{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}
  #inp{flex:1;background:#101010;border:1px solid var(--line);color:var(--txt);padding:9px 12px;border-radius:8px;outline:none}
  #send{background:var(--gold);border:none;color:#141414;font-weight:bold;padding:0 20px;border-radius:8px;cursor:pointer}
  aside{width:400px;display:flex;flex-direction:column;min-height:0}
  .card{display:flex;flex-direction:column;min-height:0;flex:1}
  .card h2{font-size:13px;color:var(--gold);padding:8px 12px;border-bottom:1px solid var(--line);font-weight:normal}
  .card .body{overflow-y:auto;padding:10px 12px;font-size:12.5px}
  #memCard{border-bottom:1px solid var(--line)}
  .kv{margin-bottom:5px}
  .kv b{color:var(--gold);font-weight:normal}
  .sec{color:var(--dim);margin:8px 0 3px;font-size:11.5px}
  .moodbar{display:inline-block;height:8px;background:var(--gold);border-radius:4px;vertical-align:middle;margin-right:4px}
  table{width:100%;border-collapse:collapse;font-size:11.5px}
  td{padding:2px 4px;border-bottom:1px dashed #2a2a25;vertical-align:top}
  td.t{color:var(--dim);white-space:nowrap}
  .sk{color:var(--gold)}
  .hbtn{background:none;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:2px 10px;cursor:pointer;font-size:12px}
  .hbtn:hover{border-color:var(--gold);color:var(--gold)}
  /* 点歌结果卡片：封面图 + 标题 + UP主 + 播放量，点击跳 B 站 */
  .musicCard{display:flex;gap:10px;align-items:center;margin-top:8px;padding:8px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--txt);background:#15120c;transition:border-color .2s}
  .musicCard:hover{border-color:var(--gold)}
  .musicCard img{width:96px;height:60px;object-fit:cover;border-radius:4px;flex:none;background:#000}
  .mcBody{display:flex;flex-direction:column;gap:2px;min-width:0}
  /* 私藏电台歌单卡片：每行一首，点击即点播（配合 local_jukebox skill） */
  .plCard{margin-top:8px;border:1px solid var(--line);border-radius:8px;background:#15120c;overflow:hidden;max-width:480px}
  .plHead{padding:6px 10px;font-size:12px;color:var(--gold);border-bottom:1px solid var(--line)}
  .plRow{display:flex;gap:8px;align-items:baseline;padding:6px 10px;cursor:pointer;border-bottom:1px dashed #2a2a25}
  .plRow:last-child{border-bottom:none}
  .plRow:hover{background:#221d10}
  .plRow b{font-weight:normal;color:var(--txt);white-space:nowrap}
  .plRow:hover b{color:var(--gold)}
  .plRow i{font-style:normal;color:var(--dim);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .plTags{margin-left:auto;color:var(--gold);font-size:11px;white-space:nowrap;flex:none}
  /* 私藏电台正在播放卡片：转动的"唱片"+歌名+小狐私评 */
  .nowCard{display:flex;gap:10px;align-items:center;margin-top:8px;padding:8px;border:1px solid var(--gold);border-radius:8px;background:#15120c;max-width:480px}
  .disc{width:44px;height:44px;border-radius:50%;flex:none;background:radial-gradient(circle at center,#2a2415 30%,#0c0c0c 31%);border:2px solid var(--gold);display:flex;align-items:center;justify-content:center;font-size:18px;animation:spin 6s linear infinite}
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  .nowBody{display:flex;flex-direction:column;gap:2px;min-width:0}
  .nowBody i{font-style:normal;color:var(--dim);font-size:11.5px}
  .mcBody b{color:var(--gold);font-weight:normal;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mcBody i{color:var(--dim);font-style:normal;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* ---------- 启动动画（开机自检序列） ---------- */
  #boot{position:fixed;inset:0;background:#0a0a08;z-index:99;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:opacity .7s}
  #boot.done{opacity:0;pointer-events:none}
  /* ---------- 经典主题 · 550C 风全屏 HUD（移植 Voidpocket/html_550c 的编排思路：CRT 扫描线+辉光+打字机+四面板） ---------- */
  #bootClassic{position:absolute;inset:0;display:none;flex-direction:column;background:#050607;color:#d8e0d8;
    font:12px/1.9 Consolas,Menlo,monospace;overflow:hidden;isolation:isolate}
  .cl-scan{position:absolute;inset:0;z-index:9;pointer-events:none;
    background:repeating-linear-gradient(0deg,rgba(0,0,0,.22) 0 1px,transparent 1px 3px)}
  .cl-hud-top,.cl-hud-bot{display:flex;align-items:center;gap:14px;padding:8px 18px;font-size:10.5px;letter-spacing:.14em;color:#8a948a;flex:none}
  .cl-hud-top{border-bottom:1px solid #1c2018}
  .cl-hud-bot{border-top:1px solid #1c2018}
  .cl-brand{color:#e8c832;font-weight:bold;text-shadow:0 0 8px rgba(232,200,50,.5)}
  .cl-sep{opacity:.35}
  .cl-item b{color:#d8e0d8;font-weight:normal;margin-left:4px}
  .cl-item b.gold{color:#e8c832}
  .cl-spacer{flex:1}
  .cl-live{color:#e05030;animation:clPulse 1.2s ease-in-out infinite}
  @keyframes clPulse{0%,100%{opacity:1}50%{opacity:.3}}
  .cl-stage{flex:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:26px 0 10px;transition:opacity .5s,transform .5s,padding .5s}
  .cl-stage.off{opacity:0;transform:scale(.94);height:0;padding:0 0 4px;overflow:hidden}
  .cl-fox{width:112px;display:block;margin:0 auto 10px;filter:drop-shadow(0 0 10px rgba(232,200,50,.45))}
  #clFoxHead{fill:none}
  .cl-fox-f{opacity:0;transform:scale(.4);transform-box:fill-box;transform-origin:center;
    transition:opacity .45s,transform .45s cubic-bezier(.34,1.56,.64,1)}
  .cl-fox-f.on{opacity:1;transform:scale(1)}
  .cl-logo{font:500 clamp(40px,7vw,84px)/1.2 "KaiTi","STKaiti",serif;letter-spacing:.18em;color:#f2ecd8;text-shadow:0 0 18px rgba(232,200,50,.35)}
  .cl-logo i{font-style:normal;color:#e8c832}
  .cl-logo span{display:inline-block;clip-path:inset(0 100% 0 0);transition:clip-path .55s cubic-bezier(.4,0,.2,1)}
  .cl-boottext{font-size:11px;letter-spacing:.34em;color:#8a948a}
  .cl-cursor{display:inline-block;width:7px;height:12px;margin-left:6px;background:#e8c832;vertical-align:-1px;animation:clBlink 1s steps(1) infinite}
  @keyframes clBlink{0%,49%{opacity:1}50%,100%{opacity:0}}
  .cl-work{flex:1;display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.55fr);grid-template-rows:minmax(0,1.15fr) minmax(0,1fr);gap:10px;padding:4px 18px 12px;min-height:0}
  .cl-w{display:flex;flex-direction:column;min-height:0;border:1px solid #1c2018;background:rgba(14,16,12,.72)}
  #clW-tele{grid-area:1/1/2/2}
  #clW-node{grid-area:2/1/3/2}
  #clW-main{grid-area:1/2/2/3}
  #clW-code{grid-area:2/2/3/3}
  .cl-whead{flex:none;display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid #1c2018;font-size:10px;letter-spacing:.2em;color:#8a948a}
  .cl-led{width:6px;height:6px;background:#e8c832;box-shadow:0 0 6px rgba(232,200,50,.8)}
  .cl-led.red{background:#e05030;box-shadow:0 0 6px rgba(224,80,48,.8)}
  .cl-wbody{flex:1;overflow:hidden;padding:8px 12px;min-height:0}
  .cl-sect{margin:6px 0 2px;font-size:9.5px;letter-spacing:.22em;color:#5c645a}
  .cl-dt{display:flex;justify-content:space-between;gap:12px;font-size:11px;line-height:2}
  .cl-dt .k{color:#8a948a}
  .cl-dt .v{color:#d8e0d8;text-align:right;white-space:nowrap}
  .cl-dt .v.gold{color:#e8c832}
  .cl-dt .v.bad{color:#e05030}
  /* 主控台：550C 式 [XIAOHU] 前缀打字行，行末 [ OK ] */
  #clMain .cl-ln{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:2.1}
  .cl-ln .cl-pfx{color:#5c645a}
  .cl-ln .cl-ok{color:#9fc86a}
  .cl-ln.sys .cl-tx{color:#c9d2c5}
  .cl-ln.warn .cl-tx{color:#e8c832}
  .cl-ln.warn .cl-ok{color:#e8c832}
  .cl-ln.ok .cl-tx{color:#9fc86a}
  /* 代码流面板 */
  #clCode{font-size:10.5px;line-height:1.8;color:#6f7a6c;overflow:hidden}
  /* 技能矩阵 */
  #clNodes{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;height:100%;align-content:center}
  .cl-node{border:1px solid #1c2018;padding:8px 4px;text-align:center;font-size:10px;color:#5c645a;transition:border-color .3s,color .3s}
  .cl-node b{display:block;font-size:11px;color:#8a948a;font-weight:normal;white-space:nowrap}
  .cl-node .st{display:block;margin-top:4px;letter-spacing:.1em}
  .cl-node.on{border-color:rgba(232,200,50,.5);color:#8a948a}
  .cl-node.on .st{color:#9fc86a}
  /* 底栏进度 */
  .cl-prog{width:min(280px,26vw);height:4px;background:#15170f;overflow:hidden}
  .cl-fill{height:100%;width:0;background:linear-gradient(90deg,#8f7a1e,#e8c832);transition:width .25s}
  .cl-pct{color:#e8c832;font-size:10.5px}
  /* 收尾定格大字 */
  .cl-final{position:absolute;inset:0;z-index:8;display:flex;align-items:center;justify-content:center;background:rgba(5,6,7,.88);
    font:500 clamp(26px,4.5vw,54px)/1.4 "KaiTi","STKaiti",serif;letter-spacing:.3em;color:#e8c832;
    text-shadow:0 0 24px rgba(232,200,50,.5);opacity:0;pointer-events:none;transition:opacity .5s}
  .cl-final.show{opacity:1}
  @media (max-width:760px){
    .cl-work{grid-template-columns:1fr;grid-template-rows:1fr}
    #clW-tele,#clW-node,#clW-code{display:none}
    #clW-main{grid-area:auto}
    .cl-hud-top .cl-item{display:none}
  }
  .bline{opacity:0;animation:bIn .25s forwards;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  @keyframes bIn{to{opacity:1}}
  .pfx{color:var(--dim)}
  .ok{color:var(--gold)}
  .bootHint{text-align:center;color:#55554a;font-size:11px;margin-top:12px;letter-spacing:2px}
  #bootClassic .bootHint{position:absolute;left:0;right:0;bottom:2.6vh;z-index:10;margin:0}
  /* ---------- 启动主题选择 ---------- */
  #themeSel{background:#101010;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:3px 6px;font-size:12px;outline:none;cursor:pointer}
  /* ---------- 狐仙立绘主题 · 按参考视频标准 ---------- */
  /* ---------- 狐仙主题 · 按参考视频（Codex 同人启动动画）标准重做 ----------
     编排：暗场星尘 + 左下状态行/细进度线 + 青色霓虹线稿自上而下勾勒
     → 彩色立绘整体交叉淡入（线稿辉光随之融解）→ 水印标题渐亮为白 → 淡出进聊天 */
  #bootSpirit{position:absolute;inset:0;display:none;overflow:hidden;
    background:radial-gradient(1px 1px at 11% 24%,rgba(255,255,255,.4) 50%,transparent 51%),
      radial-gradient(1px 1px at 27% 68%,rgba(255,255,255,.28) 50%,transparent 51%),
      radial-gradient(1.5px 1.5px at 41% 15%,rgba(255,255,255,.32) 50%,transparent 51%),
      radial-gradient(1px 1px at 56% 82%,rgba(255,255,255,.22) 50%,transparent 51%),
      radial-gradient(1.5px 1.5px at 72% 36%,rgba(255,255,255,.3) 50%,transparent 51%),
      radial-gradient(1px 1px at 88% 64%,rgba(255,255,255,.26) 50%,transparent 51%),#050708}
  #bootSpirit .art{position:absolute;right:0;top:0;bottom:0;width:62%;overflow:hidden;
    opacity:0;transition:opacity .8s ease;
    -webkit-mask-image:linear-gradient(90deg,transparent 0,#000 45%);mask-image:linear-gradient(90deg,transparent 0,#000 45%)}
  #bootSpirit.artIn .art{opacity:1}
  /* 两层同位叠加：彩色层沉底；青色霓虹线稿层在最上，勾勒完毕后被颜色"淹没" */
  #bootSpirit .artColor,#bootSpirit .artLine{position:absolute;inset:0;
    background:url(/static/fox_spirit.jpg) right center/cover no-repeat}
  #bootSpirit .artLine{background:url(/static/fox_spirit_line_cyan.png) right center/cover no-repeat;
    clip-path:inset(0 0 100% 0);
    transition:clip-path 1.7s cubic-bezier(.3,.1,.25,1),opacity 1.4s ease .45s;
    animation:lineFlicker 2.2s ease-in-out infinite}
  #bootSpirit.drawIn .artLine{clip-path:inset(0 0 0% 0)}
  #bootSpirit.clrIn .artLine{opacity:0}          /* 颜色到来后线稿辉光融解 */
  @keyframes lineFlicker{
    0%,100%{filter:drop-shadow(0 0 5px rgba(125,251,238,.7)) drop-shadow(0 0 16px rgba(125,251,238,.32))}
    50%{filter:drop-shadow(0 0 9px rgba(125,251,238,.95)) drop-shadow(0 0 26px rgba(125,251,238,.5))}}
  /* 彩色层：整幅交叉淡入（同参考视频的"颜色淹没线稿"，而非局部扩散） */
  #bootSpirit .artColor{opacity:0;transition:opacity 1s ease-in-out}
  #bootSpirit.clrIn .artColor{opacity:1}
  #bootSpirit .veil{position:absolute;inset:0;background:linear-gradient(90deg,#050708 30%,rgba(5,7,8,.55) 62%,rgba(5,7,8,.1) 100%)}
  /* 左上品牌角标（同参考视频 ">_ Codex / PERSONAL WORKSPACE"） */
  .spBrand{position:absolute;top:2.8vh;left:2.2vw;z-index:2;font:12px Consolas,monospace;color:#c3ccc6;letter-spacing:2px}
  .spBrand i{display:block;font-style:normal;font-size:9px;letter-spacing:4px;color:#5c665f;margin-top:3px}
  /* 标题块：勾勒期是暗水印，颜色到来后渐亮为白（同参考视频的 Codex 字标节奏） */
  .spBox{position:relative;z-index:2;width:min(560px,58vw);padding:26vh 0 0 6vw;font:13px/2.15 Consolas,monospace;color:#ddd8cc}
  .spTitle{font:200 68px/1.2 "Segoe UI Light","Microsoft YaHei Light","Microsoft YaHei",sans-serif;
    color:#3a423f;opacity:.55;letter-spacing:8px;transform:translateY(6px);
    transition:color 1.1s ease,opacity 1.1s ease,transform 1.1s ease}
  #bootSpirit.titleIn .spTitle{color:#f4f6f4;opacity:1;transform:none;text-shadow:0 0 22px rgba(125,251,238,.25)}
  .spSub{color:#eef0ec;font-size:21px;letter-spacing:6px;margin-top:16px;font-family:"KaiTi","STKaiti",serif;
    opacity:0;transform:translateY(8px);transition:opacity .9s ease .35s,transform .9s ease .35s}
  #bootSpirit.titleIn .spSub{opacity:1;transform:none}
  .spCaps{font:10px Consolas,monospace;letter-spacing:5px;color:#8a948c;margin-top:10px;opacity:0;transition:opacity .9s ease .6s}
  #bootSpirit.titleIn .spCaps{opacity:.85}
  /* 左下状态行 + 细进度线：正在唤醒躯体 → 正在点亮你的工作空间 → 一切就绪，即刻出发 */
  .spStatus{position:absolute;left:6vw;bottom:9vh;z-index:2;font:12px Consolas,monospace;color:#b9c2bd;letter-spacing:3px}
  .spStatus::before{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:#5ff5e0;
    margin-right:8px;vertical-align:1px;box-shadow:0 0 6px rgba(95,245,224,.9);animation:clPulse 1.2s ease-in-out infinite}
  .spProg{width:210px;height:2px;background:rgba(255,255,255,.12);margin-top:9px;overflow:hidden}
  #spBar{height:100%;width:0;background:linear-gradient(90deg,#5ff5e0,#e8c832)}
  .spSkip{position:absolute;right:2.2vw;bottom:9vh;z-index:2;font:11px Consolas,monospace;color:#5c665f;letter-spacing:3px}
  /* 狐仙主题下：右侧立绘改由全屏和风插画背景替代（见 body.spirit::before） */
  .chat{position:relative}
  #chatBg{display:none;position:absolute;right:12px;bottom:0;height:78%;max-width:48%;object-fit:contain;opacity:.26;pointer-events:none;z-index:0;
    -webkit-mask-image:linear-gradient(90deg,transparent 0,#000 60%);mask-image:linear-gradient(90deg,transparent 0,#000 60%)}
  body.spirit #chatBg{display:none}
  /* 狐仙主题：和风狐仙插画铺满全屏做背景（低透明度，面板/文本框本身是深色实底，可读性不受影响） */
  body.spirit::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
    background:url(/static/spirit-bg.jpg) center/cover no-repeat;opacity:.2}
  /* 狐仙主题动态壁纸：视频加载成功后淡入，盖过静态插画（同 0.2 透明度，面板可读性不变） */
  #spiritVideo{display:none;position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1;opacity:0;pointer-events:none;transition:opacity .8s}
  body.spirit #spiritVideo.has{display:block;opacity:.2}
  body.videoBg.spirit::before{opacity:0}
  /* 狐仙/Codex 主题聊天配色：金色→青色（与开头霓虹线稿同源），强调色做 360° 色相循环（青→蓝→紫→粉→青） */
  body.spirit{--gold:#2be0e8}
  body.spirit header h1,body.spirit .tag.gold,body.spirit .card h2,body.spirit #send,
  body.spirit .moodbar,body.spirit .kv b,body.spirit .sk,body.spirit .mcBody b{animation:spiritHue 14s linear infinite}
  @keyframes spiritHue{0%{filter:hue-rotate(0deg)}100%{filter:hue-rotate(360deg)}}
  /* 粒子动画主题：聊天背景用 Wallpaper Engine 壁纸画面（preview.jpg，即启动动画第二幕的剑士立绘），低透明度保证面板可读；
     静态图加缓慢呼吸缩放（模拟壁纸的流动感），视频版加载后淡出（见 #codexVideo） */
  body.codex::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
    background:url(/static/codex-art.jpg) center/cover no-repeat;opacity:.2;
    transform-origin:center;animation:codexBgBreath 26s ease-in-out infinite alternate}
  @keyframes codexBgBreath{from{transform:scale(1) translate(0,0)}50%{transform:scale(1.05) translate(-.6%,.4%)}to{transform:scale(1.03) translate(.5%,-.5%)}}
  /* 粒子动画主题视频壁纸：录一段本地 Wallpaper Engine 壁纸存为 static/codex-bg.mp4 即自动淡入生效 */
  #codexVideo{display:none;position:fixed;inset:0;width:100%;height:100%;object-fit:cover;z-index:-1;opacity:0;pointer-events:none;transition:opacity .8s}
  body.codex #codexVideo.has{display:block;opacity:.2}
  body.videoBg.codex::before{opacity:0;animation:none}
  /* ---------- 酒德麻衣主题聊天背景：PV 最后一幕（麻衣 + MAI SAKATEJIMA 签名），强调色改玫红适配 ---------- */
  body.md{--gold:#f0708a}
  body.md::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
    background:url(/static/md-bg.jpg) center/cover no-repeat;opacity:.24;
    transform-origin:center;animation:codexBgBreath 26s ease-in-out infinite alternate}
  #msgs{position:relative;z-index:1}
  /* ================= Codex 完整版启动主题 =================
     动画逻辑来源：yanami-sec/codex-startup-animation-windows
     （上游 panding999/codex-startup-animation），仅用于课堂作业演示。
     只提取/改写了原仓库的动画编排思路与关键参数，未整体复制其文件或素材；
     所有类名统一加 .cdx 前缀，避免与经典/狐仙两套主题样式冲突。 */
  /* 容器：铺满 #boot 遮罩，display 由 JS 按主题切换 */
  #bootCodex{position:absolute;inset:0;display:none;background:#08060d;overflow:hidden}
  /* 场景层：结尾"画面合拢"时整体 scaleY 压缩至 0（对应上游 11s 处 collapse） */
  .cdxScene{position:absolute;inset:0;transform-origin:50% 50%;pointer-events:none}
  /* 背景立绘双层叠加：线稿层自左向右勾勒 → 彩色层淡入完成"上色"
     （上游是 canvas 实时描线+上色；此处用现成的 fox_spirit_line.png 线稿图等效还原） */
  .cdxArt{position:absolute;inset:0;opacity:0;transition:opacity .45s ease,transform 4s ease}
  #bootCodex.cdxDraw .cdxArt{opacity:1}
  #bootCodex.cdxColor .cdxArt{transform:scale(1.02)}
  .cdxArtColor,.cdxArtLine{position:absolute;inset:0;background-position:center 20%;background-size:cover;background-repeat:no-repeat}
  .cdxArtColor{background-image:url(/static/codex-art.jpg);opacity:0;transition:opacity 1.3s ease}
  .cdxArtLine{background-image:url(/static/codex-art-line.png);clip-path:inset(0 100% 0 0);transition:clip-path 1.2s linear}
  /* 上色后叠加壁纸 waterflow 着色器的网页等效：SVG 湍流置换让立绘产生水流波动 */
  #bootCodex.cdxColor .cdxArtColor{filter:url(#cdxFlow)}
  /* 壁纸"雾 1"粒子层的网页等效：两团柔雾缓慢平移 */
  .cdxScene::after{content:"";position:absolute;inset:-10%;z-index:3;pointer-events:none;opacity:0;transition:opacity 1.5s;
    background:radial-gradient(38% 22% at 22% 78%, rgba(190,170,220,.10), transparent 70%),
               radial-gradient(30% 18% at 74% 86%, rgba(200,190,230,.08), transparent 70%);
    animation:cdxFog 26s ease-in-out infinite alternate}
  #bootCodex.cdxColor .cdxScene::after{opacity:1}
  @keyframes cdxFog{from{transform:translateX(-2.5%) scale(1)}to{transform:translateX(2.5%) scale(1.06)}}
  /* 壁纸"星域"粒子层的网页等效：512 颗白色星粒上升 + 拖尾 + 透明度衰减（JS 驱动，见 cdxStarfield） */
  .cdxStars{position:absolute;inset:0;z-index:4;opacity:0;transition:opacity 1.2s;pointer-events:none}
  #bootCodex.cdxColor .cdxStars{opacity:.75}
  /* 粒子描线画布：位于彩色层之上、线稿图之下；粒子汇聚后由线稿图"显影"接棒 */
  .cdxCanvas{position:absolute;inset:0;z-index:1;opacity:0;transition:opacity .8s ease}
  #bootCodex.cdxDraw .cdxCanvas{opacity:1}
  #bootCodex.cdxColor .cdxCanvas{opacity:0}
  #bootCodex.cdxLineIn .cdxArtLine{clip-path:inset(0 0% 0 0)}
  #bootCodex.cdxColor .cdxArtColor{opacity:1}
  #bootCodex.cdxColor .cdxArtLine{opacity:0;transition:opacity .9s .55s}
  /* 上下暗角（上游 .shade，上色阶段随背景一同浮现） */
  .cdxVeil{position:absolute;inset:0;z-index:2;opacity:0;transition:opacity 1.3s;pointer-events:none;
    background:linear-gradient(180deg,rgba(8,6,13,.55),rgba(8,6,13,.08) 30%,rgba(8,6,13,.1) 70%,rgba(8,6,13,.6))}
  #bootCodex.cdxColor .cdxVeil{opacity:1}
  /* CRT 扫描线纹理（上游 .scanlines） */
  .cdxScan{position:absolute;inset:0;z-index:3;opacity:.05;pointer-events:none;
    background:repeating-linear-gradient(transparent 0 3px,#201725 3px 4px)}
  /* 淡网格 + 四角定位框（上游 .boot-grid / .boot-corners，前半段装饰） */
  .cdxGrid{position:absolute;inset:18% 22% 16%;z-index:3;pointer-events:none;animation:cdxFadeIn .6s ease .1s both;transition:opacity .6s;
    background-image:linear-gradient(#7560800c 1px,transparent 1px),linear-gradient(90deg,#7560800c 1px,transparent 1px);
    background-size:34px 34px;-webkit-mask-image:radial-gradient(ellipse,black,transparent 72%);mask-image:radial-gradient(ellipse,black,transparent 72%)}
  .cdxCorners i{position:absolute;width:32px;height:32px;border:0 solid #9c456c;opacity:.65;animation:cdxFadeIn .6s ease .1s both;transition:opacity .6s}
  .cdxCorners .tl{top:19px;left:19px;border-top-width:1.5px;border-left-width:1.5px}
  .cdxCorners .tr{top:19px;right:19px;border-top-width:1.5px;border-right-width:1.5px}
  .cdxCorners .bl{bottom:19px;left:19px;border-bottom-width:1.5px;border-left-width:1.5px}
  .cdxCorners .br{bottom:19px;right:19px;border-bottom-width:1.5px;border-right-width:1.5px}
  #bootCodex.cdxDraw .cdxGrid,#bootCodex.cdxDraw .cdxCorners i{opacity:0}
  /* 上浮粒子（上游 .particles，JS 生成 6 颗；此处改为纯 CSS 定位） */
  .cdxParticles{position:absolute;inset:0;z-index:4;opacity:0;transition:opacity 1.2s;pointer-events:none}
  #bootCodex.cdxColor .cdxParticles{opacity:.6}
  .cdxParticles i{position:absolute;border-radius:50%;background:#e8f9ff;box-shadow:0 0 10px #d8f5ff88;animation:cdxFloat 10s linear infinite}
  .cdxParticles i:nth-child(1){left:7%;top:82%;width:3px;height:3px;animation-duration:9s}
  .cdxParticles i:nth-child(2){left:44%;top:88%;width:1.5px;height:1.5px;animation-duration:12s}
  .cdxParticles i:nth-child(3){left:81%;top:80%;width:1.5px;height:1.5px;animation-duration:8s}
  .cdxParticles i:nth-child(4){left:18%;top:92%;width:1.5px;height:1.5px;animation-duration:11s}
  .cdxParticles i:nth-child(5){left:55%;top:85%;width:3px;height:3px;animation-duration:13s}
  .cdxParticles i:nth-child(6){left:92%;top:90%;width:1.5px;height:1.5px;animation-duration:10s}
  @keyframes cdxFloat{0%{transform:translateY(0);opacity:0}12%{opacity:.9}100%{transform:translateY(-60vh);opacity:0}}
  /* 斜向扫光（上游 .light-sweep，HUD 阶段划过一次） */
  .cdxSweep{position:absolute;inset:-50%;z-index:4;opacity:0;pointer-events:none;
    background:linear-gradient(110deg,transparent 43%,#fff4 50%,transparent 57%)}
  #bootCodex.cdxHudIn .cdxSweep{animation:cdxSweep 1s ease .1s both}
  @keyframes cdxSweep{from{transform:translateX(-60%);opacity:.12}to{transform:translateX(60%);opacity:0}}
  /* 前半段：脉冲环 + 雷达头像 + 标题/小字（上游 .intro，1~4.2s 的"身份登场"） */
  .cdxIntro{position:absolute;inset:0;z-index:6;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:radial-gradient(ellipse,#141020 0%,#08060d 72%);color:#d980a7;pointer-events:none;transition:opacity .55s}
  #bootCodex.cdxDraw .cdxIntro{opacity:0}
  .cdxPulse{position:absolute;left:50%;top:50%;width:110px;height:110px;transform:translate(-50%,-50%)}
  .cdxPulse i{position:absolute;inset:0;border:2px solid #bd5d8980;border-radius:50%;animation:cdxPulse 1.6s ease-out infinite}
  .cdxPulse i:nth-child(2){animation-delay:.55s}
  .cdxPulse b{position:absolute;left:50%;top:50%;width:8px;height:8px;transform:translate(-50%,-50%);border-radius:50%;background:#ee96bc;box-shadow:0 0 12px #ee79b288}
  @keyframes cdxPulse{0%{transform:scale(.25);opacity:.8}100%{transform:scale(1.15);opacity:0}}
  .cdxIdentity{position:absolute;left:50%;top:50%;width:min(52vh,420px);text-align:center;
    opacity:0;transform:translate(-50%,-43%) scale(.94);transition:opacity .65s ease,transform .65s ease}
  #bootCodex.cdxId .cdxIdentity{opacity:1;transform:translate(-50%,-43%) scale(1)}
  /* 雷达圈：外环 + 60 格刻度环 + 旋转虚线环 + 十字准星（上游 .radar/.dial） */
  .cdxRadar{position:relative;width:min(38vh,300px);aspect-ratio:1;margin:0 auto}
  .cdxDial{position:absolute;inset:0;width:100%;height:100%;fill:none;stroke:#c27697;stroke-width:1;overflow:visible}
  .cdxDial .cdxDashed{stroke-dasharray:9 12;stroke:#8f819e;opacity:.4;transform-box:fill-box;transform-origin:center;animation:cdxSpin 22.5s linear infinite}
  .cdxDial .cdxTicksRing{stroke:#c27697;stroke-width:1.6;opacity:.55}
  .cdxDial .cdxCross{stroke:#c5b2c4;opacity:.65}
  @keyframes cdxSpin{to{transform:rotate(360deg)}}
  /* 头像：第一幕圆形头像（codex-avatar.jpg，52%/30% 对准脸部）；心跳浮动对应上游 1.05s 起 avatar-frame 的 beat 动画 */
  .cdxAvatar{position:absolute;inset:21%;border-radius:50%;border:1px solid #cb7b9f;box-shadow:0 0 18px #f18ab514;
    background:url(/static/codex-avatar.jpg) 52% 30%/cover no-repeat;animation:cdxBeat 1.08s ease-in-out infinite}
  @keyframes cdxBeat{0%,100%{transform:none}50%{transform:translateY(-4px) scale(1.025)}}
  .cdxWave{display:block;width:min(34vh,270px);height:22px;margin:14px auto -2px;fill:none;stroke:#d087a6;stroke-width:1.4;opacity:.7;animation:cdxWaveA 1.1s ease-in-out infinite}
  @keyframes cdxWaveA{0%,100%{transform:scaleY(1)}50%{transform:scaleY(.55)}}
  /* 标题「小狐」：初始右侧裁切，入场后自左向右展开（上游 1.9~2.6s clipPath inset 动画） */
  .cdxName{font-family:"KaiTi","STKaiti","SimSun",serif;font-size:clamp(38px,6vh,60px);font-weight:700;letter-spacing:.32em;padding-left:.32em;line-height:1.25;
    color:#d9d8e2;text-shadow:2px 0 #853d62,-2px 0 #8cc3cd;clip-path:inset(0 100% 0 0);transition:clip-path .7s ease}
  #bootCodex.cdxTitle .cdxName{clip-path:inset(0 -10% 0 0)}
  .cdxSub{font:9px Consolas,Menlo,monospace;letter-spacing:6px;color:#d980a7;margin-top:12px;opacity:0;transition:opacity .35s}
  #bootCodex.cdxCap .cdxSub{opacity:.55}
  /* 左下角启动日志（上游 .boot-logs；内容沿用本应用 /api/state 拼出的 9 行真实信息） */
  .cdxLogs{position:absolute;left:4%;bottom:6%;z-index:4;font:clamp(6px,.85vw,10px)/1.9 Consolas,Menlo,monospace;letter-spacing:.45px;color:#968391;opacity:.75;transition:opacity .6s}
  .cdxLogs div{opacity:0;animation:bIn .3s forwards;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cdxLogs .ok{color:#d98fb2}
  #bootCodex.cdxDraw .cdxLogs{opacity:0}
  /* 后半段 HUD：四角框 + SYNC RATIO 进度 + 底部字幕 + 时间码（上游 .hud） */
  .cdxHud{position:absolute;inset:0;z-index:5;color:#f3d9e6;font-family:Consolas,Menlo,monospace;text-shadow:0 1px 7px #32203066;opacity:0;transition:opacity .45s;pointer-events:none}
  #bootCodex.cdxHudIn .cdxHud{opacity:1}
  #bootCodex.cdxClosing .cdxHud{opacity:0;transition:opacity .25s}
  .cdxCorner{position:absolute;width:32px;height:32px;border:0 solid #fce9f0;opacity:.75}
  .cdxCorner.tl{top:19px;left:19px;border-top-width:1.5px;border-left-width:1.5px}
  .cdxCorner.tr{top:19px;right:19px;border-top-width:1.5px;border-right-width:1.5px}
  .cdxCorner.bl{bottom:19px;left:19px;border-bottom-width:1.5px;border-left-width:1.5px}
  .cdxCorner.br{bottom:19px;right:19px;border-bottom-width:1.5px;border-right-width:1.5px}
  .cdxSync{position:absolute;top:8.5%;left:4%;width:23%;font-size:clamp(8px,.9vw,11px);letter-spacing:1.25px}
  .cdxSyncLabel{display:flex;justify-content:space-between;margin-bottom:7px}
  .cdxTrack{height:4px;border:1px solid #ffedf284;background:#291d3025}
  .cdxFill{height:100%;width:100%;background:#f2dfa8;transform:scaleX(0);transform-origin:left center;box-shadow:0 0 9px #e8c83299;transition:transform .1s linear}
  .cdxPhase{display:block;margin-top:8px;font-size:8px;letter-spacing:1.6px;opacity:.57}
  .cdxSubtitle{position:absolute;left:12%;right:12%;bottom:7.5%;text-align:center;font-size:clamp(15px,1.9vw,22px);font-weight:500;letter-spacing:3px;color:#f7eef2;text-shadow:0 2px 8px #291225b3;opacity:0}
  #bootCodex.cdxHudIn .cdxSubtitle{opacity:1;transition:opacity .5s .25s}
  #bootCodex.cdxSubOut .cdxSubtitle{opacity:0;transition:opacity .35s}
  .cdxCoords{display:flex;justify-content:space-between;position:absolute;bottom:3.6%;left:6%;right:6%;font-size:8px;letter-spacing:1.7px;opacity:.48}
  /* 结尾"画面合拢"（上游 11~12s：场景 scaleY 压缩 + 中缝亮线 scaleX 收缩） */
  .cdxShutter{position:absolute;z-index:8;top:50%;left:0;right:0;height:2px;background:#fff9fd;box-shadow:0 0 6px #fff,0 0 18px #f5cee8;opacity:0;transform-origin:center;pointer-events:none}
  #bootCodex.cdxClosing .cdxScene{transform:scaleY(0);opacity:0;transition:transform .38s cubic-bezier(.65,0,.85,1),opacity .32s ease-in}
  #bootCodex.cdxClosing .cdxShutter{animation:cdxShutter .75s ease forwards}
  @keyframes cdxShutter{0%{opacity:0;transform:scaleX(1)}20%{opacity:1}70%{opacity:1;transform:scaleX(1)}100%{opacity:0;transform:scaleX(0)}}
  @keyframes cdxFadeIn{from{opacity:0}to{opacity:1}}
  #bootCodex .cdxHint{position:absolute;left:0;right:0;bottom:3vh;z-index:9}
  /* ================= EVA 驾驶员认证主题（仿造 dsh-plugin-eva-theme） =================
     启动流程：NERV GIF → 红色警报 → 打字标题「选择你的驾驶员」→ 驾驶员选择
     （插入栓 + 双驾驶员卡片 + 橙色等高线）→ 语音同步进度 → 双侧舱门 → 进入聊天。
     素材（NERV logo/明日香/绫波丽/鷺巣詩郎《EM20#070720》/日语配音）为第三方版权，
     仅课堂演示；源码 MIT。角色配色由 data-pilot 切换：明日香=红黑 / 绫波丽=白蓝。 */
  #bootEva{position:absolute;inset:0;display:none;background:#000101;color:#fff1e7;overflow:hidden;
    font-family:Consolas,Menlo,monospace;isolation:isolate;
    --boot-accent:#ff354d;--boot-ink:#fff1e7;--boot-dim:#c6b7ac;
    --boot-surface:#0d0f13;--boot-panel:#14171c;--boot-line:#f33a517a;
    --boot-signal:#e5a24f;--boot-ok:#8dc358}
  #bootEva[data-pilot="rei"]{--boot-accent:#176b91;--boot-ink:#203849;--boot-dim:#476173;
    --boot-surface:#eff6fa;--boot-panel:#f7fbfd;--boot-line:#28698a59;
    --boot-signal:#926008;--boot-ok:#267263}
  #bootEva *{box-sizing:border-box}
  /* 各阶段 display 一律由本组 [data-phase] 规则控制；下方 .eva-intro/.eva-console 等类规则
     不要再写 display —— 否则与隐藏规则同特异性(1,1,0)且靠后，会覆盖隐藏规则导致该层常显
     （曾因 .eva-intro 常显 + z-index:5 黑底，把选择页永久盖住，表现为"卡在打字标题"） */
  #bootEva [data-role]{display:none}
  #bootEva[data-phase="gif"]>[data-role="gif"],
  #bootEva[data-phase="intro"]>[data-role="intro"]{display:grid}
  #bootEva[data-phase="emergency"]>[data-role="emergency"],
  #bootEva[data-phase="handoff"]>[data-role="gates"]{display:block}
  #bootEva[data-phase="loading"]>[data-role="loading"]{display:flex}
  /* 选择页容器是 .eva-console（flex 列布局）：若按上面规则显示为 block，
     内部 flex:1 的驾驶舱网格会失去高度，驾驶员卡片(1fr 行)塌陷成 0×0 不可见——故单独用 flex 显示 */
  #bootEva[data-phase="select"]>[data-role="select"]{display:flex}
  /* —— 阶段1：NERV GIF（两倍速，约 3.84s） —— */
  #bootEva .eva-boot-gifwrap{position:absolute;inset:0;place-items:center;background:#000101}
  #bootEva .eva-boot-gif{width:min(512px,calc(100vw - 24px),calc(100dvh - 24px));height:auto;aspect-ratio:1;object-fit:contain}
  /* —— 阶段2：红色警报（nerv-emergency.svg，3s 闪烁） —— */
  #bootEva .eva-emergency{position:absolute;inset:0;overflow:hidden;background:#000;pointer-events:none}
  #bootEva .eva-emergency>svg{display:block;width:100%;height:100%;animation:evaAlertSeq 3s ease-in-out both}
  #bootEva .eva-alert-cell{animation:evaAlertCell 1.25s ease-in-out infinite;animation-delay:var(--alert-lag,0s)}
  @keyframes evaAlertSeq{0%{opacity:0}10%{opacity:.96}28%{opacity:.42}45%{opacity:.98}62%{opacity:.3}78%{opacity:.96}91%{opacity:.68}100%{opacity:0}}
  @keyframes evaAlertCell{0%,100%{opacity:1}50%{opacity:.24}}
  /* —— 阶段3：黑底打字标题 —— */
  #bootEva .eva-intro{position:absolute;inset:0;z-index:5;place-items:center;background:#000101;color:#e5e9e7;overflow:hidden}
  #bootEva .eva-intro .eva-intro-copy{position:relative;z-index:1;text-align:center}
  #bootEva .eva-intro-kicker{margin:0 0 24px;color:#81908f;font:10px/1.6 Consolas,Menlo,monospace;letter-spacing:.28em}
  #bootEva .eva-intro-title{font:500 clamp(26px,4vw,56px)/1.5 "KaiTi","STKaiti",serif;
    letter-spacing:.14em;color:#e5e9e7;white-space:nowrap;margin:0 0 26px}
  #bootEva .eva-intro-typed::after{content:"";display:inline-block;width:2px;height:.85em;margin-left:.12em;
    background:#cbd9d8;vertical-align:-.03em;animation:evaCaret .72s steps(1,end) infinite}
  #bootEva .eva-intro-rule{display:block;width:90px;height:1px;margin:0 auto;
    background:linear-gradient(90deg,#ff354d 0 48%,transparent 48% 52%,#176b91 52%);
    transform-origin:center;animation:evaRuleIn .7s ease-out both}
  @keyframes evaCaret{0%,100%{opacity:1}50%{opacity:0}}
  @keyframes evaRuleIn{from{transform:scaleX(0)}to{transform:scaleX(1)}}
  /* —— 阶段4：驾驶员选择（等高线 + 插入栓 + 双卡片） —— */
  #bootEva .eva-console{position:absolute;inset:0;flex-direction:column;background:var(--boot-surface);
    padding:clamp(14px,3vh,38px) clamp(18px,3vw,64px) clamp(10px,2vh,22px);gap:clamp(10px,2vh,20px);color:var(--boot-ink)}
  #bootEva .eva-console .eva-contours{position:absolute;inset:0;width:100%;height:100%;color:#f49344;opacity:.5;pointer-events:none}
  #bootEva .eva-console .eva-contours *{stroke:#f49344;fill:none;stroke-width:1.4}
  #bootEva .eva-console .eva-watermark{position:absolute;right:-.03em;bottom:-.1em;color:#f49344;opacity:.04;
    font:800 clamp(220px,40vw,820px)/1 Consolas,Menlo,monospace;letter-spacing:-.1em;pointer-events:none}
  #bootEva .eva-boot-header{position:relative;z-index:1;display:flex;justify-content:space-between;align-items:flex-start;
    border-top:2px solid var(--boot-accent);padding-top:12px}
  #bootEva .eva-boot-kicker{margin:0;color:var(--boot-accent);font:10px/1.6 Consolas,Menlo,monospace;letter-spacing:.22em}
  #bootEva .eva-boot-kicker small{display:block;color:var(--boot-dim);font-size:8px;letter-spacing:.16em}
  #bootEva .eva-boot-title{margin:0;color:var(--boot-ink);font:500 clamp(24px,3vw,46px)/1.3 "KaiTi","STKaiti",serif;letter-spacing:.12em}
  #bootEva .eva-boot-hint{margin:8px 0 0;color:var(--boot-dim);font:10px/1.6 Consolas,Menlo,monospace}
  #bootEva .eva-boot-grid{position:relative;z-index:1;flex:1;display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);
    gap:clamp(14px,2.5vw,40px);align-items:stretch;min-height:0}
  /* 左栏：图纸风插入栓展示舱——纸面 + 红色标注网格 + 大圆表盘 + 立式插入栓图（对齐视频选择页/同步页左栏） */
  #bootEva .eva-entry-bay{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;min-width:0;container-type:size;
    border:1px solid var(--boot-line);background:
      repeating-linear-gradient(0deg,transparent 0 27px,color-mix(in srgb,var(--boot-accent) 5%,transparent) 27px 28px),
      repeating-linear-gradient(90deg,transparent 0 27px,color-mix(in srgb,var(--boot-accent) 5%,transparent) 27px 28px),
      var(--boot-panel);overflow:hidden}
  #bootEva .eva-entry-label{position:absolute;left:14px;top:12px;color:var(--boot-dim);font:8px/1.6 Consolas,Menlo,monospace;letter-spacing:.16em;z-index:1}
  #bootEva .eva-entry-label b{display:block;color:var(--boot-accent);font-size:11px}
  /* 圆表盘：双圈 + 锥形刻度环 + 缓慢自转（垫在插入栓线稿下层） */
  #bootEva .eva-entry-dial{position:absolute;inset:0;margin:auto;width:min(64%,44vh);aspect-ratio:1;border-radius:50%;
    border:1px solid color-mix(in srgb,var(--boot-accent) 45%,transparent);
    box-shadow:inset 0 0 0 14px color-mix(in srgb,var(--boot-accent) 4%,transparent);
    background:repeating-conic-gradient(from 0deg,color-mix(in srgb,var(--boot-accent) 20%,transparent) 0 .6deg,transparent .6deg 6deg);
    animation:evaDialSpin 90s linear infinite}
  #bootEva .eva-entry-dial::after{content:"";position:absolute;inset:16%;border-radius:50%;
    border:1px dashed color-mix(in srgb,var(--boot-accent) 40%,transparent)}
  @keyframes evaDialSpin{to{transform:rotate(360deg)}}
  /* 插入栓：装配容器倾斜 14°，筒体按装载区等比缩放（移植 dsh-plugin-eva-theme 的容器查询方案） */
  #bootEva .eva-entry-machine{--plug-clearance:96px;--plug-width:128cqw;position:relative;flex:none;z-index:1;
    height:min(calc(100cqh - var(--plug-clearance)),var(--plug-width));aspect-ratio:1/2;color:var(--boot-dim)}
  #bootEva .eva-entry-assembly{position:absolute;inset:0;transform:rotate(14deg)}
  #bootEva .eva-entry-plug{display:block;width:100%;height:100%;color:inherit;overflow:visible;
    filter:drop-shadow(0 10px 16px rgba(0,0,0,.18));animation:evaPlugFloat 5.5s ease-in-out infinite}
  @keyframes evaPlugFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
  /* 同步阶段：插入栓随驾驶员轻微变色（明日香偏红 / 绫波丽偏蓝） */
  #bootEva[data-pilot="asuka"] .eva-entry-plug{filter:sepia(.5) saturate(2.4) hue-rotate(-28deg) brightness(.96) drop-shadow(0 10px 16px rgba(0,0,0,.18))}
  #bootEva[data-pilot="rei"] .eva-entry-plug{filter:sepia(.35) saturate(1.6) hue-rotate(150deg) brightness(1.04) drop-shadow(0 10px 16px rgba(0,0,0,.18))}
  /* 拖拽悬停态：插入栓舱高亮 + 幻影跟随光标 */
  #bootEva .eva-entry-bay[data-over="1"]{border-color:var(--boot-accent);box-shadow:inset 0 0 90px color-mix(in srgb,var(--boot-accent) 14%,transparent)}
  #bootEva .eva-pilot-ghost{position:fixed;left:0;top:0;z-index:40;pointer-events:none;opacity:.85;will-change:transform;
    border:1px solid var(--boot-accent);background-color:var(--boot-surface);background-repeat:no-repeat;
    background-position:center;background-size:contain;box-shadow:0 12px 60px rgba(0,0,0,.6)}
  #bootEva .eva-entry-target{position:absolute;left:10px;right:10px;bottom:12px;margin:0;text-align:center;
    color:var(--boot-accent);font:9px/1.5 Consolas,Menlo,monospace;letter-spacing:.12em}
  #bootEva .eva-entry-target::before{content:"";display:block;width:58px;height:3px;margin:0 auto 8px;
    background:repeating-linear-gradient(135deg,var(--boot-signal) 0 4px,transparent 4px 8px)}
  /* 选择页固定图纸亮色（视频：白纸底红标注，两卡一暗一亮）；写在 [data-pilot] 变量之后以覆盖驾驶员配色 */
  #bootEva[data-phase="select"]{--boot-accent:#c9352e;--boot-ink:#2a2320;--boot-dim:#8a7f76;
    --boot-surface:#f7f4ee;--boot-panel:#fffdf8;--boot-line:#c9352e70;--boot-signal:#e5a24f}
  /* 右栏驾驶员卡：明日香=暗黑红调、绫波丽=瓷白蓝调，各卡配色独立（对齐视频） */
  #bootEva .eva-pilot-list{display:grid;grid-template-rows:minmax(0,1fr) minmax(0,1fr);gap:clamp(10px,2vh,24px);min-height:0}
  #bootEva .eva-pilot-card{--card-accent:#ff354d;--card-bg:#0d0f13;--card-ink:#fff1e7;position:relative;display:grid;
    grid-template-columns:44% 1fr;align-items:center;text-align:left;min-height:0;padding:0;background:var(--card-bg);
    border:1px solid color-mix(in srgb,var(--card-accent) 55%,transparent);border-left:3px solid var(--card-accent);
    border-radius:0;color:var(--card-ink);cursor:pointer;overflow:hidden;user-select:none;-webkit-user-select:none;
    transition:transform .25s ease,border-color .2s ease}
  /* 线稿头像禁止原生拖拽/接收指针事件：拖动头像会吞掉卡片的 click（按下与抬起不在同一元素） */
  #bootEva .eva-pilot-face{pointer-events:none;-webkit-user-drag:none}
  #bootEva .eva-pilot-card[data-pilot="rei"]{--card-accent:#176b91;--card-bg:#f4f9fc;--card-ink:#203849}
  #bootEva .eva-pilot-card:hover{border-color:var(--card-accent);transform:translateY(-2px)}
  #bootEva .eva-pilot-card::before{content:attr(data-unit);position:absolute;right:-.04em;bottom:-.2em;color:var(--card-accent);
    font:800 clamp(90px,14vw,220px)/1 Consolas,Menlo,monospace;letter-spacing:-.1em;opacity:.1;pointer-events:none;z-index:2}
  /* 卡片头像：整幅角色线稿肖像铺满左格（对齐视频卡片里的红发/蓝发线稿） */
  #bootEva .eva-pilot-face{display:block;width:100%;height:100%;min-height:120px;object-fit:cover;object-position:center top;
    opacity:.9;pointer-events:none;filter:contrast(1.05)}
  #bootEva .eva-pilot-card[data-pilot="asuka"] .eva-pilot-face{background:#160b0d}
  #bootEva .eva-pilot-info{display:block;position:relative;min-width:0;padding:12px 14px;z-index:1}
  #bootEva .eva-pilot-number{display:block;color:var(--card-accent);font:700 clamp(26px,3.6vw,52px)/1 Consolas,Menlo,monospace;letter-spacing:-.06em}
  #bootEva .eva-pilot-info b{display:block;margin-top:6px;color:var(--card-accent);font:500 clamp(15px,2vw,26px)/1.3 "KaiTi","STKaiti",serif;letter-spacing:.12em}
  #bootEva .eva-pilot-info small{display:block;margin-top:4px;color:var(--card-accent);opacity:.75;font:9px/1.4 Consolas,Menlo,monospace;letter-spacing:.08em}
  #bootEva .eva-pilot-info em{display:block;margin-top:8px;color:var(--card-accent);opacity:.75;font:normal 9px/1.4 Consolas,Menlo,monospace;letter-spacing:.08em}
  /* 同步页：标题行（大字名字 + 右侧同步环）+ 红色波形条 + 进度（对齐视频同步页布局） */
  #bootEva .eva-sync-head{display:flex;align-items:center;justify-content:space-between;gap:clamp(12px,3vw,34px)}
  #bootEva .eva-sync-head h2{margin:0;color:var(--boot-accent);font:500 clamp(30px,4.6vw,66px)/1.25 "KaiTi","STKaiti",serif;letter-spacing:.16em}
  #bootEva .eva-wave{position:relative;height:30px;border:1px solid color-mix(in srgb,var(--boot-accent) 45%,transparent);
    overflow:hidden;background:color-mix(in srgb,var(--boot-accent) 5%,transparent)}
  #bootEva .eva-wave i{position:absolute;inset:0;display:block;transform:scaleX(0);transform-origin:left;
    background:repeating-linear-gradient(90deg,var(--boot-accent) 0 3px,transparent 3px 7px);
    transition:transform .2s linear;
    -webkit-mask:radial-gradient(8px 22px at 50% 50%,#000 60%,transparent) ;mask:radial-gradient(8px 22px at 50% 50%,#000 60%,transparent)}
  #bootEva .eva-wave::after{content:"";position:absolute;inset:0;
    background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--boot-accent) 30%,transparent),transparent);
    background-size:200% 100%;animation:evaWaveScan 1.6s linear infinite}
  @keyframes evaWaveScan{to{background-position:-200% 0}}
  #bootEva .eva-sync-head .eva-sync-orbit{width:min(24vh,180px);flex:none}
  #bootEva .eva-boot-footer{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;
    gap:16px;border-top:1px solid var(--boot-line);padding-top:10px;min-width:0}
  #bootEva .eva-boot-status{margin:0;display:flex;gap:10px;align-items:center;color:var(--boot-dim);font:10px/1.5 Consolas,Menlo,monospace;letter-spacing:.1em}
  #bootEva .eva-boot-status::before{content:"";width:6px;height:6px;flex:none;background:var(--boot-accent)}
  /* —— 阶段5：装载同步（语音 + 进度 + 同步环） —— */
  #bootEva .eva-boot-loading{position:absolute;inset:0;flex-direction:column;justify-content:center;
    gap:clamp(14px,2.5vh,30px);padding:clamp(20px,4vw,64px);border:1px solid var(--boot-line);background:var(--boot-surface);color:var(--boot-ink)}
  #bootEva .eva-boot-loading h2{margin:0;color:var(--boot-accent);font:500 clamp(26px,4vw,58px)/1.3 "KaiTi","STKaiti",serif;letter-spacing:.14em}
  #bootEva .eva-boot-code{color:var(--boot-dim);font:10px/1.6 Consolas,Menlo,monospace;letter-spacing:.15em}
  #bootEva .eva-sync-main{display:grid;grid-template-columns:minmax(0,1fr) minmax(88px,22%);align-items:center;gap:18px}
  #bootEva .eva-sync-orbit{position:relative;aspect-ratio:1;color:var(--boot-accent);width:min(46vh,80%,320px);justify-self:center}
  #bootEva .eva-sync-orbit svg{display:block;width:100%;height:100%}
  #bootEva .eva-sync-ring-track{fill:none;stroke:var(--boot-line);stroke-width:6}
  #bootEva .eva-sync-ring-meter{fill:none;stroke:var(--boot-accent);stroke-width:6;stroke-linecap:round;
    stroke-dasharray:440;stroke-dashoffset:440;transform:rotate(-90deg);transform-origin:90px 90px;transition:stroke-dashoffset .12s linear}
  #bootEva .eva-sync-readout{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
  #bootEva .eva-sync-value{font:400 clamp(20px,2.6vw,40px)/1 Consolas,Menlo,monospace;letter-spacing:-.06em}
  #bootEva .eva-sync-readout small{margin-top:8px;font:8px/1 Consolas,Menlo,monospace;letter-spacing:.16em}
  #bootEva .eva-boot-meter{height:16px;overflow:hidden;border:1px solid var(--boot-line);padding:3px}
  #bootEva .eva-boot-meter i{display:block;width:100%;height:100%;
    background:repeating-linear-gradient(90deg,var(--boot-accent) 0 7px,transparent 7px 10px);
    transform:scaleX(0);transform-origin:left}
  #bootEva .eva-boot-progress-label{margin-top:8px;display:flex;justify-content:space-between;color:var(--boot-accent);font:11px/1.5 Consolas,Menlo,monospace}
  #bootEva .eva-boot-progress-label time{color:var(--boot-dim)}
  #bootEva .eva-sync-caption{margin-top:6px;color:var(--boot-dim);font:8px/1.5 Consolas,Menlo,monospace;letter-spacing:.1em}
  /* —— 阶段6：双侧机械舱门 + 交接字幕 —— */
  #bootEva .eva-boot-gate{position:absolute;top:0;bottom:0;width:50.3%;z-index:20;pointer-events:none;overflow:hidden;
    background:var(--boot-surface);color:var(--boot-accent)}
  #bootEva .eva-boot-gate::before{content:"";position:absolute;inset:18px;border:1px solid var(--boot-line);
    background:repeating-linear-gradient(135deg,transparent 0 18px,color-mix(in srgb,var(--boot-accent) 3%,transparent) 18px 19px)}
  #bootEva .eva-boot-gate::after{content:"";position:absolute;top:0;bottom:0;width:3px;
    background:repeating-linear-gradient(0deg,var(--boot-accent) 0 12px,transparent 12px 20px);opacity:.7}
  #bootEva .eva-boot-gate.left{left:0;border-right:1px solid var(--boot-accent);animation:evaGateLeft 1.6s cubic-bezier(.65,0,.2,1) both}
  #bootEva .eva-boot-gate.right{right:0;border-left:1px solid var(--boot-accent);animation:evaGateRight 1.6s cubic-bezier(.65,0,.2,1) both}
  #bootEva .eva-boot-gate.left::after{right:10px}
  #bootEva .eva-boot-gate.right::after{left:10px}
  @keyframes evaGateLeft{0%,18%{transform:translateX(0)}90%,100%{transform:translateX(-102%)}}
  @keyframes evaGateRight{0%,18%{transform:translateX(0)}90%,100%{transform:translateX(102%)}}
  #bootEva .eva-boot-clearance{position:absolute;z-index:21;left:50%;top:50%;transform:translate(-50%,-50%);padding:13px 22px;
    background:var(--boot-surface);border-block:1px solid var(--boot-accent);color:var(--boot-accent);text-align:center;
    white-space:nowrap;pointer-events:none;animation:evaClearance 1.6s ease-out both}
  #bootEva .eva-boot-clearance b{display:block;font:400 clamp(15px,2vw,26px)/1.4 "KaiTi","STKaiti",serif;letter-spacing:.22em}
  #bootEva .eva-boot-clearance small{font:8px/1.6 Consolas,Menlo,monospace;letter-spacing:.16em}
  @keyframes evaClearance{0%{opacity:0}16%,32%{opacity:1}55%,100%{opacity:0}}
  /* 声音开关（负责背景乐与语音；默认静音，点开关可开） */
  #bootEva .eva-sound{position:absolute;right:22px;bottom:20px;z-index:30;color:var(--boot-dim);
    background:rgba(10,10,10,.5);border:1px solid var(--boot-line)}
  #bootEva .eva-sound:hover{border-color:var(--boot-accent);color:var(--boot-accent)}
  #bootEva .bootHint{position:absolute;left:0;right:0;bottom:3vh;z-index:30;margin-top:0}
  /* ================= EVA 双生驾驶舱皮肤（选完驾驶员后聊天主界面换肤，对齐视频 DARK/LIGHT MODE） =================
     思路：页面所有颜色都走 --bg/--panel/--line/--gold/--txt/--dim 变量，皮肤只覆写变量即可整体换装；
     再叠加装饰层：左上时钟、角色线稿背景（复用 #chatBg）、编号大水印、欢迎横幅。 */
  body.eva-asuka{--bg:#0b0507;--panel:#160b0d;--line:#5a2330;--gold:#ff354d;--txt:#ffeae4;--dim:#c7938a}
  body.eva-rei{--bg:#eef4f8;--panel:#f7fafc;--line:#b9d4e2;--gold:#176b91;--txt:#203849;--dim:#476173}
  body.eva-asuka #chatBg,body.eva-rei #chatBg{display:block}
  /* 明日香：亮红线条画（人无物线稿，暗底上可见；不遮挡右下角 02 编号水印） */
  body.eva-asuka #chatBg{opacity:.24}
  body.eva-rei #chatBg{opacity:.2;mix-blend-mode:multiply}
  /* 编号大水印（聊天区右下角，02/00） */
  #evaWatermark{display:none;position:absolute;right:-10px;bottom:-30px;z-index:0;pointer-events:none;
    font:800 clamp(160px,24vw,380px)/1 Consolas,Menlo,monospace;letter-spacing:-.08em;color:var(--gold);opacity:.05}
  body.eva-asuka #evaWatermark,body.eva-rei #evaWatermark{display:block}
  /* 左上 EVA 时钟 */
  #evaClock{display:none;font:700 13px/1 Consolas,Menlo,monospace;letter-spacing:.14em;color:var(--gold);
    border:1px solid var(--gold);padding:3px 8px;border-radius:4px}
  body.eva-asuka #evaClock,body.eva-rei #evaClock{display:inline-block}
  /* 欢迎横幅：进入聊天后中央浮现，数秒后淡出 */
  #evaBanner{position:fixed;left:50%;top:34%;transform:translate(-50%,-50%);z-index:60;pointer-events:none;
    text-align:center;opacity:0;transition:opacity .8s ease}
  #evaBanner.show{opacity:1}
  #evaBanner b{display:block;font:500 clamp(26px,4vw,44px)/1.3 "KaiTi","STKaiti",serif;letter-spacing:.2em;color:var(--gold);
    text-shadow:0 2px 24px rgba(0,0,0,.35)}
  #evaBanner small{display:block;margin-top:10px;font:10px Consolas,Menlo,monospace;letter-spacing:.3em;color:var(--dim)}
  /* ================= EVA 电影感启动主题（仿造 dsh-eva-boot 1.1.5 · style:"cine"） =================
     特效语言：深色底 + HUD 框线 + 网格 + 尘埃 + 线稿揭幕 + 海报淡入 + 金属字标。
     时间轴：起播门(等待点击解锁音频) → HUD → 02 字标+光带 → 三段机构
     （插入栓投放 → LCL 注入 → 神经接驳）→ 线稿扫过 → 海报层 → 金属字标 → 淡出。
     素材（NERV/明日香/二号机插画/启动音频）为第三方版权，仅课堂演示。 */
  #bootCine{position:absolute;inset:0;display:none;overflow:hidden;background:#080506;color:#ffeae4;
    font-family:"Microsoft YaHei",sans-serif;isolation:isolate;
    --cn-text:#ffeae4;--cn-dim:#c7938a;--cn-faint:#7c5a54;
    --cn-line:rgba(255,140,125,.26);--cn-accent:#ff4a3d;--cn-amber:#ff8a1f;
    --cn-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  /* —— 素材层：海报（从第一帧就铺满，后期提亮）与线稿 —— */
  #bootCine .cine-bg{position:absolute;inset:0;background:#080506;opacity:0;
    transition:opacity 1400ms cubic-bezier(.3,.6,.3,1),filter 1600ms cubic-bezier(.3,.6,.3,1)}
  #bootCine.is-backdrop .cine-bg{opacity:.5;filter:saturate(.82) contrast(1.06) brightness(.48)}
  #bootCine.is-line .cine-bg{opacity:.22;filter:saturate(.6) brightness(.32)}
  #bootCine.is-poster .cine-bg{opacity:1;filter:none}
  #bootCine .cine-bg.is-in{opacity:1}
  #bootCine .cine-bg img{width:100%;height:100%;object-fit:cover;display:block;
    filter:saturate(1.04) contrast(1.06) brightness(.8);animation:cineBgZoom 40s ease-out both}
  @keyframes cineBgZoom{from{transform:scale(1.07)}to{transform:scale(1)}}
  #bootCine .cine-bg::after{content:"";position:absolute;inset:0;pointer-events:none;background:
    linear-gradient(90deg,rgba(8,5,6,.96) 0%,rgba(8,5,6,.74) 34%,rgba(8,5,6,.24) 56%,rgba(8,5,6,.55) 78%,rgba(8,5,6,.72) 100%),
    linear-gradient(0deg,rgba(8,5,6,.92) 0%,transparent 46%),
    linear-gradient(180deg,rgba(8,5,6,.55) 0%,transparent 22%),
    radial-gradient(120% 90% at 70% 40%,transparent 24%,rgba(8,5,6,.7) 100%)}
  /* 线稿层：遮罩横扫（105deg 方向的一道光把线稿"擦"出来） */
  #bootCine .cine-lineart{position:absolute;inset:0;opacity:0;transition:opacity 900ms ease;pointer-events:none}
  #bootCine .cine-lineart.is-in{opacity:1}
  #bootCine .cine-lineart img{width:100%;height:100%;object-fit:cover;mix-blend-mode:screen;
    filter:brightness(1.5) contrast(1.25) saturate(0);
    -webkit-mask-image:linear-gradient(105deg,transparent 12%,#000 46%,#000 74%,transparent 96%);
    mask-image:linear-gradient(105deg,transparent 12%,#000 46%,#000 74%,transparent 96%);
    -webkit-mask-size:260% 100%;mask-size:260% 100%;-webkit-mask-position:100% 0;mask-position:100% 0;
    animation:cineLineartSweep 2200ms cubic-bezier(.4,.1,.2,1) forwards}
  @keyframes cineLineartSweep{from{-webkit-mask-position:100% 0;mask-position:100% 0}to{-webkit-mask-position:0% 0;mask-position:0% 0}}
  /* —— 网格 / 尘埃画布 / 暗角 —— */
  #bootCine .cine-mesh{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity 1400ms ease 300ms;
    background-image:repeating-linear-gradient(74deg,rgba(255,150,135,.35) 0 1px,transparent 1px 46px),
      repeating-linear-gradient(-16deg,rgba(255,150,135,.28) 0 1px,transparent 1px 42px);
    -webkit-mask-image:radial-gradient(46% 62% at 74% 44%,#000 0%,rgba(0,0,0,.55) 46%,transparent 78%);
    mask-image:radial-gradient(46% 62% at 74% 44%,#000 0%,rgba(0,0,0,.55) 46%,transparent 78%);mix-blend-mode:screen}
  #bootCine.is-poster .cine-mesh{opacity:.5}
  #bootCine .cine-dust{position:absolute;inset:0;pointer-events:none}
  #bootCine .cine-vignette{position:absolute;inset:0;pointer-events:none;background:
    radial-gradient(120% 120% at 50% 50%,transparent 52%,rgba(0,0,0,.55) 100%),
    repeating-linear-gradient(0deg,rgba(255,220,210,.028) 0 1px,transparent 1px 3px)}
  /* —— HUD：品牌块 / 左上任务列表 / 右上角标 / 右中数据 / 左下脚注 —— */
  #bootCine .cine-hud{position:absolute;inset:0;padding:40px 52px 36px;pointer-events:none;
    font-family:var(--cn-mono);font-size:10px;letter-spacing:.18em;color:var(--cn-dim);
    text-shadow:0 1px 10px rgba(0,0,0,.85),0 0 2px rgba(0,0,0,.7)}
  #bootCine.is-hud .cine-hud{animation:cineHudIn 700ms ease both}
  @keyframes cineHudIn{from{opacity:0}to{opacity:1}}
  #bootCine .cine-brand{display:flex;align-items:flex-start;gap:12px}
  #bootCine .cine-crown{width:26px;height:18px;flex:none;margin-top:2px;opacity:.9;color:var(--cn-dim)}
  #bootCine .cine-brand-main{display:grid;gap:6px}
  #bootCine .cine-brand-name{font-family:"Microsoft YaHei",sans-serif;font-size:17px;font-weight:500;letter-spacing:.02em;color:var(--cn-text)}
  #bootCine .cine-brand-sub{font-size:9.5px;line-height:1.55;letter-spacing:.2em;color:var(--cn-faint);text-transform:uppercase}
  #bootCine .cine-rule{position:relative;height:1px;margin-top:14px;width:min(320px,42vw);
    background:linear-gradient(to right,var(--cn-line),transparent)}
  #bootCine .cine-rule::after{content:"+";position:absolute;right:-10px;top:-7px;font-size:11px;color:var(--cn-line)}
  #bootCine .cine-steps{position:absolute;left:52px;top:148px;display:grid;gap:7px;
    font-size:9.5px;letter-spacing:.26em;text-transform:uppercase}
  #bootCine .cine-step{position:relative;padding-left:12px;color:var(--cn-faint);transition:color 320ms ease}
  #bootCine .cine-step::before{content:"";position:absolute;left:0;top:50%;width:4px;height:4px;margin-top:-2px;background:currentColor;opacity:.5}
  #bootCine .cine-step.is-on{color:var(--cn-accent)}
  #bootCine .cine-step.is-done{color:var(--cn-dim)}
  #bootCine .cine-step i{position:absolute;left:0;top:50%;height:1px;width:0;background:var(--cn-accent);
    box-shadow:0 0 8px var(--cn-accent);transition:width 420ms ease}
  #bootCine .cine-step.is-on i{width:34px}
  #bootCine .cine-topright{position:absolute;right:52px;top:44px;text-align:right;font-size:9.5px;
    letter-spacing:.2em;color:var(--cn-faint);display:grid;gap:8px;justify-items:end}
  #bootCine .cine-topright b{font-weight:500;color:var(--cn-dim);font-size:10.5px}
  #bootCine .cine-topright span{display:block;width:92px;height:1px;background:linear-gradient(to left,var(--cn-line),transparent)}
  #bootCine .cine-midright{position:absolute;right:52px;top:46%;text-align:right;display:grid;gap:6px;
    font-size:9px;line-height:1.7;letter-spacing:.24em;color:var(--cn-faint);text-transform:uppercase}
  #bootCine .cine-midright b{display:block;width:62px;height:1px;margin-left:auto;background:var(--cn-accent);opacity:.7;
    box-shadow:0 0 10px rgba(255,74,61,.55)}
  #bootCine .cine-footer{position:absolute;left:52px;bottom:40px;font-size:9px;line-height:1.75;
    letter-spacing:.22em;color:var(--cn-faint);text-transform:uppercase}
  #bootCine .cine-footer::after{content:"";display:block;width:84px;height:1px;margin-top:10px;
    background:linear-gradient(to right,var(--cn-line),transparent)}
  /* —— 中央 02 字标（细线描边 + 擦除揭幕）+ 横穿光带 —— */
  #bootCine .cine-mark{position:absolute;left:52px;top:42%;transform:translateY(-50%);width:252px;height:200px;
    opacity:.92;pointer-events:none;transition:transform 760ms cubic-bezier(.3,.7,.3,1),opacity 620ms ease}
  #bootCine.is-stage .cine-mark{opacity:0;transform:translateY(-50%) scale(.92)}
  #bootCine .cine-num{font-family:"Microsoft YaHei",sans-serif;font-size:150px;font-weight:200;line-height:1;
    letter-spacing:.04em;color:transparent;-webkit-text-stroke:1.5px rgba(255,236,230,.85);
    filter:drop-shadow(0 0 10px rgba(255,74,61,.4));clip-path:inset(0 100% 0 0)}
  #bootCine.is-mark .cine-num{animation:cineNumWipe 1250ms cubic-bezier(.5,.1,.2,1) forwards}
  @keyframes cineNumWipe{to{clip-path:inset(0 0 0 0)}}
  #bootCine .cine-streak{position:absolute;left:-40px;right:46%;top:54%;height:1px;opacity:0;
    background:linear-gradient(to right,transparent,rgba(255,140,110,.5),#fff2ea,rgba(255,140,110,.5),transparent);
    filter:drop-shadow(0 0 6px rgba(160,220,255,.8))}
  #bootCine.is-mark .cine-streak{animation:cineStreak 1100ms cubic-bezier(.3,.7,.2,1) 700ms forwards}
  @keyframes cineStreak{0%{opacity:0;transform:scaleX(.15);transform-origin:left}40%{opacity:1}100%{opacity:.85;transform:scaleX(1);transform-origin:left}}
  #bootCine .cine-streak::after{content:"";position:absolute;right:42%;top:-3px;width:7px;height:7px;border-radius:50%;
    background:#fff3ef;box-shadow:0 0 16px 4px rgba(255,120,100,.85)}
  /* 打字行（阶段开始后由机构面板接替，自动淡出） */
  #bootCine .cine-log{position:absolute;left:54px;bottom:34%;font-family:var(--cn-mono);font-size:10px;
    letter-spacing:.16em;color:rgba(255,74,61,.85);min-height:14px;transition:opacity 420ms ease}
  #bootCine .cine-log::before{content:"> ";color:var(--cn-faint)}
  #bootCine .cine-log::after{content:"";display:inline-block;width:6px;height:11px;margin-left:3px;
    background:rgba(255,74,61,.7);vertical-align:-1px;animation:cineCaret 1s steps(1) infinite}
  @keyframes cineCaret{50%{opacity:0}}
  #bootCine.is-stage .cine-log{opacity:0}
  /* —— 三段机构面板（同位叠放，is-on 轮流点亮） —— */
  #bootCine .cine-stage{position:absolute;display:grid;left:52px;top:33%;width:min(380px,40vw);
    pointer-events:none;transition:opacity 600ms ease,transform 700ms ease}
  #bootCine.is-stage-out .cine-stage{opacity:0;transform:translateY(-14px)}
  #bootCine .cine-panel{grid-area:1/1;opacity:0;transform:translateY(10px);
    transition:opacity 380ms ease,transform 480ms cubic-bezier(.2,.7,.3,1)}
  #bootCine .cine-panel.is-on{opacity:1;transform:none}
  #bootCine .cine-panel-k{font-family:var(--cn-mono);font-size:10px;letter-spacing:.3em;color:var(--cn-accent);text-transform:uppercase}
  #bootCine .cine-panel-t{margin:8px 0 18px;font-size:22px;font-weight:300;letter-spacing:.1em;color:var(--cn-text)}
  /* 插入栓：三层舱口 + 下行栓体 + 深度读数 */
  #bootCine .cine-plug{display:flex;align-items:center;gap:22px}
  #bootCine .cine-plug svg{width:136px;height:136px;overflow:visible}
  #bootCine .cine-plug .r1,#bootCine .cine-plug .r2,#bootCine .cine-plug .r3{fill:none;stroke:rgba(255,140,125,.35);stroke-width:1}
  #bootCine .cine-plug .r2{stroke:rgba(255,140,125,.55);stroke-dasharray:3 6}
  #bootCine .cine-plug .r3{stroke:rgba(255,74,61,.75)}
  #bootCine .cine-plug .plug-g rect{fill:rgba(255,74,61,.16);stroke:rgba(255,236,230,.85);stroke-width:1.2;
    filter:drop-shadow(0 0 8px rgba(255,74,61,.55))}
  #bootCine .cine-panel.is-on .cine-plug .plug-g{animation:cinePlugIn 1500ms cubic-bezier(.4,.1,.2,1) forwards}
  @keyframes cinePlugIn{from{transform:translateY(-30px);opacity:.25}to{transform:translateY(16px);opacity:1}}
  #bootCine .cine-plug-depth{font-family:var(--cn-mono);font-size:10px;letter-spacing:.22em;color:var(--cn-faint)}
  #bootCine .cine-plug-depth b{display:block;margin-top:6px;font-size:26px;font-weight:300;letter-spacing:.02em;
    color:var(--cn-text);font-variant-numeric:tabular-nums}
  /* LCL：液面上升 + 四项参数 */
  #bootCine .cine-lcl{display:flex;align-items:stretch;gap:22px}
  #bootCine .cine-tank{position:relative;width:62px;height:132px;border:1px solid rgba(255,140,125,.35);
    overflow:hidden;background:rgba(255,74,61,.04)}
  #bootCine .cine-tank i{position:absolute;left:0;right:0;bottom:0;height:0;
    background:linear-gradient(180deg,rgba(255,138,31,.55),rgba(255,74,61,.65));
    box-shadow:0 0 18px rgba(255,110,80,.5) inset;transition:height 1700ms cubic-bezier(.25,.8,.3,1)}
  #bootCine .cine-panel.is-on .cine-tank i{height:76%}
  #bootCine .cine-tank i::after{content:"";position:absolute;left:-20%;right:-20%;top:-4px;height:8px;
    background:radial-gradient(50% 100% at 50% 100%,rgba(255,220,190,.85),transparent 70%);
    animation:cineLclWave 2.4s ease-in-out infinite}
  @keyframes cineLclWave{0%,100%{transform:translateY(0) scaleX(1);opacity:.7}50%{transform:translateY(2px) scaleX(1.08);opacity:1}}
  #bootCine .cine-tank em{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
    font-family:var(--cn-mono);font-size:9px;font-style:normal;letter-spacing:.24em;color:rgba(255,236,230,.75);mix-blend-mode:screen}
  #bootCine .cine-params{margin:0;display:grid;gap:9px;align-content:center;flex:1}
  #bootCine .cine-params>div{display:flex;align-items:baseline;justify-content:space-between;gap:14px;
    padding-bottom:6px;border-bottom:1px solid rgba(255,140,125,.12)}
  #bootCine .cine-params dt{font-size:11px;letter-spacing:.14em;color:var(--cn-dim)}
  #bootCine .cine-params dd{margin:0;font-family:var(--cn-mono);font-size:13px;letter-spacing:.06em;
    color:var(--cn-text);font-variant-numeric:tabular-nums}
  /* 神经接驳：同步率弧 */
  #bootCine .cine-sync{position:relative;width:150px;height:150px}
  #bootCine .cine-sync svg{width:100%;height:100%;transform:rotate(-90deg);overflow:visible}
  #bootCine .cine-sync-track,#bootCine .cine-sync-arc{fill:none;stroke-width:1.6}
  #bootCine .cine-sync-track{stroke:rgba(255,140,125,.2)}
  #bootCine .cine-sync-arc{stroke:var(--cn-accent);stroke-linecap:round;stroke-dasharray:351.86;stroke-dashoffset:351.86;
    filter:drop-shadow(0 0 6px rgba(255,74,61,.65))}
  #bootCine .cine-panel.is-on .cine-sync-arc{animation:cineSyncFill 2100ms cubic-bezier(.2,.7,.3,1) forwards}
  @keyframes cineSyncFill{to{stroke-dashoffset:5.2}}
  #bootCine .cine-sync-val{position:absolute;inset:0;display:grid;place-content:center;text-align:center;font-family:var(--cn-mono)}
  #bootCine .cine-sync-val b{font-size:30px;font-weight:300;letter-spacing:.02em;color:var(--cn-text);font-variant-numeric:tabular-nums}
  #bootCine .cine-sync-val span{display:block;margin-top:2px;font-size:9px;letter-spacing:.3em;color:var(--cn-faint)}
  /* —— 金属字标 + 副标 —— */
  #bootCine .cine-logo{position:absolute;left:52px;bottom:19%;opacity:0;transform:translateY(10px);
    transition:opacity 900ms ease,transform 1100ms cubic-bezier(.2,.7,.3,1)}
  #bootCine.is-logo .cine-logo{opacity:1;transform:none}
  #bootCine .cine-logo b{display:block;font-size:clamp(32px,4.6vw,62px);font-weight:500;letter-spacing:.1em;line-height:1;
    background:linear-gradient(180deg,#ffffff 0%,#ffd9cf 32%,#b86256 64%,#ffffff 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent;
    filter:drop-shadow(0 2px 18px rgba(140,210,255,.35));position:relative}
  #bootCine .cine-logo b::after{content:"";position:absolute;inset:0;
    background:linear-gradient(100deg,transparent 36%,rgba(255,255,255,.9) 50%,transparent 64%);
    -webkit-background-clip:text;background-clip:text;color:transparent;opacity:0}
  #bootCine.is-logo .cine-logo b::after{animation:cineSheen 1200ms ease 420ms forwards}
  @keyframes cineSheen{0%{opacity:0;transform:translateX(-30%)}60%{opacity:.85}100%{opacity:0;transform:translateX(30%)}}
  #bootCine .cine-logo span{display:block;margin-top:14px;font-size:12px;letter-spacing:.34em;color:rgba(255,226,218,.7)}
  /* —— 跳过 / 声音 —— */
  #bootCine .cine-skip{position:absolute;right:52px;bottom:38px;z-index:5;background:none;border:none;
    font-family:var(--cn-mono);font-size:9.5px;letter-spacing:.24em;color:var(--cn-faint);cursor:pointer}
  #bootCine .cine-skip:hover{color:var(--cn-text)}
  /* ---------- 酒德麻衣主题 · PV 视频直播（cover 铺满裁掉黑边，底部留跳过提示） ---------- */
  #bootMd{position:absolute;inset:0;display:none;background:#000}
  #bootMd video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
  #bootMd .md-hint{position:absolute;bottom:4.5%;left:0;right:0;z-index:2;text-align:center;pointer-events:none;
    font:11px/1.6 Consolas,monospace;letter-spacing:.3em;color:rgba(232,192,122,.55);animation:clPulse 1.6s ease-in-out infinite}
  /* —— 起播门：明确的「开始」按钮，顺便解锁音频 —— */
  #bootCine .cine-gate{position:absolute;inset:0;z-index:60;display:grid;place-items:center;transition:opacity 340ms ease;
    background:radial-gradient(ellipse 60% 50% at 50% 42%,rgba(255,74,61,.12),transparent 70%),
      radial-gradient(ellipse 80% 60% at 50% 100%,rgba(8,5,6,.9),transparent 60%),#070405}
  #bootCine .cine-gate.is-out{opacity:0;pointer-events:none}
  #bootCine .cine-gate::after{content:"";position:absolute;inset:22px;border:1px solid rgba(255,140,125,.16);pointer-events:none}
  #bootCine .cine-gate-inner{position:relative;display:grid;justify-items:center;gap:12px;padding:36px 44px;text-align:center}
  #bootCine .cine-gate-kicker{font-family:var(--cn-mono);font-size:10px;letter-spacing:.42em;text-indent:.42em;
    color:rgba(255,90,74,.72);text-transform:uppercase}
  #bootCine .cine-gate-title{font-size:clamp(52px,9vw,116px);font-weight:800;line-height:.96;letter-spacing:.16em;
    text-indent:.16em;color:var(--cn-text);text-shadow:0 0 46px rgba(255,74,61,.28)}
  #bootCine .cine-gate-sub{font-family:var(--cn-mono);font-size:11px;letter-spacing:.22em;color:var(--cn-faint)}
  #bootCine .cine-gate-row{display:flex;gap:14px;margin-top:20px;flex-wrap:wrap;justify-content:center}
  #bootCine .cine-gate-start,#bootCine .cine-gate-skip{appearance:none;border:1px solid rgba(255,74,61,.55);
    background:rgba(255,74,61,.06);color:var(--cn-text);font-family:var(--cn-mono);font-size:12px;
    letter-spacing:.22em;text-transform:uppercase;padding:14px 30px;cursor:pointer;
    transition:background 160ms ease,color 160ms ease,border-color 160ms ease}
  #bootCine .cine-gate-start{border-color:var(--cn-accent)}
  #bootCine .cine-gate-start:hover{background:var(--cn-accent);color:#120607;outline:none;
    box-shadow:0 0 0 1px var(--cn-accent),0 0 36px rgba(255,74,61,.35)}
  #bootCine .cine-gate-skip{border-color:rgba(255,140,125,.22);background:transparent;color:var(--cn-faint)}
  #bootCine .cine-gate-skip:hover{color:var(--cn-text);border-color:rgba(255,140,125,.5)}
  #bootCine .bootHint{position:absolute;left:0;right:0;bottom:3vh;z-index:4;margin-top:0}
  /* 收尾整层淡出 + 窄屏适配 */
  #bootCine.is-out{opacity:0;transition:opacity 700ms ease}
  @media (max-width:880px){
    #bootCine .cine-hud{padding:24px 22px}
    #bootCine .cine-steps{left:22px;top:118px}
    #bootCine .cine-mark{left:22px;width:200px;height:170px}
    #bootCine .cine-num{font-size:110px}
    #bootCine .cine-topright,#bootCine .cine-midright{right:22px}
    #bootCine .cine-footer{left:22px;bottom:26px}
    #bootCine .cine-logo{left:22px;bottom:24%}
    #bootCine .cine-skip{right:22px;bottom:24px}
    #bootCine .cine-stage{left:22px;top:30%;width:min(320px,62vw)}
    #bootCine .cine-plug svg{width:82px;height:82px}
    #bootCine .cine-tank{height:108px;width:52px}
    #bootCine .cine-sync{width:118px;height:118px}
    #bootCine .cine-sync-val b{font-size:24px}
    #bootCine .cine-panel-t{font-size:18px}
  }
  /* ---------- 小狐电台 · Lattice 队列拼贴播放器（样式致敬 Folia） ---------- */
  #fox{position:fixed;inset:0;z-index:80;display:none;background:#0a0a08}
  #fox.open{display:flex}
  #foxBg{position:absolute;inset:-40px;background-size:cover;background-position:center;
    filter:blur(70px) brightness(.35);transition:background-image .6s;transform:scale(1.1)}
  #foxMain{position:relative;flex:1;display:flex;gap:34px;padding:56px 48px 110px;min-width:0;align-items:center}
  #foxLattice{flex:1.15;display:grid;grid-template-columns:repeat(4,1fr);gap:14px;align-content:center;max-height:100%;overflow-y:auto;padding:20px}
  .fpTile{position:relative;aspect-ratio:1;border-radius:10px;overflow:hidden;cursor:pointer;border:1px solid #26221a;
    transition:transform .45s cubic-bezier(.22,1.2,.36,1),box-shadow .45s,border-color .45s;background:#141109}
  .fpTile:nth-child(4n+3){transform:translateY(10px)}  /* 拼贴错落感 */
  .fpTile:nth-child(4n+2){transform:translateY(-6px)}
  .fpTile img{width:100%;height:100%;object-fit:cover;display:block}
  .fpTile span{position:absolute;left:6px;right:6px;bottom:5px;font-size:11px;color:#f5ead0;
    text-shadow:0 1px 4px rgba(0,0,0,.9);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fpTile:hover{border-color:var(--gold)}
  .fpTile.on{transform:translateY(0) scale(1.22)!important;border-color:var(--gold);z-index:5;
    box-shadow:0 0 34px rgba(230,180,60,.45),0 10px 30px rgba(0,0,0,.6)}
  .fpTile.on::after{content:"⏸";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-size:26px;color:var(--gold);background:rgba(10,8,2,.35);text-shadow:0 0 14px rgba(230,180,60,.9)}
  .fpTile.on.paused::after{content:"▶"}
  .fpTile.deco{opacity:.55;pointer-events:none;filter:saturate(.9)}
  .fpTile.deco span{display:none}
  #foxSide{flex:1;max-width:430px;max-height:100%;display:flex;flex-direction:column;gap:14px;min-height:0;
    background:linear-gradient(90deg,rgba(8,6,2,.66),rgba(8,6,2,.30));border-radius:16px;
    padding:22px 24px;backdrop-filter:blur(3px)}
  #foxTitle{font-size:26px;color:var(--gold);letter-spacing:.04em}
  #foxArtist{color:var(--dim);font-size:13px}
  #foxNote{color:#9a8a60;font-size:12px}
  #foxLyrics{position:relative;flex:1;min-height:0;overflow-y:auto;mask-image:linear-gradient(transparent,#000 12%,#000 88%,transparent);
    padding:30% 0;scroll-behavior:smooth}
  .fpLine{padding:7px 2px;color:#a89d78;font-size:15px;line-height:1.7;
    transition:color .4s,opacity .5s,transform .5s,filter .5s;cursor:pointer;opacity:.55;transform-origin:left center;
    text-shadow:0 1px 3px rgba(0,0,0,.85)}
  .fpLine.near{opacity:.88;color:#cabf98}
  .fpLine:hover{color:#d8cba0}
  .fpLine.on{color:#f2c94c;opacity:1;font-size:19px;transform:translateX(8px) scale(1.05);
    text-shadow:0 0 18px rgba(230,180,60,.45),0 2px 6px rgba(0,0,0,.9);animation:fpIn .55s cubic-bezier(.2,.9,.3,1.2)}
  .fpLine.far{opacity:.3;filter:blur(1px)}
  @keyframes fpIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
  #foxBar{position:absolute;left:48px;right:48px;bottom:34px;display:flex;align-items:center;gap:14px}
  .fpBtn{width:42px;height:42px;border-radius:50%;border:1px solid var(--gold);background:transparent;color:var(--gold);
    font-size:16px;cursor:pointer;transition:all .25s;flex:none}
  .fpBtn:hover{background:var(--gold);color:#0a0a08}
  .fpBtn.big{width:54px;height:54px;font-size:20px}
  #foxTime{color:var(--dim);font-size:11.5px;font-variant-numeric:tabular-nums}
  #foxProg{flex:1;height:4px;background:#2a2415;border-radius:2px;cursor:pointer;position:relative}
  #foxProgFill{height:100%;width:0;background:linear-gradient(90deg,#8a6a20,var(--gold));border-radius:2px;position:relative}
  #foxProgFill::after{content:"";position:absolute;right:-5px;top:-3px;width:10px;height:10px;border-radius:50%;background:var(--gold)}
  #foxClose{position:absolute;top:18px;right:22px;z-index:5;background:none;border:none;color:var(--dim);
    font-size:22px;cursor:pointer;transition:color .25s}
  #foxClose:hover{color:var(--gold)}
  /* ---------- 白龙酱 · 网页宠物（透明 WebM 素材来自 bailong-desktop-pet 发布包，状态联动为原创实现） ---------- */
  #pet{position:fixed;left:20px;bottom:16px;z-index:95;width:152px;user-select:none;cursor:grab;touch-action:none;
    filter:drop-shadow(0 8px 16px rgba(0,0,0,.5))}
  #pet:active{cursor:grabbing}
  #petVid{display:block;width:100%;pointer-events:none}
  .petNote{position:absolute;color:#f2c94c;font-size:13px;pointer-events:none;text-shadow:0 0 6px rgba(242,201,76,.85);
    animation:petNote 1.6s ease-out forwards}
  @keyframes petNote{0%{opacity:0;transform:translateY(0) scale(.6)}25%{opacity:1}100%{opacity:0;transform:translate(10px,-46px) scale(1.15)}}
  #petBubble{position:absolute;left:50%;bottom:98%;transform:translateX(-50%) translateY(6px);min-width:110px;max-width:190px;
    background:#fffdf4;color:#4a3d16;border:1px solid var(--gold);border-radius:10px;padding:7px 10px;font-size:12px;line-height:1.5;
    opacity:0;pointer-events:none;transition:opacity .3s,transform .3s;white-space:pre-wrap;z-index:2}
  #petBubble::after{content:"";position:absolute;left:50%;bottom:-6px;margin-left:-6px;border:6px solid transparent;
    border-top-color:var(--gold);border-bottom:none}
  #petBubble.show{opacity:1;transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>
<!-- 小狐电台 · Lattice 播放器（Folia 风格：队列拼贴 + 当前播放放大 + 歌词浮现） -->
<div id="fox">
  <div id="foxBg"></div>
  <button id="foxClose" title="收起电台">✕</button>
  <div id="foxMain">
    <div id="foxLattice"></div>
    <div id="foxSide">
      <div id="foxTitle">—</div>
      <div id="foxArtist">—</div>
      <div id="foxNote"></div>
      <div id="foxLyrics"></div>
    </div>
  </div>
  <div id="foxBar">
    <button class="fpBtn" id="foxPrev" title="上一首">⏮</button>
    <button class="fpBtn big" id="foxPlay" title="播放/暂停">▶</button>
    <button class="fpBtn" id="foxNext" title="下一首">⏭</button>
    <span id="foxTime">0:00 / 0:00</span>
    <div id="foxProg"><div id="foxProgFill"></div></div>
  </div>
</div>
<!-- 白龙酱 · 网页宠物：透明 WebM 动画（素材：bailong-desktop-pet v0.5.1 发布包），按 Agent 状态切换动作 -->
<div id="pet" title="白龙酱（可以拖动，点点看）">
  <div id="petBubble"></div>
  <video id="petVid" src="/static/pet/idle.webm" autoplay loop muted playsinline></video>
</div>
<header>
  <h1>小狐 · 情感陪伴 Agent</h1>
  <span class="tag gold" id="offTag" style="display:none">离线演示模式（未配置 API Key）</span>
  <span class="tag" id="stateTag">Skill 待命中</span>
  <span class="tag" id="humTag">幽默档 -</span>
  <select id="themeSel" title="选择启动动画主题">
    <option value="classic">启动主题：小狐经典</option>
    <option value="spirit">启动主题：狐仙立绘</option>
    <option value="codex">启动主题：粒子动画</option>
    <option value="eva">启动主题：EVA 驾驶员认证</option>
    <option value="cine">启动主题：EVA 电影感（Cine）</option>
    <option value="md">启动主题：酒德麻衣</option>
  </select>
  <button class="hbtn" id="replayBtn">&#9654; 重启动画</button>
  <span id="evaClock">--:--:--</span>
  <span class="uid">用户ID <input id="uid" value="demo"> <button class="hbtn" id="switchBtn">切换</button></span>
</header>
<main>
  <section class="chat">
    <img id="chatBg" src="/static/fox_spirit.jpg" alt="">
    <div id="evaWatermark">02</div>
    <div id="msgs"></div>
    <div class="inputbar">
      <input id="inp" placeholder="跟小狐说点什么…（试试：最近在追的番 / 吐槽导师 / 坏心情）" autofocus>
      <button id="send" onclick="send()">发送</button>
    </div>
  </section>
  <aside>
    <div class="card" id="memCard">
      <h2>记忆档案（长期画像 + 会话摘要）</h2>
      <div class="body" id="memBody">加载中…</div>
    </div>
    <div class="card" id="logCard">
      <h2>运行日志（最近 40 条 / JSONL 可核对）</h2>
      <div class="body"><table id="logTable"></table></div>
    </div>
  </aside>
</main>
<!-- 狐仙主题动态壁纸：把视频命名为 static/spirit-bg.mp4 即自动启用（静音循环）；无视频时回退静态插画 -->
<video id="spiritVideo" autoplay muted loop playsinline preload="auto" src="/static/spirit-bg.mp4"></video>
<video id="codexVideo" autoplay muted loop playsinline preload="auto" src="/static/codex-bg.mp4"></video>
<!-- 启动动画覆盖层：主题可选（经典/狐仙立绘），点击可跳过 -->
<div id="boot">
  <div id="bootClassic">
    <div class="cl-hud-top">
      <span class="cl-brand">◢ XIAOHU // 小狐</span><span class="cl-sep">│</span>
      <span class="cl-item">MODE <b>EMPATHY</b></span>
      <span class="cl-item">SESSION <b id="clSession">--------</b></span>
      <span class="cl-spacer"></span>
      <span class="cl-item">TIME <b id="clTime">--:--:--</b></span>
      <span class="cl-sep">│</span>
      <span class="cl-item cl-live">● REC</span>
    </div>
    <div class="cl-stage" id="clStageBox">
      <svg class="cl-fox" viewBox="0 0 100 90" aria-hidden="true">
        <polygon id="clFoxHead" points="10,8 38,28 62,28 90,8 84,52 50,86 16,52"
          fill="none" stroke="#e8c832" stroke-width="3" stroke-linejoin="round"/>
        <g class="cl-fox-f">
          <polygon points="50,60 41,48 59,48" fill="#e8c832"/>
          <circle cx="36" cy="42" r="4" fill="#e8c832"/>
          <circle cx="64" cy="42" r="4" fill="#e8c832"/>
        </g>
      </svg>
      <div class="cl-logo"><span>小<i>狐</i></span><span> ·EMPATHY OS</span></div>
      <div class="cl-boottext"><span id="clBootTxt"></span><span class="cl-cursor"></span></div>
    </div>
    <div class="cl-work">
      <section class="cl-w" id="clW-tele">
        <div class="cl-whead"><span class="cl-led"></span>PROFILE / MEMORY</div>
        <div class="cl-wbody" id="clTele"></div>
      </section>
      <section class="cl-w" id="clW-main">
        <div class="cl-whead"><span class="cl-led red"></span>XIAOHU CORE TERMINAL</div>
        <div class="cl-wbody" id="clMain"></div>
      </section>
      <section class="cl-w" id="clW-code">
        <div class="cl-whead"><span class="cl-led"></span>SKILL INJECTION</div>
        <div class="cl-wbody"><div id="clCode"></div></div>
      </section>
      <section class="cl-w" id="clW-node">
        <div class="cl-whead"><span class="cl-led red"></span>SKILL MATRIX</div>
        <div class="cl-wbody"><div id="clNodes">
          <div class="cl-node"><b>N1 玩梗陪聊</b><span class="st">STANDBY</span></div>
          <div class="cl-node"><b>N2 倾听共情</b><span class="st">STANDBY</span></div>
          <div class="cl-node"><b>N3 暖心开导</b><span class="st">STANDBY</span></div>
          <div class="cl-node"><b>N4 关系树洞</b><span class="st">STANDBY</span></div>
          <div class="cl-node"><b>N5 危机守护</b><span class="st">STANDBY</span></div>
        </div></div>
      </section>
    </div>
    <div class="cl-hud-bot">
      <span class="cl-item">STAGE <b id="clStage">IDLE</b></span>
      <span class="cl-item">LINE <b id="clLine">00 / 09</b></span>
      <span class="cl-item">BOOT</span>
      <div class="cl-prog"><div class="cl-fill" id="clFill"></div></div>
      <span class="cl-pct" id="clPct">0%</span>
      <span class="cl-spacer"></span>
      <span class="cl-item">NET <b id="clNet">OFFLINE</b></span>
      <span class="cl-item">FPS <b id="clFps">60</b></span>
    </div>
    <div class="cl-final" id="clFinal">小狐已上线</div>
    <div class="cl-scan"></div>
    <div class="bootHint">点击任意处跳过</div>
  </div>
  <div id="bootSpirit">
    <div class="art"><div class="artColor"></div><div class="artLine"></div></div>
    <div class="veil"></div>
    <div class="spBrand">&gt;_ 小狐<i>EMPATHY OS · PERSONAL WORKSPACE</i></div>
    <div class="spBox">
      <div class="spTitle">小狐</div>
      <div class="spSub">欢迎主人回家</div>
      <div class="spCaps">WELCOME HOME, MASTER</div>
    </div>
    <div class="spStatus"><span id="spStatusTx">正在唤醒躯体</span><div class="spProg"><div id="spBar"></div></div></div>
    <div class="spSkip">ESC 跳过</div>
    <div class="bootHint" style="position:absolute;left:0;right:0;bottom:3vh;z-index:2">点击任意处跳过</div>
  </div>
  <!-- Codex 完整版主题：移植自 yanami-sec/codex-startup-animation-windows（上游 panding999/codex-startup-animation），仅课堂作业演示 -->
  <div id="bootCodex">
    <div class="cdxScene">
      <!-- 后半段背景立绘：粒子描线层 + 线稿勾勒层 + 彩色上色层 三层叠加（codex-art 剑士壁纸） -->
      <div class="cdxArt"><div class="cdxArtColor"></div><canvas class="cdxCanvas"></canvas><div class="cdxArtLine"></div></div>
      <!-- waterflow 水流置换滤镜（壁纸 shaders/effects/waterflow.frag 的网页等效实现） -->
      <svg width="0" height="0" style="position:absolute">
        <filter id="cdxFlow" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.011" numOctaves="2" seed="7" result="n">
            <animate attributeName="baseFrequency" values="0.006 0.011;0.009 0.014;0.006 0.011" dur="9s" repeatCount="indefinite"/>
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/>
        </filter>
      </svg>
      <div class="cdxVeil"></div>
      <div class="cdxScan"></div>
      <div class="cdxGrid"></div>
      <div class="cdxCorners"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>
      <div class="cdxParticles"><i></i><i></i><i></i><i></i><i></i><i></i></div>
      <canvas class="cdxStars"></canvas>
      <div class="cdxSweep"></div>
      <!-- 前半段身份登场：脉冲环 + 雷达圈 + 圆形头像（codex-avatar.jpg 漫画少女）+ 标题/小字 -->
      <div class="cdxIntro">
        <div class="cdxPulse"><i></i><i></i><b></b></div>
        <div class="cdxIdentity">
          <div class="cdxRadar">
            <svg class="cdxDial" viewBox="0 0 400 400">
              <circle cx="200" cy="200" r="177"/>
              <circle class="cdxDashed" cx="200" cy="200" r="151"/>
              <!-- r=190 周长约 1194，dasharray 2/17.9 近似上游 60 根刻度线 -->
              <circle class="cdxTicksRing" cx="200" cy="200" r="190" stroke-dasharray="2 17.9"/>
              <path class="cdxCross" d="M200 9V61 M200 339V391 M9 200H61 M339 200H391"/>
            </svg>
            <div class="cdxAvatar"></div>
          </div>
          <svg class="cdxWave" viewBox="0 0 400 22"><path d="M0 11 Q15 5 30 11 T60 11 T90 11 T120 11 T150 11 T180 11 T210 11 T240 11 T270 11 T300 11 T330 11 T360 11 T400 11"/></svg>
          <div class="cdxName">小狐</div>
          <div class="cdxSub">XIAOHU · 狐仙系统</div>
        </div>
      </div>
      <!-- 左下角启动日志：由 JS 填充（沿用 /api/state 的 9 行） -->
      <div class="cdxLogs" id="cdxLogs"></div>
      <!-- 后半段 HUD：四角框 + SYNC RATIO 进度 + 字幕 + 时间码 -->
      <div class="cdxHud">
        <i class="cdxCorner tl"></i><i class="cdxCorner tr"></i><i class="cdxCorner bl"></i><i class="cdxCorner br"></i>
        <div class="cdxSync">
          <div class="cdxSyncLabel"><span>SYNC RATIO</span><span id="cdxRatio">00.00%</span></div>
          <div class="cdxTrack"><div class="cdxFill"></div></div>
          <span class="cdxPhase" id="cdxPhase">INITIALIZING</span>
        </div>
        <div class="cdxSubtitle">XIAOHU · 狐仙系统</div>
        <div class="cdxCoords"><span>小狐 · 情感陪伴 AGENT</span><span id="cdxTime">00:00:00</span></div>
      </div>
    </div>
    <!-- 结尾"画面合拢"的中缝亮线（场景收缩时出现、随后横向收束消失） -->
    <div class="cdxShutter"></div>
    <div class="bootHint cdxHint">点击任意处跳过</div>
  </div>
  <!-- EVA 驾驶员认证主题：仿造自 seaison/dsh-plugin-eva-theme（仅提取启动流程与素材，课堂演示） -->
  <div id="bootEva" data-pilot="asuka" data-phase="gif" data-sound="on">
    <!-- 阶段1：NERV GIF -->
    <div class="eva-boot-gifwrap" data-role="gif">
      <img class="eva-boot-gif" src="/static/eva/nerv-boot.gif" alt="NERV boot">
    </div>
    <!-- 阶段2：红色警报 -->
    <div class="eva-emergency" data-role="emergency">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" fill="none">
        <title>NERV EMERGENCY</title>
        <defs>
          <path id="eva-alert-hex" d="M-120 0-60-104H60L120 0 60 104H-60Z"/>
          <g id="eva-alert-tile">
            <use href="#eva-alert-hex" fill="#ef060c" stroke="#df0308" stroke-width="5"/>
            <path d="M0-66-22-30H22ZM-22 29H22L0 65Z" fill="#030101"/>
            <text x="0" y="9" fill="#030101" font-family="Arial,Helvetica,sans-serif" font-size="26" font-weight="800" text-anchor="middle" textLength="195" lengthAdjust="spacingAndGlyphs">EMERGENCY</text>
          </g>
          <pattern id="eva-alert-scan" width="4" height="4" patternUnits="userSpaceOnUse">
            <path d="M0 .5H4" stroke="#000" stroke-opacity=".24"/>
            <path d="M.5 0V4" stroke="#260000" stroke-opacity=".08"/>
          </pattern>
          <filter id="eva-alert-grain" x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency=".72" numOctaves="3" seed="19"/>
            <feColorMatrix type="saturate" values="0"/>
          </filter>
        </defs>
        <path fill="#000" d="M0 0H1000V1000H0Z"/>
        <g class="eva-alert-honeycomb" stroke-linejoin="miter">
          <g class="eva-alert-cell" style="--alert-lag:-.16s"><use href="#eva-alert-tile" transform="translate(363 173)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.74s" opacity=".78"><use href="#eva-alert-tile" transform="translate(565 67)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.42s"><use href="#eva-alert-tile" transform="translate(565 280)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.95s"><use href="#eva-alert-tile" transform="translate(767 174)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.32s" opacity=".28"><use href="#eva-alert-tile" transform="translate(767 -38)"/></g>
          <use href="#eva-alert-hex" transform="translate(969 67)" stroke="#df0308" stroke-width="7"/>
          <use href="#eva-alert-hex" transform="translate(-49 793)" stroke="#df0308" stroke-width="7"/>
          <g class="eva-alert-cell" style="--alert-lag:-.64s"><use href="#eva-alert-tile" transform="translate(132 899)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.11s" opacity=".65"><use href="#eva-alert-tile" transform="translate(334 793)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.83s"><use href="#eva-alert-tile" transform="translate(334 1005)"/></g>
          <g class="eva-alert-cell" style="--alert-lag:-.36s" opacity=".24"><use href="#eva-alert-tile" transform="translate(-70 1005)"/></g>
          <use href="#eva-alert-hex" transform="translate(536 899)" stroke="#df0308" stroke-width="7"/>
          <use href="#eva-alert-hex" transform="translate(1128 899)" stroke="#df0308" stroke-width="7"/>
        </g>
        <g class="eva-alert-wordmark" fill="#ed050b">
          <text x="-25" y="558" font-family="Baskerville,'Times New Roman',serif" font-size="218" textLength="578" lengthAdjust="spacingAndGlyphs">NERV</text>
          <path d="M570 416H939V484H549ZM546 496H1016V565H524Z"/>
          <g fill="#070000" font-family="'Times New Roman',Baskerville,serif">
            <text x="572" y="466" font-size="37" textLength="344" lengthAdjust="spacingAndGlyphs">God's In His Heaven</text>
            <text x="547" y="544" font-size="35" textLength="432" lengthAdjust="spacingAndGlyphs">All's Right With The World</text>
          </g>
          <text data-emergency-clock="" x="459" y="653" text-anchor="middle" font-family="'Times New Roman',Baskerville,serif" font-size="96" textLength="420" lengthAdjust="spacingAndGlyphs">09:58:57</text>
        </g>
        <path fill="url(#eva-alert-scan)" d="M0 0H1000V1000H0Z"/>
        <path fill="#fff" filter="url(#eva-alert-grain)" opacity=".045" d="M0 0H1000V1000H0Z"/>
      </svg>
    </div>
    <!-- 阶段3：黑底打字标题 -->
    <div class="eva-intro" data-role="intro">
      <div class="eva-intro-copy">
        <p class="eva-intro-kicker">NERV · DIRECT ENTRY SYSTEM</p>
        <div class="eva-intro-title"><span class="eva-intro-typed" id="evaTyped"></span></div>
        <span class="eva-intro-rule"></span>
      </div>
    </div>
    <!-- 阶段4：驾驶员选择 -->
    <div class="eva-console" data-role="select">
      <svg class="eva-contours" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true"></svg>
      <div class="eva-watermark">NERV</div>
      <header class="eva-boot-header">
        <div class="eva-boot-heading">
          <p class="eva-boot-kicker">nerv boot sequence <small>SELECT YOUR PILOT</small></p>
          <h2 class="eva-boot-title" id="evaTitle">选择你的驾驶员</h2>
          <p class="eva-boot-hint">拖拽驾驶员卡片到左侧插入栓，或点击卡片 / 按下 1 · 2 键选择</p>
        </div>
      </header>
      <div class="eva-boot-grid">
        <div class="eva-entry-bay">
          <span class="eva-entry-label">ENTRY PLUG <b>SOCKET</b></span>
          <div class="eva-entry-dial"></div>
          <div class="eva-entry-machine"><div class="eva-entry-assembly">
            <svg xmlns="http://www.w3.org/2000/svg" class="eva-entry-plug" viewBox="0 0 400 800" fill="none" aria-hidden="true">
              <defs>
                <linearGradient id="eva-plug-shell" x1="129" y1="0" x2="271" y2="0" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#9aa8a8"/><stop offset=".16" stop-color="#dce3df"/><stop offset=".43" stop-color="#fffff3"/><stop offset=".7" stop-color="#f5f4e7"/><stop offset="1" stop-color="#aab6b3"/>
                </linearGradient>
                <linearGradient id="eva-plug-cap" x1="129" y1="0" x2="271" y2="0" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#82542d"/><stop offset=".25" stop-color="#d19b59"/><stop offset=".57" stop-color="#f5cd87"/><stop offset="1" stop-color="#a2703e"/>
                </linearGradient>
                <linearGradient id="eva-plug-gold" x1="129" y1="0" x2="271" y2="0" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#85621f"/><stop offset=".4" stop-color="#e4bd4f"/><stop offset=".7" stop-color="#f8d96e"/><stop offset="1" stop-color="#a78630"/>
                </linearGradient>
                <clipPath id="eva-plug-outline"><rect x="129" y="54" width="142" height="692" rx="71"/></clipPath>
              </defs>
              <g stroke="var(--boot-line)" stroke-width="1">
                <path d="M105 115v578m190-578v578M96 115h18m-18 578h18m172-578h18m-18 578h18"/>
                <path d="M105 202h22m146 0h22M105 588h22m146 0h22" stroke-dasharray="3 4"/>
              </g>
              <g clip-path="url(#eva-plug-outline)" stroke="#677778" stroke-width="1.4" stroke-linejoin="round">
                <rect x="129" y="54" width="142" height="692" rx="71" fill="url(#eva-plug-shell)"/>
                <path d="M129 54h142v107c-40 9-102 9-142 0z" fill="url(#eva-plug-cap)"/>
                <path d="M129 158q71 13 142 0v14q-71 13-142 0z" fill="#333e42"/>
                <path class="eva-plug-band" d="M129 172q71 13 142 0v29q-71 13-142 0z" fill="var(--boot-accent)" stroke="#36444a"/>
                <path d="M129 202q71 13 142 0M129 257q71 12 142 0M129 571q71 12 142 0M143 212v349m112-349v349" opacity=".6"/>
                <g class="eva-plug-roll eva-plug-roll-front">
                  <path d="M148 217h20v27h-20zM232 217h20v27h-20zM154 226h8m76 0h8" stroke="#879492"/>
                  <path d="M167 76q33-13 66 0l4 33q-37 9-74 0z" fill="#f2c47d"/>
                  <path d="M174 84h52m-48 9h44M151 126v19m98-19v19" stroke="#896a44"/>
                  <g fill="#535d57" stroke="#b98c53">
                    <circle cx="154" cy="111" r="3"/><circle cx="246" cy="111" r="3"/>
                    <circle cx="155" cy="151" r="2.5"/><circle cx="245" cy="151" r="2.5"/>
                  </g>
                  <path d="M180 132q20-10 40 0l-4 9h-32z" fill="#333e42" stroke="#a37b46"/>
                  <g transform="rotate(90 200 338)" fill="#344247" stroke="none" text-anchor="middle">
                    <text x="200" y="336" class="eva-plug-stencil">EVA-<tspan data-boot-unit>02</tspan></text>
                    <text x="200" y="353" class="eva-plug-micro">NERV · DIRECT ENTRY SYSTEM</text>
                  </g>
                  <path d="M157 281h-8v110h8m86-110h8v110h-8" stroke="#93a09c"/>
                  <path d="M166 406h68v9h-68z" fill="#e6e8dc"/>
                  <path d="M176 410h48" stroke="var(--boot-accent)"/>
                  <path d="M162 433l-10 13v83l10 14h76l10-14v-83l-10-13z" fill="#b3bfba" stroke="#536467" stroke-width="2"/>
                  <path d="M168 443h64l7 9v71l-7 10h-64l-7-10v-71z" fill="#182b30"/>
                  <path d="M166 450h12m44 0h12m-68 73h12m44 0h12" stroke="var(--boot-accent)" stroke-width="2"/>
                  <path d="M173 462h54m-54 13h54m-54 13h54m-54 13h54m-54 13h54" stroke="#709c94" opacity=".17"/>
                  <g fill="#657571" stroke="#dce2d5"><circle cx="160" cy="440" r="2"/><circle cx="240" cy="440" r="2"/><circle cx="160" cy="535" r="2"/><circle cx="240" cy="535" r="2"/></g>
                  <path d="M185 552h30m-25 6h20" stroke="#73817b"/>
                </g>
                <g class="eva-plug-roll eva-plug-roll-back" stroke="#84918b">
                  <path d="M177 228h46v330h-46zM188 236v310m24-310v310" fill="#e8e9dd"/>
                  <path d="M181 276h38m-38 9h38m-38 9h38m-38 155h38m-38 9h38m-38 9h38"/>
                  <g transform="rotate(90 200 357)" fill="#465450" stroke="none" text-anchor="middle">
                    <text x="200" y="358" class="eva-plug-micro">NERV / SERVICE ACCESS · L.C.L.</text>
                  </g>
                  <path d="M181 506h38v28h-38z" fill="#d5ad4c"/><path d="m188 528 12-17 12 17z" fill="#344247"/>
                  <path d="M188 85h24v55h-24z" fill="#bd894e"/><path d="M193 96h14m-14 8h14m-14 8h14m-14 8h14"/>
                </g>
                <g class="eva-plug-collar">
                  <path d="M129 583q71 12 142 0v55q-71 12-142 0z" fill="url(#eva-plug-gold)" stroke="#494f41" stroke-width="2"/>
                  <path d="M129 582q71 12 142 0m-142 59q71 12 142 0" stroke="#29383d" stroke-width="6"/>
                  <path d="M129 646q71 12 142 0v53q-71 12-142 0z" fill="#4a595d" stroke="#304247"/>
                  <path class="eva-plug-roll eva-plug-roll-front" d="M145 654l15 37h-17zM178 657l14 39h-22zM211 658l12 38h-22zM245 654l10 36h-22z" fill="#ee9b41" stroke="#263c42" stroke-width="2"/>
                  <path d="M129 702q71 12 142 0" stroke="#7a8780"/>
                </g>
                <path d="M168 718q32 9 64 0m-53 10q21 5 42 0" stroke="#97a19a"/>
                <path d="M145 90v61m0 63v347m0 148v9" stroke="#fffbe5" stroke-width="3" opacity=".5"/>
              </g>
              <rect x="129" y="54" width="142" height="692" rx="71" stroke="#889694" stroke-width="1.8"/>
              <g class="eva-plug-callouts" fill="none" stroke="var(--boot-line)" stroke-width="1">
                <path d="M269 228h35v-15h28M130 486H83v18H65M270 610h36v18h24"/>
                <g fill="var(--boot-dim)" stroke="none" class="eva-plug-micro"><text x="299" y="205">A10</text><text x="41" y="518">L.C.L.</text><text x="290" y="642">LOCK</text></g>
                <circle cx="269" cy="228" r="2" fill="var(--boot-accent)"/><circle cx="130" cy="486" r="2" fill="var(--boot-accent)"/>
              </g>
            </svg>
          </div></div>
          <p class="eva-entry-target">INSERT PILOT // 插入栓待机</p>
        </div>
        <div class="eva-pilot-list">
          <button class="eva-pilot-card" data-pilot="asuka" data-unit="02">
            <img class="eva-pilot-face" src="/static/eva/asuka-portrait-lineart.png" alt="明日香" draggable="false">
            <span class="eva-pilot-info">
              <span class="eva-pilot-number">02</span><b>明日香</b><small>ASUKA LANGLEY</small><em>战斗服红 · 炭黑 · 橙金</em>
            </span>
          </button>
          <button class="eva-pilot-card" data-pilot="rei" data-unit="00">
            <img class="eva-pilot-face" src="/static/eva/rei-portrait-lineart.png" alt="绫波丽" draggable="false">
            <span class="eva-pilot-info">
              <span class="eva-pilot-number">00</span><b>绫波丽</b><small>REI AYANAMI</small><em>瓷白 · 冰蓝 · 红标</em>
            </span>
          </button>
        </div>
      </div>
      <footer class="eva-boot-footer">
        <p class="eva-boot-status">驾驶员认证待机 · MAGI 系统已通过</p>
      </footer>
    </div>
    <!-- 阶段5：装载同步（对齐视频：大字名字 + 右侧同步环 + 红色波形条） -->
    <div class="eva-boot-loading" data-role="loading">
      <div class="eva-boot-code" id="evaCode">L.C.L. 注入 · 神经接続開始</div>
      <div class="eva-sync-head">
        <h2 id="evaLoadName">明日香</h2>
        <div class="eva-sync-orbit">
          <svg viewBox="0 0 180 180">
            <circle class="eva-sync-ring-track" cx="90" cy="90" r="70"/>
            <circle class="eva-sync-ring-meter" id="evaRing" cx="90" cy="90" r="70"/>
          </svg>
          <div class="eva-sync-readout"><span class="eva-sync-value" id="evaRatio">0.0%</span><small>SYNC RATIO</small></div>
        </div>
      </div>
      <div class="eva-wave"><i id="evaWave"></i></div>
      <div>
        <div class="eva-boot-meter"><i id="evaMeter"></i></div>
        <div class="eva-boot-progress-label"><span id="evaPhaseTxt">接続開始</span><time id="evaTime">00:00</time></div>
        <p class="eva-sync-caption">同步率随语音播放推进 · 完成后开启舱门</p>
      </div>
    </div>
    <!-- 阶段6：双侧机械舱门 -->
    <div data-role="gates">
      <div class="eva-boot-gate left"><span>02</span></div>
      <div class="eva-boot-gate right"><span>00</span></div>
      <div class="eva-boot-clearance"><b id="evaClearName">明日香 · 同步完成</b><small>CLEARANCE GRANTED</small></div>
    </div>
    <button class="hbtn eva-sound" id="evaMuteBtn">声音：开</button>
    <div class="bootHint">点击空白处跳过 · EVA 驾驶员认证（声音默认开启，点按钮切换）</div>
  </div>
  <!-- EVA 电影感主题：仿造 dsh-eva-boot 1.1.5 的 cine 模式（起播门→HUD→02字标→三段机构→线稿→海报→字标） -->
  <div id="bootCine">
    <div class="cine-bg"><img src="/static/eva/cine-poster.jpg" alt=""></div>
    <div class="cine-lineart"><img src="/static/eva/cine-lineart.jpg" alt=""></div>
    <div class="cine-mesh"></div>
    <canvas class="cine-dust"></canvas>
    <div class="cine-vignette"></div>
    <div class="cine-hud">
      <div class="cine-brand">
        <svg class="cine-crown" viewBox="0 0 26 18" fill="none" stroke="currentColor" stroke-width="1.1">
          <path d="M13 2 L24 9 L13 16 L2 9 Z"/><path d="M13 6 L19 9 L13 12 L7 9 Z" opacity="0.6"/>
        </svg>
        <div class="cine-brand-main">
          <div class="cine-brand-name">NERV</div>
          <div class="cine-brand-sub">SPECIAL AGENCY<br>NERV</div>
        </div>
      </div>
      <div class="cine-rule" style="margin-left:38px"></div>
      <div class="cine-steps">
        <div class="cine-step"><i></i>ENTRY PLUG</div>
        <div class="cine-step"><i></i>LCL INJECT</div>
        <div class="cine-step"><i></i>NEURAL LINK</div>
        <div class="cine-step"><i></i>A10 CLIP</div>
        <div class="cine-step"><i></i>LAUNCH</div>
      </div>
      <div class="cine-topright"><b>UNIT-02 / NERV</b><span></span></div>
      <div class="cine-midright">SYNC RATIO 98.4%<br>LCL PRESSURE NOMINAL<b></b></div>
      <div class="cine-footer">小狐 · 情感陪伴 AGENT<br>YOUR WILL IS THE TRIGGER</div>
    </div>
    <div class="cine-mark"><div class="cine-num">02</div></div>
    <div class="cine-stage">
      <div class="cine-panel" id="cinePPlug">
        <div class="cine-panel-k">02 · ENTRY PLUG</div>
        <div class="cine-panel-t">插入栓投放</div>
        <div class="cine-plug">
          <svg viewBox="0 0 120 120" aria-hidden="true">
            <circle class="r1" cx="60" cy="60" r="54"/><circle class="r2" cx="60" cy="60" r="44"/>
            <circle class="r3" cx="60" cy="60" r="30"/>
            <g class="plug-g"><rect x="48" y="10" width="24" height="42" rx="5"/></g>
          </svg>
          <div class="cine-plug-depth">DEPTH<b id="cineDepth">0.0 m</b></div>
        </div>
      </div>
      <div class="cine-panel" id="cinePLcl">
        <div class="cine-panel-k">03 · LCL INJECTION</div>
        <div class="cine-panel-t">LCL 注入</div>
        <div class="cine-lcl">
          <div class="cine-tank"><i></i><em>LCL</em></div>
          <dl class="cine-params">
            <div><dt>压力</dt><dd id="cinePressure">0.00</dd></div>
            <div><dt>温度</dt><dd id="cineTemp">0.0</dd></div>
            <div><dt>浓度</dt><dd id="cineDensity">0</dd></div>
            <div><dt>神经递质</dt><dd id="cineNeuro">0</dd></div>
          </dl>
        </div>
      </div>
      <div class="cine-panel" id="cinePSync">
        <div class="cine-panel-k">04 · NEURAL HANDSHAKE</div>
        <div class="cine-panel-t">神经接驳</div>
        <div class="cine-sync">
          <svg viewBox="0 0 140 140" aria-hidden="true">
            <circle class="cine-sync-track" cx="70" cy="70" r="56"/>
            <circle class="cine-sync-arc" id="cineArc" cx="70" cy="70" r="56"/>
          </svg>
          <div class="cine-sync-val"><b id="cineSyncVal">0.0</b><span>SYNC %</span></div>
        </div>
      </div>
    </div>
    <div class="cine-streak"></div>
    <div class="cine-log" id="cineLog"></div>
    <div class="cine-logo"><b>NERV</b><span>二号机 · 驾驶员 明日香</span></div>
    <button class="cine-skip" id="cineSkipBtn">SKIP · ESC</button>
    <div class="cine-gate" id="cineGate">
      <div class="cine-gate-inner">
        <div class="cine-gate-kicker">SPECIAL AGENCY NERV</div>
        <div class="cine-gate-title">NERV</div>
        <div class="cine-gate-sub">二号机 · 驾驶员 明日香</div>
        <div class="cine-gate-row">
          <button class="cine-gate-start" id="cineStartBtn">开始 / START</button>
          <button class="cine-gate-skip" id="cineGateSkip">跳过 / SKIP</button>
        </div>
      </div>
    </div>
    <div class="bootHint">点击空白处跳过 · EVA 电影感</div>
  </div>
  <!-- 启动动画 · 酒德麻衣：PV 视频直播（22.8s，播完自动进聊天，点击/ESC 跳过） -->
  <div id="bootMd">
    <video id="mdVideo" src="/static/md-boot.mp4" preload="auto" playsinline></video>
    <div class="md-hint">点击任意处跳过 · ESC</div>
  </div>
</div>
<!-- EVA 双生皮肤欢迎横幅（选完驾驶员进入聊天后短暂浮现） -->
<div id="evaBanner"><b id="evaBannerTitle"></b><small id="evaBannerSub"></small></div>
<script>
let UID = localStorage.getItem("uid") || "demo";
document.getElementById("uid").value = UID;

function esc(s){const d=document.createElement("div");d.textContent=s==null?"":String(s);return d.innerHTML;}

async function send(){
  const inp = document.getElementById("inp");
  const text = inp.value.trim();
  if(!text) return;
  inp.value = "";
  sendText(text);
}

// 歌单卡片点击也会走这里（等价于用户亲口报歌名，完整经过 Skill 路由，答辩可演示）
async function sendText(text){
  addMsg("me", text, null);
  try{
    const r = await fetch("/api/chat", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({user_id: UID, text})});
    const d = await r.json();
    if(d.error){ addMsg("ai", "出错了："+d.error, null); return; }
    addMsg("ai", d.reply, d);
  }catch(e){ addMsg("ai", "网络错误："+e, null); }
  refresh();
}

function addMsg(who, text, d){
  const box = document.getElementById("msgs");
  const row = document.createElement("div");
  row.className = "row " + (who==="me"?"me":"ai");
  let inner = '<div class="bubble">' + esc(text) + '</div>';
  if(d){
    if(d.music){
      if(d.music.type === "playlist"){
        // 私藏电台：歌单卡片，每行可点击点播
        inner += '<div class="plCard"><div class="plHead">🎵 小狐私藏歌单 · ' + d.music.items.length + ' 首'
               + (d.music.online ? ' · 播放器就绪' : ' · Folia 未启动，将用系统播放器') + '</div>';
        d.music.items.forEach(function(s){
          const t = esc(s.title).replace(/'/g, "").replace(/"/g, "");
          inner += '<div class="plRow" data-q="放一首' + t + '">'
                 + '<b>《' + esc(s.title) + '》</b><i>' + esc(s.artist) + '</i>'
                 + (s.tags && s.tags.length ? '<span class="plTags">' + esc(s.tags.join('/')) + '</span>' : '')
                 + '</div>';
        });
        inner += '</div>';
      }else if(d.music.type === "local"){
        // 私藏电台：正在播放卡片（转动的唱片），点击可打开 Lattice 播放器
        const vt = d.music.via === 'folia' ? '正在 Folia 中播放' : d.music.via === 'web' ? '小狐电台播放中 · 点击卡片打开'
                 : d.music.via === 'system' ? '正在系统播放器中播放' : '播放失败';
        inner += '<div class="nowCard" data-play="' + esc(d.music.title) + '" style="cursor:pointer"><div class="disc">🎵</div><span class="nowBody"><b>《'
               + esc(d.music.title) + '》· ' + esc(d.music.artist) + '</b><i>' + vt
               + (d.music.note ? ' · 小狐私评：' + esc(d.music.note) : '') + '</i></span></div>';
      }else{
        // B 站点歌兜底卡片
        inner += '<a class="musicCard" href="' + esc(d.music.url) + '" target="_blank" rel="noopener">'
               + '<img src="' + esc(d.music.cover) + '" alt="" referrerpolicy="no-referrer">'
               + '<span class="mcBody"><b>' + esc(d.music.title) + '</b><i>'
               + esc(d.music.author) + ' · 播放 ' + (d.music.play||0).toLocaleString() + '</i></span></a>';
      }
    }
    let tags = '<span class="tag gold">' + esc(d.skill_title) + '</span>'
             + '<span class="tag">幽默档 ' + d.humor_level + '</span>';
    if(d.humor_suppressed) tags += '<span class="tag warn">玩笑已抑制</span>';
    if(d.offline) tags += '<span class="tag">离线文案</span>';
    tags += '<span class="tag">' + d.latency_ms + 'ms</span>';
    if(d.memory_write && Object.keys(d.memory_write).length)
      tags += '<span class="tag">写入:' + esc(Object.keys(d.memory_write).join("/")) + '</span>';
    tags += '<span class="tag" title="' + esc(d.reason) + '">' + esc(d.reason) + '</span>';
    inner += '<div class="meta">' + tags + '</div>';
  }
  row.innerHTML = inner;
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
  if(d && d.music && d.music.type === "local" && d.music.via === "web" && window.Fox)
    Fox.playByTitle(d.music.title);  // 网页播放：自动弹出 Lattice 电台
}

// 歌单卡片点击（事件委托）：等价于用户亲口报歌名，完整走 Skill 路由
document.getElementById("msgs").addEventListener("click", function(e){
  const r = e.target.closest(".plRow");
  if(r){ sendText(r.getAttribute("data-q")); return; }
  const nc = e.target.closest(".nowCard");
  if(nc && window.Fox) Fox.open();  // 正在播放卡片：打开电台面板
});

async function refresh(){
  try{
    const s = await (await fetch("/api/state?user_id=" + encodeURIComponent(UID))).json();
    document.getElementById("offTag").style.display = s.offline ? "" : "none";
    document.getElementById("stateTag").textContent = "Skill: " + s.last_skill
      + (s.crisis_mode ? " | 守护态" : "") + (s.empathy_streak ? " | 共情x" + s.empathy_streak : "");
    document.getElementById("humTag").textContent = "幽默档 " + s.profile.humor_level;
    // 记忆面板
    const p = s.profile;
    let h = "";
    h += '<div class="kv"><b>幽默档位</b> ' + "●".repeat(p.humor_level) + "○".repeat(3-p.humor_level) + " (" + p.humor_level + "/3)</div>";
    if(p.nickname) h += '<div class="kv"><b>昵称</b> ' + esc(p.nickname) + '</div>';
    if(p.self_label) h += '<div class="kv"><b>自认</b> ' + esc(p.self_label) + '</div>';
    if(p.watching.length) h += '<div class="kv"><b>在追</b> ' + esc(p.watching.join("、")) + '</div>';
    if(p.liked_jokes.length) h += '<div class="kv"><b>吃过的梗</b> ' + esc(p.liked_jokes.join("、")) + '</div>';
    if(p.disliked_jokes.length) h += '<div class="kv"><b>玩砸的梗</b> ' + esc(p.disliked_jokes.join("、")) + '</div>';
    if(p.important_people.length) h += '<div class="kv"><b>重要他人</b> ' + esc(p.important_people.join("、")) + '</div>';
    if(p.triggers.length) h += '<div class="kv"><b>触发点</b> ' + esc(p.triggers.join("、")) + '</div>';
    if(p.mood_timeline.length){
      h += '<div class="sec">情绪时间线（近6条）</div>';
      p.mood_timeline.slice(-6).reverse().forEach(m=>{
        h += '<div><span class="moodbar" style="width:' + (m.score*28) + 'px"></span>'
           + esc(m.date) + ' 强度' + m.score + ' ' + esc(m.note) + '</div>';
      });
    }
    h += '<div class="sec">会话摘要（第2层记忆）</div><div class="kv">' + (s.summary ? esc(s.summary) : '（暂无，聊满自动压缩）') + '</div>';
    h += '<div class="sec">短期窗口 ' + s.window_len + ' 条 / 待压缩 ' + s.overflow_len + ' 条</div>';
    document.getElementById("memBody").innerHTML = h;
    // 日志面板
    const logs = await (await fetch("/api/logs?user_id=" + encodeURIComponent(UID))).json();
    let rows = "";
    logs.forEach(l=>{
      if(l.type!=="turn") return;
      rows += '<tr><td class="t">' + esc(l.ts.slice(11)) + '</td><td><span class="sk">'
           + esc(l.skill) + '</span> ' + esc((l.text||"").slice(0,26)) + ' <span style="color:var(--dim)">→</span> '
           + esc((l.reply||"").slice(0,26)) + '</td></tr>';
    });
    document.getElementById("logTable").innerHTML = rows || '<tr><td style="color:var(--dim)">暂无日志</td></tr>';
  }catch(e){}
}

function switchUser(){
  UID = document.getElementById("uid").value.trim() || "demo";
  localStorage.setItem("uid", UID);
  document.getElementById("msgs").innerHTML = "";
  refresh();
  replayBoot();  // 切换用户时重播启动序列，展示新档案的加载过程
}

// ---------------- 启动动画：主题可选（经典 / 狐仙立绘 / Codex 完整版），内容取自真实 /api/state ----------------
let bootTimers = [];
function bootTheme(){
  const t = localStorage.getItem("bootTheme") || "classic";
  return t === "dragon" ? "classic" : t;   // 龙娘主题已移除，老缓存值回退经典主题
}

function runBoot(){
  const theme = bootTheme();
  const boot = document.getElementById("boot");
  const classic = document.getElementById("bootClassic");
  const spirit = document.getElementById("bootSpirit");
  const codex = document.getElementById("bootCodex");
  const eva = document.getElementById("bootEva");
  const cine = document.getElementById("bootCine");
  const md = document.getElementById("bootMd");
  bootTimers.forEach(clearTimeout); bootTimers = [];
  boot.style.display = "flex";
  boot.classList.remove("done");
  spirit.classList.remove("artIn", "drawIn", "titleIn", "clrIn");
  codex.className = "";   // Codex 主题：清空全部阶段类，防重播/跳过后残留状态
  const isClassic = theme === "classic";
  const isSpirit  = theme === "spirit";
  const isCodex   = theme === "codex";
  const isEva     = theme === "eva";
  const isCine    = theme === "cine";
  const isMd      = theme === "md";
  // 狐仙 / Codex 两种主题下，聊天区右下角都保留低透明度立绘（同视频：立绘延续到主界面）
  document.body.classList.toggle("spirit", isSpirit || isCodex);
  document.body.classList.toggle("codex", isCodex);   // 粒子动画主题：聊天背景用壁纸剑士画面（body.codex::before）
  document.body.classList.toggle("md", isMd);         // 酒德麻衣主题：聊天背景用 PV 最后一幕 + 玫红强调色（body.md）
  classic.style.display = isClassic ? "block" : "none";
  spirit.style.display  = isSpirit  ? "block" : "none";
  codex.style.display   = isCodex   ? "block" : "none";
  eva.style.display     = isEva     ? "block" : "none";
  cine.style.display    = isCine    ? "block" : "none";
  md.style.display      = isMd      ? "block" : "none";
  if(isEva){ runBootEva(); return; }         // EVA 驾驶员认证主题：不依赖 /api/state
  if(isCine){ runBootCine(); return; }       // EVA 电影感主题：起播门等待点击，也不依赖 /api/state
  if(isMd){ clearEvaSkin(); runBootMd(); return; }   // 酒德麻衣主题：PV 视频直播，不依赖 /api/state
  clearEvaSkin();                            // 其余主题：清除 EVA 双生皮肤与时钟，恢复狐仙背景

  fetch("/api/state?user_id=" + encodeURIComponent(UID)).then(r=>r.json()).then(s=>{
    const p = s.profile;
    const lines = [
      "内核初始化 XIAOHU-OS v1.0",
      "加载长期记忆档案 " + UID + ".json" + (p.watching.length ? "（在追 " + p.watching.length + " 项）" : "（新档案）"),
      "挂载 Skill 注册表 ×5：玩梗陪聊 / 倾听共情 / 暖心开导 / 关系树洞 / 危机守护",
      "幽默模块校准：当前档位 " + p.humor_level + "/3",
      "规则引擎载入：情绪词表 + 6 组触发正则",
      "三层记忆总线连接：短期窗口 / 会话摘要 / 长期档案",
      "危机守护模块上线（最高优先级·硬规则）",
      "人格核注入：「小狐 · 毒舌但暖」",
      "启动完成 —— 小狐已上线"
    ];
    // Codex 完整版主题：交给移植过来的独立编排函数（日志同样取自上面 9 行）
    if(isCodex){ runBootCodex(lines); return; }
    // 经典主题：550C 风全屏 HUD（数据同样取自真实 state 与上面 9 行日志）
    if(isClassic){ runBootClassic(s, lines); return; }
    // 狐仙立绘主题：参考视频标准编排（青色霓虹线稿 → 颜色淹没 → 标题渐亮）
    if(isSpirit){ runBootSpirit(s); return; }
  }).catch(()=>{ finishBoot(); });
}

// ================= 狐仙立绘主题 · 参考视频标准编排 =================
// 时间线（对照参考视频节奏，总约 4.6s，期间点击任意处 / ESC 可跳过）：
//   0     黑场星尘，状态行「正在唤醒躯体」，标题呈暗水印，青色霓虹线稿自上而下勾勒（1.7s）
//   1900  「正在点亮你的工作空间」：彩色立绘整幅交叉淡入（1s），线稿辉光随之融解
//   2500  水印标题渐亮为白，「欢迎主人回家」+ WELCOME HOME, MASTER 依次浮现
//   3300  「一切就绪，即刻出发」，进度线 100%
//   4600  finishBoot() 淡出进聊天（聊天区右侧保留低透明度立绘）
function runBootSpirit(s){
  const spirit = document.getElementById("bootSpirit");
  const statusTx = document.getElementById("spStatusTx");
  const bar = document.getElementById("spBar");
  // 重置上一轮残留（重播/切主题场景）
  spirit.classList.remove("artIn", "drawIn", "titleIn", "clrIn");
  statusTx.textContent = "正在唤醒躯体";
  bar.style.transition = "none"; bar.style.width = "0%";
  // 重播时线稿/彩层/标题可能带着上一轮的过渡中间态：
  // 先瞬时快照到初始外观（否则移除 clrIn 后 artLine 会以 1.4s+0.45s 延迟慢慢浮现，勾勒前半段几乎看不见）
  const snap = (el, props) => {
    el.style.transition = "none";
    for(const k in props) el.style[k] = props[k];
  };
  snap(spirit.querySelector(".artLine"),  {opacity: "1", clipPath: "inset(0 0 100% 0)"});
  snap(spirit.querySelector(".artColor"), {opacity: "0"});
  snap(spirit.querySelector(".spTitle"),  {color: "", opacity: "", transform: ""});
  void spirit.offsetWidth;                     // 强制回流，让快照生效后再开始新一轮过渡
  spirit.querySelectorAll(".artLine,.artColor,.spTitle").forEach(el=>{ el.style.transition = ""; el.style.opacity = ""; el.style.clipPath = ""; });
  spirit.classList.add("artIn", "drawIn");
  bar.style.transition = "width 1.9s linear";
  bar.style.width = "34%";
  bootTimers.push(setTimeout(()=>{
    statusTx.textContent = "正在点亮你的工作空间";
    bar.style.transition = "width 1.4s ease";
    bar.style.width = "86%";
    spirit.classList.add("clrIn");             // 颜色整幅淡入，线稿辉光融解
  }, 1900));
  bootTimers.push(setTimeout(()=>spirit.classList.add("titleIn"), 2500));
  bootTimers.push(setTimeout(()=>{
    statusTx.textContent = "一切就绪，即刻出发";
    bar.style.transition = "width .5s ease";
    bar.style.width = "100%";
  }, 3300));
  bootTimers.push(setTimeout(finishBoot, 4600));
}

// ================= 经典主题 · 550C 风全屏 HUD（移植编排） =================
// 编排思路来源：Voidpocket/html_550c（550C Boot Animation，仅提取其"HUD 顶/底栏 + 打字机
// 主控台 + 阶段推进 + 节点矩阵"思路，未复制上游素材）。
// 我们版本的时间线（总约 7.5s，期间点击任意处可跳过；数据仍取自真实 /api/state）：
//   0     狐狸 logo 描线绘制轮廓（1.6s，stroke-dashoffset）→ 1.95s 五官弹出
//   2400  「小狐 ·EMPATHY OS」字标逐字揭示 + "XIAOHU SYSTEM BOOT" 打字
//   3600  字标舞台收起，四面板工作区成为主角
//   3700  主控台逐字打印 9 行启动日志，底栏 STAGE 依次 BOOT/SKILL/MEM/GUARD/PERSONA/READY；
//         同步：PROFILE 面板填真实档案、SKILL INJECTION 伪代码流滚动、第 3 行起技能矩阵逐格点亮
//   ~6200 日志完毕：NET 上线、进度 100%，定格大字「小狐已上线」
//   ~7500 finishBoot() 交还主界面
function runBootClassic(s, lines){
  const boot = document.getElementById("boot");
  const $ = sel => document.querySelector(sel);
  const sleep = ms => new Promise(r => bootTimers.push(setTimeout(r, ms)));
  const dead = () => boot.classList.contains("done");   // 跳过后立即中止后续编排
  // —— 重置上一轮残留（重播/切回主题场景） ——
  const foxHead = document.getElementById("clFoxHead");
  foxHead.style.transition = "none";
  const foxLen = foxHead.getTotalLength();
  foxHead.style.strokeDasharray = foxLen;
  foxHead.style.strokeDashoffset = foxLen;
  document.querySelector(".cl-fox-f").classList.remove("on");
  $("#clStageBox").classList.remove("off");
  $("#clFinal").classList.remove("show");
  $("#clStage").textContent = "IDLE";
  $("#clLine").textContent = "00 / 09";
  $("#clNet").textContent = "OFFLINE"; $("#clNet").classList.remove("gold");
  $("#clFill").style.width = "0%"; $("#clPct").textContent = "0%";
  $("#clBootTxt").textContent = ""; $("#clTele").innerHTML = ""; $("#clMain").innerHTML = ""; $("#clCode").innerHTML = "";
  document.querySelectorAll("#clStageBox .cl-logo span").forEach(sp => { sp.style.clipPath = ""; });
  document.querySelectorAll(".cl-node").forEach(n => { n.classList.remove("on"); n.querySelector(".st").textContent = "STANDBY"; });
  // —— 顶栏：会话号 / 时钟 / FPS 模拟（interval id 一并进 bootTimers，finishBoot 时 clearTimeout 同步清除） ——
  $("#clSession").textContent = "0x" + Math.random().toString(16).slice(2,10).toUpperCase();
  const tick = () => { $("#clTime").textContent = new Date().toTimeString().slice(0,8); };
  tick(); bootTimers.push(setInterval(tick, 1000));
  bootTimers.push(setInterval(()=>{ $("#clFps").textContent = 58 + Math.round(Math.random()*4); }, 700));
  const kv = (k,v,cls) => '<div class="cl-dt"><span class="k">'+k+'</span><span class="v '+(cls||"")+'">'+esc(v)+'</span></div>';
  // —— PROFILE 面板：真实档案 ——
  const p = s.profile;
  $("#clTele").innerHTML =
    '<div class="cl-sect">PROFILE</div>'
    + kv("USER", UID)
    + kv("WATCHING", p.watching.length ? p.watching.length + " 项在追" : "空档案（新朋友）")
    + '<div class="cl-sect">PERSONA</div>'
    + kv("HUMOR", "档位 " + p.humor_level + " / 3")
    + kv("PERSONA", "毒舌但暖", "gold")
    + '<div class="cl-sect">MEMORY</div>'
    + kv("LAYERS", "短期 / 摘要 / 长期")
    + kv("GUARD", "ONLINE · 最高优先级", "bad");
  // —— SKILL INJECTION 代码流：技能装载伪代码循环滚动 ——
  const CL_CODE = [
    'skill.register("玩梗陪聊", prio=1);',
    'skill.register("倾听共情", prio=2);',
    'skill.register("暖心开导", prio=3);',
    'skill.register("关系树洞", prio=4);',
    'skill.register("危机守护", prio=MAX);',
    'regex.load(6) -> emotion_lexicon;',
    'mem.bus.attach("short_term", window=12);',
    'mem.bus.attach("summary", compress=true);',
    'mem.bus.attach("long_term", profile.sync);',
    'persona.inject("小狐 · 毒舌但暖");',
    'humor.calibrate(level=' + p.humor_level + ');',
    'llm.warmup() -> 200 OK;'
  ];
  const codeEl = $("#clCode"); let ci = 0;
  bootTimers.push(setInterval(()=>{
    const d = document.createElement("div");
    d.textContent = "> " + CL_CODE[ci % CL_CODE.length];
    codeEl.appendChild(d);
    while(codeEl.children.length > 30) codeEl.firstChild.remove();
    ci++;
  }, 150));
  // —— 打字机：每帧 2 字符（跳过后 dead() 短路退出） ——
  const type = async (el, text) => {
    for(let i = 0; i < text.length; i += 2){
      if(dead()) return false;
      el.textContent = text.slice(0, i + 2);
      await sleep(14);
    }
    el.textContent = text; return true;
  };
  (async ()=>{
    // 狐狸 logo 描线动画（550C 字标的等价演绎）：轮廓描线 1.6s → 五官弹出 → 字标揭示
    bootTimers.push(setTimeout(()=>{
      foxHead.style.transition = "stroke-dashoffset 1.6s ease-in-out";
      foxHead.style.strokeDashoffset = "0";
    }, 200));
    bootTimers.push(setTimeout(()=>{ document.querySelector(".cl-fox-f").classList.add("on"); }, 1950));
    await sleep(2400);
    if(dead()) return;
    // 字标逐字揭示（两段 span 依次展开 clip-path）
    document.querySelectorAll("#clStageBox .cl-logo span").forEach((sp, i)=>{
      bootTimers.push(setTimeout(()=>{ sp.style.clipPath = "inset(0 0 0 0)"; }, i*300));
    });
    await type($("#clBootTxt"), "XIAOHU SYSTEM BOOT");
    if(dead()) return;
    await sleep(500);
    if(dead()) return;
    $("#clStageBox").classList.add("off");       // 舞台收起，工作区成为主角
    // 9 行日志的 STAGE 与配色映射
    const META = [
      ["BOOT","sys"],["BOOT","sys"],["SKILL","sys"],["SKILL","sys"],
      ["MEM","sys"],["MEM","sys"],["GUARD","warn"],["PERSONA","sys"],["READY","ok"]
    ];
    const main = $("#clMain");
    for(let i = 0; i < lines.length; i++){
      if(dead()) return;
      $("#clStage").textContent = META[i][0];
      const ln = document.createElement("div");
      ln.className = "cl-ln " + META[i][1];
      ln.innerHTML = '<span class="cl-pfx">[XIAOHU]</span> <span class="cl-tx"></span> <span class="cl-ok">[ OK ]</span>';
      main.appendChild(ln);
      if(!await type(ln.querySelector(".cl-tx"), lines[i])) return;
      $("#clLine").textContent = String(i+1).padStart(2,"0") + " / " + String(lines.length).padStart(2,"0");
      const pct = Math.round((i+1) / lines.length * 100);
      $("#clFill").style.width = pct + "%"; $("#clPct").textContent = pct + "%";
      if(i === 2){   // 技能注册表行 → 矩阵 5 格逐格点亮
        document.querySelectorAll(".cl-node").forEach((n, j)=>{
          bootTimers.push(setTimeout(()=>{ n.classList.add("on"); n.querySelector(".st").textContent = "ONLINE"; }, j*160));
        });
      }
      if(i === 6){ $("#clNet").textContent = "GUARD-UP"; $("#clNet").classList.add("gold"); }
      await sleep(80);
    }
    if(dead()) return;
    $("#clStage").textContent = "READY";
    $("#clNet").textContent = "ONLINE";
    await sleep(280);
    if(dead()) return;
    $("#clFinal").classList.add("show");         // 定格大字「小狐已上线」
    await sleep(1150);
    if(dead()) return;
    finishBoot();
  })();
}

// ================= Codex 完整版启动主题（移植编排） =================
// 动画逻辑来源：yanami-sec/codex-startup-animation-windows
//（上游 panding999/codex-startup-animation），仅用于课堂作业演示；
// 未复制上游素材文件，仅提取/改写其"单时钟分阶段"编排思路与关键参数。
// 我们版本的分阶段时间线（毫秒，总计 10.4s 后交还 finishBoot，期间点击任意处可跳过）：
//   0     中心脉冲环 + 网格/四角框亮起；0.2s 起左下角逐行打印 9 行启动日志
//   1000  雷达圈 + 圆形头像 + 标题组淡入（头像心跳、虚线环旋转）
//   1900  标题「小狐」自左向右展开；2500 小字「XIAOHU · 狐仙系统」浮现
//   4200  前半段整体淡出，立绘登场：粒子向剑士轮廓汇聚（codex_particles.json）
//   5300  粒子汇聚成形 → 线稿显影接棒（codex-art-line.png，左→右）
//   5600  彩色立绘淡入完成"上色"（codex-art.jpg），暗角/星域粒子/雾/扫描线跟进（对应壁纸 scene 三层）
//   6800  HUD 亮起：SYNC RATIO 进度推进 + 斜向扫光 + 底部字幕浮现
//   9300  字幕淡出
//   9800  "画面合拢"：场景上下压缩(scaleY→0) + 中缝亮线横向收束
//   10400 调用 finishBoot()：淡出 #boot 遮罩进入主界面
function runBootCodex(lines){
  const box = document.getElementById("bootCodex");
  box.className = "";                      // 再清一次阶段类，防重播残留
  // —— 前半段启动日志：沿用 fetch /api/state 拼好的 9 行，0.2s 起每 300ms 一行 ——
  const logsEl = document.getElementById("cdxLogs");
  logsEl.innerHTML = "";
  lines.forEach((t,i)=>{
    bootTimers.push(setTimeout(()=>{
      const div = document.createElement("div");
      div.innerHTML = '<span class="pfx">&gt;</span> ' + esc(t) + ' <span class="ok">[ OK ]</span>';
      logsEl.appendChild(div);
    }, 200 + i*300));
  });
  // 阶段切换辅助：at(毫秒, 状态类)。所有定时器统一进 bootTimers，
  // 跳过(finishBoot)/重播(runBoot)时被 clearTimeout 一并清除，天然防竞态。
  const at = (ms, cls) => bootTimers.push(setTimeout(()=>box.classList.add(cls), ms));
  at(1000,  "cdxId");      // 雷达头像组入场
  at(1900,  "cdxTitle");   // 标题「小狐」自左向右展开
  at(2500,  "cdxCap");     // 小字「XIAOHU · 狐仙系统」浮现
  at(4200,  "cdxDraw");    // 前半段退场 → 粒子开始向轮廓汇聚
  bootTimers.push(setTimeout(cdxParticleSketch, 4200)); // 粒子描线动画（真实 canvas 粒子变换）
  at(5300,  "cdxLineIn");  // 粒子汇聚成形 → 线稿图显影接棒（左→右显影）
  at(5600,  "cdxColor");   // 线稿"上色"成彩色立绘
  at(6800,  "cdxHudIn");   // HUD + 扫光 + 底部字幕
  at(9300,  "cdxSubOut");  // 字幕淡出
  at(9800,  "cdxClosing"); // 画面合拢
  bootTimers.push(setTimeout(cdxStarfield, 5600));   // 壁纸"星域"粒子层：上色阶段启动
  bootTimers.push(setTimeout(finishBoot, 10400));
  // —— SYNC RATIO 进度曲线：复用上游的里程碑平滑插值（前段慢、中段快、收尾平滑）——
  const CDX_MILESTONES = [[0,0],[.12,.06],[.35,.41],[.56,.76],[.66,.924],[.72,.97],[.77,1],[1,1]];
  const clampN  = n => Math.max(0, Math.min(1, n));
  const smoothN = n => { const t = clampN(n); return t*t*(3-2*t); };
  function progress(t){
    for(let i = 1; i < CDX_MILESTONES.length; i++){
      if(t <= CDX_MILESTONES[i][0]){
        const a = CDX_MILESTONES[i-1], b = CDX_MILESTONES[i];
        return a[1] + (b[1]-a[1]) * smoothN((t-a[0])/(b[0]-a[0]));
      }
    }
    return 1;
  }
  const fill    = document.querySelector("#bootCodex .cdxFill");
  const ratioEl = document.getElementById("cdxRatio");
  const phaseEl = document.getElementById("cdxPhase");
  const timeEl  = document.getElementById("cdxTime");
  const TOTAL = 10400;
  const pad2  = n => String(n).padStart(2, "0");
  // 自调度心跳：每 100ms 刷新进度条/百分比/阶段文案/时间码（同样纳入 bootTimers）
  (function tick(el){
    if(el > TOTAL) return;
    const p = progress(el / TOTAL);
    fill.style.transform = "scaleX(" + p + ")";
    ratioEl.textContent = (p*100).toFixed(2).padStart(5, "0") + "%";
    phaseEl.textContent = el < 6800 ? "INITIALIZING" : p < 1 ? "SYNCHRONIZING" : "SYNC COMPLETE";
    timeEl.textContent  = "00:" + pad2(Math.floor(el/1000)) + ":" + pad2(Math.floor(el%1000/1000*30));
    bootTimers.push(setTimeout(()=>tick(el+100), 100));
  })(0);
}
// ================= 粒子描线动画（Codex 主题 4.2s~5.6s 阶段） =================
// 原理：事先用 opencv 从 fox_spirit_line.png 提取 4000 个轮廓点（fox_particles.json），
// canvas 里每颗粒子从画面随机位置出发，错峰飞向自己的目标轮廓点，汇聚成狐狸线稿；
// 汇聚完成后线稿图（cdxLineIn）显影接棒，随后彩色立绘淡入覆盖。
let cdxAnimGen = 0;   // 动画代号：重播/跳过时 +1，旧 rAF 循环检测到代号变化即自杀
let cdxParticlesCache = null;   // 粒子目标点缓存（首次 fetch 后复用）
function cdxParticleSketch(){
  const gen = ++cdxAnimGen;                 // 本轮代号
  const box = document.getElementById("bootCodex");
  const art = box.querySelector(".cdxArt");
  const cv  = box.querySelector(".cdxCanvas");
  const ctx = cv.getContext("2d");
  // 画布按容器实际尺寸×DPR 设置，保证高分屏清晰
  const cw = art.clientWidth, ch = art.clientHeight, dpr = window.devicePixelRatio || 1;
  cv.width = cw * dpr; cv.height = ch * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // 装载粒子目标点（带缓存），失败则静默跳过（动画降级为纯线稿显影，不影响流程）
  const start = (data) => {
    if(gen !== cdxAnimGen) return;
    const aspect = data.aspect;   // 原图宽高比，用于和 CSS cover 裁剪对齐
    let drawW, drawH, offX, offY;
    if(aspect > cw / ch){ drawW = cw; drawH = cw / aspect; offX = 0; offY = (ch - drawH) / 2; }
    else               { drawH = ch; drawW = ch * aspect; offY = 0; offX = (cw - drawW) / 2; }
    // 初始化粒子：起点画面随机散布，终点为轮廓点；错峰出发（0~500ms），飞行 0.7~1.1s
    const pts = data.points;
    const parts = pts.map(p => {
      const tx = offX + p[0] * drawW, ty = offY + p[1] * drawH;
      return { sx: Math.random() * cw, sy: Math.random() * ch, tx, ty,
               d: Math.random() * 500, t: 700 + Math.random() * 400,
               big: Math.random() < 0.06, warm: Math.random() < 0.25 };
    });
    const T0 = performance.now(), MAX = 500 + 1100 + 300;   // 出发延迟 + 最长飞行 + 尾光
    const ease = t => 1 - Math.pow(1 - t, 3);               // easeOutCubic：先快后缓地"落座"
    (function frame(now){
      if(gen !== cdxAnimGen) return;                        // 被跳过/重播：停止绘制
      const el = now - T0;
      ctx.clearRect(0, 0, cw, ch);
      let alive = 0;
      for(const q of parts){
        const local = el - q.d;
        if(local <= 0){ continue; }                         // 还没出发
        const k = ease(Math.min(1, local / q.t));
        const x = q.sx + (q.tx - q.sx) * k, y = q.sy + (q.ty - q.sy) * k;
        alive++;
        if(q.big){   // 少量"亮星"粒子：更大、带光晕，增强层次
          ctx.fillStyle = "rgba(240,230,190,.28)";
          ctx.fillRect(x - 2.5, y - 2.5, 5, 5);
          ctx.fillStyle = "rgba(255,246,210,.95)";
          ctx.fillRect(x - 1, y - 1, 2, 2);
        } else {     // 常规粒子：暖金/品红两色小方点（对应上游霓虹描线风）
          ctx.fillStyle = q.warm ? "rgba(236,150,170,.9)" : "rgba(238,200,90,.9)";
          ctx.fillRect(x - 0.8, y - 0.8, 1.6, 1.6);
        }
      }
      if(alive === 0 && el > MAX) return;                   // 全部落座且到时：结束循环
      if(el < MAX + 600) requestAnimationFrame(frame);      // 多留 0.6s 展示成形线稿
    })(T0);
  };
  if(cdxParticlesCache){ start(cdxParticlesCache); return; }
  fetch("/static/codex_particles.json").then(r=>r.json()).then(d=>{ cdxParticlesCache = d; start(d); })
    .catch(()=>{ /* 加载失败：跳过粒子层，后续线稿显影照常进行 */ });
}

// ================= 星域粒子层（Codex/粒子动画主题 5.6s 起，壁纸 particles/presets/starfield.json 的移植） =================
// 壁纸参数：512 颗白色星粒、球域随机发射、初速沿 +Z（屏幕上即向上）、spritetrail 拖尾、
// alphafade（0.1s 淡入 / 0.9s 淡出）、drag 0.2。此处用 canvas 2D 等效实现。
let cdxStarsGen = 0;
function cdxStarfield(){
  const gen = ++cdxStarsGen;
  const cv = document.querySelector("#bootCodex .cdxStars");
  if(!cv) return;
  const ctx = cv.getContext("2d");
  const bootEl = document.getElementById("boot");
  const dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  const W = cv.width, H = cv.height, R = Math.random;
  const spawn = q => {                       // 出生态：屏幕内随机位置，向上漂（对应 +Z 速度）
    q.x = R() * W; q.y = R() * H + H * 0.12;
    q.vy = -(30 + R() * 85) * dpr; q.vx = (R() - .5) * 9 * dpr;
    q.s = (R() < .08 ? 2.4 : 1.2) * dpr;     // 少量大星
    q.life = 0; q.max = 4 + R() * 5;
  };
  const P = [];
  for(let i = 0; i < 512; i++){ const q = {}; spawn(q); q.y = R() * H; q.life = R() * q.max; P.push(q); }
  let last = performance.now();
  (function frame(now){
    if(gen !== cdxStarsGen || bootEl.classList.contains("done")) return;   // 跳过/重播/结束：停止
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    ctx.globalCompositeOperation = "destination-out";                      // 拖尾：逐帧擦淡旧迹
    ctx.fillStyle = "rgba(0,0,0,.2)";
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "source-over";
    for(const q of P){
      q.life += dt;
      if(q.life > q.max){ spawn(q); continue; }
      q.vy *= (1 - .2 * dt); q.x += q.vx * dt; q.y += q.vy * dt;           // drag 0.2
      const a = Math.min(1, q.life / .5, (q.max - q.life) / 1.2) * .85;    // alphafade 0.1/0.9
      if(a <= 0) continue;
      ctx.fillStyle = "rgba(236,240,255," + a.toFixed(3) + ")";
      ctx.fillRect(q.x, q.y, q.s, Math.min(16 * dpr, -q.vy * .07));        // 星迹：沿速度方向拉伸
    }
    requestAnimationFrame(frame);
  })(last);
}

// ================= EVA 驾驶员认证启动主题（仿造 dsh-plugin-eva-theme） =================
// 素材（NERV/明日香/绫波丽/鹭巢诗郎《EM20#070720》/日语配音）为第三方版权，仅课堂演示。
// 时间线：NERV GIF(3.84s) → 红色警报(3s) → 打字标题 → 驾驶员选择(点选/按1 2，9s 兜底) →
//         应答+启动语音+同步率进度 → 双侧舱门(1.6s) → finishBoot() 进入主界面。
let evaSound = true;             // 默认开启声音；页面刚加载时浏览器可能拦自动播放，首次点击/按键会自动补启 BGM（见 unlockBootAudio）
let evaGen = 0;                  // 本次启动世代号（跳过/重播时作废旧的 timeout/rAF）
let evaContoursRaf = 0;          // 等高线 rAF 句柄
// EVA 专用计时器：跑在 Web Worker 线程里。页面切到后台/失焦时，主线程 setTimeout 会被
// Chrome 节流（110ms 打字被拖成 1s+、9 秒选择窗实测拖到 44s），导致 GIF/警报/打字/选择页
// 时序全乱、看起来"跳幕"；Worker 线程不受页面可见性节流影响，切走也能准时触发。
const evaTick = (() => {
  let w = null; const pend = new Map(); let seq = 0;
  try{
    w = new Worker(URL.createObjectURL(new Blob([
      "const t=new Map();onmessage=e=>{const d=e.data;if(d.id){t.set(d.id,setTimeout(()=>{postMessage(d.id);t.delete(d.id)},d.ms))}else{t.forEach(clearTimeout);t.clear()}}"
    ], {type:"text/javascript"})));
    w.onmessage = e => { const fn = pend.get(e.data); pend.delete(e.data); if(fn) fn(); };
  }catch(err){ w = null; }   // Worker 不可用（file:// 等）时退回主线程 setTimeout
  return {
    at(ms, fn){
      if(w){ const id = ++seq; pend.set(id, fn); w.postMessage({id, ms}); return; }
      return setTimeout(fn, ms);
    },
    clearAll(){ if(w){ w.postMessage({}); pend.clear(); } }
  };
})();
let evaSyncRaf = 0;              // 同步进度 rAF 句柄
let evaBgm = null;               // 循环背景乐
let evaVoices = [];              // 一次性语音池（跳过时统一掐断）
const EVA_PILOTS = {
  asuka:{ order:"02", name:"明日香", unit:["EVA-02","A-264 SORYU"], ms:6840,
          boot:"/static/eva/asuka-voice-boot.mp3", select:"/static/eva/asuka-voice-select.mp3", welcome:"/static/eva/asuka-voice-welcome.mp3",
          skin:{ bodyClass:"eva-asuka", bg:"/static/eva/asuka-portrait-lineart-light.png",
                 banner:"欢迎回来！好，开始吧！", bannerSub:"ASUKA / WELCOME · UNIT-02 DARK MODE" } },
  rei:  { order:"00", name:"绫波丽", unit:["EVA-00","R-000 AYANAMI"], ms:6600,
          boot:"/static/eva/rei-voice-boot.mp3",   select:"/static/eva/rei-voice-select.mp3",   welcome:"/static/eva/rei-voice-welcome.mp3",
          skin:{ bodyClass:"eva-rei", bg:"/static/eva/rei-portrait-lineart.png",
                 banner:"欢迎回来。开始吧。", bannerSub:"REI / WELCOME · UNIT-00 LIGHT MODE" } }
};

// ================= EVA 双生驾驶舱皮肤 =================
// 选完驾驶员进入聊天后，整个界面换装成对应驾驶员配色（明日香=暗色红黑 / 绫波丽=亮色白蓝），
// 并叠加装饰：左上时钟、角色线稿背景、编号大水印、欢迎横幅（对齐视频 DARK/LIGHT MODE 效果）。
let evaClockTimer = 0;
function applyEvaSkin(pid){
  const P = EVA_PILOTS[pid];
  if(!P || !P.skin) return;
  document.body.classList.remove("eva-asuka","eva-rei");
  document.body.classList.add(P.skin.bodyClass);
  const bg = document.getElementById("chatBg");
  if(bg) bg.src = P.skin.bg;
  const wm = document.getElementById("evaWatermark");
  if(wm) wm.textContent = P.order;
  if(!evaClockTimer){
    const tick = ()=>{ const el = document.getElementById("evaClock"); if(el) el.textContent = new Date().toTimeString().slice(0,8); };
    tick(); evaClockTimer = setInterval(tick, 1000);
  }
  const bn = document.getElementById("evaBanner");
  if(bn){
    document.getElementById("evaBannerTitle").textContent = P.skin.banner;
    document.getElementById("evaBannerSub").textContent = P.skin.bannerSub;
    // 注意：applyEvaSkin 由 finishBoot 调用，而 finishBoot 随后会清空 bootTimers，
    // 因此横幅定时器不能用 bootTimers 管理，否则 600ms 的 show 会被立刻清掉。
    setTimeout(()=>bn.classList.add("show"), 600);
    setTimeout(()=>bn.classList.remove("show"), 6600);
  }
}
function clearEvaSkin(){
  document.body.classList.remove("eva-asuka","eva-rei");
  if(evaClockTimer){ clearInterval(evaClockTimer); evaClockTimer = 0; }
  const bg = document.getElementById("chatBg");
  if(bg) bg.src = "/static/fox_spirit.jpg";   // 恢复狐仙立绘背景，避免残留角色线稿
  localStorage.removeItem("evaPilot");
}

// 播放一段音频（仅声音开启时出声）；返回 Audio 供外部控制，null 表示被静音跳过
function evaPlay(src, loop){
  if(!evaSound) return null;
  const a = new Audio(src);
  a.loop = !!loop;
  evaVoices.push(a);
  const p = a.play();
  if(p && p.catch) p.catch(()=>{});
  return a;
}
function evaBgmStart(){
  stopEvaBgm();
  if(!evaSound) return;
  evaBgm = new Audio("/static/eva/nerv-boot-music.mp3");
  evaBgm.loop = true;
  evaBgm.volume = .1;
  evaVoices.push(evaBgm);
  const p = evaBgm.play();
  if(p && p.catch) p.catch(()=>{});
}
function stopEvaBgm(){ if(evaBgm){ evaBgm.pause(); evaBgm = null; } }
function stopEvaAudio(){
  stopEvaBgm();
  evaVoices.forEach(a=>{ try{ a.pause(); a.currentTime = 0; }catch(_){} });
  evaVoices = [];
}

// 橙色等高线：移植 boot-contours.js 的 marching-squares 高度场，实时生成 24 层截线到 SVG
function evaContours(svg){
  const NS = "http://www.w3.org/2000/svg";
  const paths = [];
  for(let k=0;k<24;k++){ const p = document.createElementNS(NS, "path"); svg.appendChild(p); paths.push(p); }
  const columns = 81, rows = 51, heights = new Float32Array(columns * rows);
  const pairs = [[],[0,3],[0,1],[1,3],[1,2],null,[0,2],[2,3],[2,3],[0,2],null,[1,2],[1,3],[0,1],[0,3],[]];
  const render = (time) => {
    const result = [], phase = time * .18,
      peaks = [[.18 + .035*Math.sin(phase), .17 + .04*Math.cos(phase*.7), .03, .055, 1.2],
               [.89 + .03*Math.cos(phase*.8), .84 + .06*Math.sin(phase*.65), .045, .09, 1.3],
               [-.1, .9, .06, .07, .65], [.54, .53, .06, .05, -.45]];
    for(let y=0;y<rows;y++) for(let x=0;x<columns;x++){
      const u = x/(columns-1), v = y/(rows-1);
      let h = .11*Math.sin(9*u + 3*v + phase) + .075*Math.cos(12*v - 4*u - phase*.8) + .035*Math.sin(18*u - 11*v + phase*.6);
      for(const [px,py,sx,sy,gain] of peaks) h += gain*Math.exp(-((u-px)**2/sx + (v-py)**2/sy));
      heights[y*columns + x] = h;
    }
    for(let li=0;li<24;li++){
      const level = -.26 + li*.065, nodes = new Map();
      for(let y=0;y<rows-1;y++) for(let x=0;x<columns-1;x++){
        const i = y*columns + x, a = heights[i], b = heights[i+1], c = heights[i+columns+1], d = heights[i+columns];
        const mask = (a>level?1:0) | (b>level?2:0) | (c>level?4:0) | (d>level?8:0);
        let edges = pairs[mask];
        if(edges === null){ const centerHigh = (a+b+c+d)/4 > level; edges = (mask===5)===centerHigh ? [0,1,2,3] : [0,3,1,2]; }
        if(!edges.length) continue;
        const edge = (id) => {
          const horiz = id % 2 === 0, xx = x + (id===1 ? 1 : 0), yy = y + (id===2 ? 1 : 0);
          const key = horiz ? yy*(columns-1) + xx : rows*(columns-1) + yy*columns + xx;
          if(!nodes.has(key)){
            const from = id===0||id===3 ? a : id===1 ? b : d, to = id===0 ? b : id===3 ? d : c, t = (level-from)/(to-from);
            nodes.set(key, { x:(xx + (horiz ? t : 0))*20, y:(yy + (horiz ? 0 : t))*20, links:[] });
          }
          return nodes.get(key);
        };
        for(let e=0;e<edges.length;e+=2){ const f = edge(edges[e]), t = edge(edges[e+1]); f.links.push(t); t.links.push(f); }
      }
      const visited = new Set(), curves = [], point = p => p.x.toFixed(1) + " " + p.y.toFixed(1),
        mid = (a,b) => ({ x:(a.x+b.x)/2, y:(a.y+b.y)/2 });
      const trace = (start) => {
        if(visited.has(start)) return;
        const chain = []; let node = start;
        while(node && !visited.has(node)){ visited.add(node); chain.push(node); node = node.links.find(n => !visited.has(n)); }
        if(chain.length < 2) return;
        const last = chain[chain.length-1], closed = chain.length > 2 && last.links.includes(start);
        let path = "M" + point(closed ? mid(last,start) : start);
        for(let n = closed ? 0 : 1; n < chain.length - (closed ? 0 : 1); n++)
          path += "Q" + point(chain[n]) + " " + point(mid(chain[n], chain[(n+1)%chain.length]));
        curves.push(path + (closed ? "Z" : "L" + point(last)));
      };
      for(const node of nodes.values()) if(node.links.length === 1) trace(node);
      for(const node of nodes.values()) trace(node);
      result.push(curves.join(""));
    }
    return result;
  };
  return (t) => { const res = render(t); for(let k=0;k<24;k++) paths[k].setAttribute("d", res[k]); };
}

function evaFmtSec(s){
  s = Math.max(0, Math.floor(s));
  return ("0" + Math.floor(s/60)).slice(-2) + ":" + ("0" + (s%60)).slice(-2);
}

function pickPilot(id){
  const box = document.getElementById("bootEva");
  if(box.getAttribute("data-phase") !== "select") return;   // 已在装载则忽略重复选择
  const g = evaGen, P = EVA_PILOTS[id];
  box.setAttribute("data-pilot", id);
  box.setAttribute("data-phase", "loading");
  document.getElementById("evaLoadName").textContent = P.name + " · 同步开始";
  document.getElementById("evaClearName").textContent = P.name + " · 同步完成";
  document.getElementById("evaCode").textContent = P.unit[0] + " 插入栓装载 · " + P.unit[1];
  const bu = box.querySelector("[data-boot-unit]");
  if(bu) bu.textContent = P.order;
  localStorage.setItem("evaPilot", id);        // 记住所选驾驶员，finishBoot 时据此应用双生皮肤
  evaPlay(P.select);
  evaTick.at(900, ()=>{                         // 短应答音后接启动语音，并推进同步率（Worker 计时，后台不节流）
    if(g !== evaGen) return;
    const bootAudio = evaPlay(P.boot);          // 返回 Audio（静音时 null）；进度据此跟随真实播放位置
    runEvaSync(P.ms, bootAudio);
  });
}

function runEvaSync(dur, audio){
  // 用 setTimeout 驱动推进而非 requestAnimationFrame：后台标签页里 rAF 会被节流/暂停，
  // 导致卡在"装载"阶段无法进入"舱门开启"。setTimeout 即便后台也会继续走，保证收尾一定能触发。
  const g = evaGen, box = document.getElementById("bootEva"),
    meter = document.getElementById("evaMeter"),
    ring = document.getElementById("evaRing"), ratio = document.getElementById("evaRatio"),
    timeEl = document.getElementById("evaTime"), phaseTxt = document.getElementById("evaPhaseTxt");
  const phases = ["接続開始", "神経同期中", "L.C.L. 注入", "思念波共鸣"];
  let t0 = performance.now();   // 墙钟起点：语音暂停切回墙钟时会动态校准（故为 let，const 会抛 TypeError 卡死进度）
  // 进度优先跟随真实语音播放位置（currentTime/duration，对齐 dsh-plugin-eva-theme），
  // 静音或时长不可用时退回墙钟（dur 毫秒）。
  let realDur = (audio && isFinite(audio.duration) && audio.duration > 0) ? audio.duration : 0;
  let finished = false;
  const completeSync = () => {
    if(finished || g !== evaGen) return;
    if(box.getAttribute("data-phase") !== "loading") return;
    finished = true;
    box.setAttribute("data-phase", "handoff");      // 双侧舱门开启
    evaPlay(EVA_PILOTS[box.getAttribute("data-pilot")].welcome);
    evaTick.at(1600, ()=>{ if(g !== evaGen) return; finishBoot(); });
  };
  if(audio){
    audio.addEventListener("durationchange", ()=>{ if(audio.duration && isFinite(audio.duration)) realDur = audio.duration; });
    audio.addEventListener("ended", ()=>{ if(g === evaGen) completeSync(); });   // 语音自然结束即推进舱门
  }
  let lastT = 0;
  const step = () => {
    if(g !== evaGen || finished) return;
    let t;
    if(audio && !audio.paused && realDur > 0){
      // 跟随真实语音播放位置；同时校准墙钟起点，语音被暂停/关声音时可无感切回墙钟继续推进
      t = Math.min(1, audio.currentTime / realDur);
      lastT = t; t0 = performance.now() - t * dur;
    }
    else{
      // 语音被 pause（如点了"关闭声音"）或时长不可用：墙钟从当前进度继续，防止进度停在原地卡死
      t = Math.max(lastT, Math.min(1, (performance.now() - t0) / dur));
    }
    meter.style.transform = "scaleX(" + t + ")";
    ring.style.strokeDashoffset = (440 * (1 - t)).toFixed(1);
    ratio.textContent = (t * 100).toFixed(1) + "%";
    timeEl.textContent = evaFmtSec(t * (realDur || dur) / 1000);
    phaseTxt.textContent = phases[Math.min(phases.length-1, Math.floor(t * phases.length))];
    if(t < 1){ evaTick.at(66, step); }
    else{ completeSync(); }
  };
  step();
}

function runBootEva(){
  const box = document.getElementById("bootEva");
  const g = ++evaGen;                              // 本次启动世代号
  evaTick.clearAll();                              // 清掉 Worker 里上一轮的计时（后台不节流，必须显式清）
  stopEvaAudio();
  clearEvaSkin();                                  // 重新认证：先脱掉上一轮的双生皮肤
  // 复位各阶段
  box.setAttribute("data-phase", "gif");
  box.setAttribute("data-pilot", "asuka");
  box.setAttribute("data-sound", evaSound ? "on" : "off");
  document.getElementById("evaMuteBtn").textContent = evaSound ? "声音：开" : "声音：关";
  document.getElementById("evaTyped").textContent = "";
  document.getElementById("evaTitle").textContent = "选择你的驾驶员";
  document.getElementById("evaMeter").style.transform = "scaleX(0)";
  document.getElementById("evaRing").style.strokeDashoffset = "440";
  document.getElementById("evaRatio").textContent = "0.0%";
  document.getElementById("evaTime").textContent = "00:00";
  document.getElementById("evaPhaseTxt").textContent = "接続開始";
  // 等高线独立于阶段循环渲染（仅 rAF，不占用 bootTimers；结束时用 evaGen 作废）
  const conts = evaContours(box.querySelector(".eva-contours"));
  const cloop = () => { if(g !== evaGen) return; conts(performance.now()/1000); evaContoursRaf = requestAnimationFrame(cloop); };
  evaContoursRaf = requestAnimationFrame(cloop);
  evaBgmStart();
  const at = (ms, fn) => evaTick.at(ms, ()=>{ if(g !== evaGen) return; fn(); });
  at(3840, ()=>{                                   // GIF 播完 → 红色警报
    box.setAttribute("data-phase", "emergency");
    const clk = box.querySelector("[data-emergency-clock]");
    if(clk) clk.textContent = new Date().toTimeString().slice(0, 8);
  });
  at(3840 + 3000, ()=>{ box.setAttribute("data-phase","intro"); evaType(g); });   // 警报 3s → 打字标题
}

// 打字标题：逐字出现"选择你的驾驶员"，配打字音；完成后进入选择页，等待用户选择（点击/拖拽/1·2 键，不自动选人）
function evaType(g){
  const text = "选择你的驾驶员";
  const el = document.getElementById("evaTyped");
  evaPlay("/static/eva/nerv-ui-typing.mp3");
  let i = 0;
  (function loop(){
    if(g !== evaGen) return;
    if(i < text.length){
      el.textContent = text.slice(0, ++i);
      evaTick.at(110, loop);                       // Worker 计时：失焦/后台时打字速度不被拖慢
    } else {
      evaTick.at(460, ()=>{
        if(g !== evaGen) return;
        document.getElementById("bootEva").setAttribute("data-phase","select");
        // 选择页保持停留，等待用户拖拽/点击卡片或按 1/2 键，避免自动默认成明日香
      });
    }
  })();
}

// ================= EVA 电影感启动主题（仿造 dsh-eva-boot 1.1.5 cine 模式） =================
// 时间轴（毫秒，与上游 sequence() 一致）：HUD(0) → 02字标+光带(600) → 插入栓(1900) →
// LCL(3800) → 神经接驳(5900) → 机构退场(8200) → 线稿扫过(8400) → 海报层(10300) → 字标(12000) → 收尾(14600)。
let cineGen = 0;            // 世代号：跳过/重播/收尾时作废在跑的定时器与 rAF
let cineStarted = false;    // 起播门是否已点「开始」
let cineSound = true;       // 默认开启声音；自动播放被浏览器拦截时由首次手势补启（见 unlockBootAudio）
let cineAudio = null;       // 启动音频（cine-audio.m4a，即上游 boot-audio）
let cineDustRaf = 0;        // 尘埃粒子 rAF 句柄
let cineCtx = null;         // WebAudio 合成音上下文（惰性创建）

function cineTone(freq, dur, type, level){
  if(!cineSound) return;
  try{
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if(!Ctx) return;
    if(!cineCtx) cineCtx = new Ctx();
    if(cineCtx.state === "suspended") cineCtx.resume();
    const t0 = cineCtx.currentTime, vol = Math.max(.001, Math.min(1, .3 * (level == null ? 1 : level)));
    const osc = cineCtx.createOscillator(), gain = cineCtx.createGain();
    osc.type = type || "sine";
    osc.frequency.setValueAtTime(freq, t0);
    gain.gain.setValueAtTime(.0001, t0);
    gain.gain.exponentialRampToValueAtTime(vol, t0 + .02);
    gain.gain.exponentialRampToValueAtTime(.0001, t0 + dur);
    osc.connect(gain); gain.connect(cineCtx.destination);
    osc.start(t0); osc.stop(t0 + dur + .03);
  }catch(e){ /* 声音失败不影响画面 */ }
}
function cineSwell(freq, dur){   // 低频渐强（LCL 注入 / 海报揭幕时用）
  if(!cineSound) return;
  try{
    if(!cineCtx) return;
    if(cineCtx.state === "suspended") cineCtx.resume();
    const t0 = cineCtx.currentTime;
    const osc = cineCtx.createOscillator(), gain = cineCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, t0);
    osc.frequency.exponentialRampToValueAtTime(freq * .5, t0 + dur);
    gain.gain.setValueAtTime(.0001, t0);
    gain.gain.exponentialRampToValueAtTime(Math.min(.5, .3), t0 + dur * .35);
    gain.gain.exponentialRampToValueAtTime(.0001, t0 + dur);
    osc.connect(gain); gain.connect(cineCtx.destination);
    osc.start(t0); osc.stop(t0 + dur + .05);
  }catch(e){ /* noop */ }
}
function startCineAudio(){
  if(!cineSound) return;
  try{
    if(!cineAudio){ cineAudio = new Audio("/static/eva/cine-audio.m4a"); cineAudio.volume = .5; }
    cineAudio.currentTime = 0;
    const p = cineAudio.play();
    if(p && p.catch) p.catch(()=>{});
  }catch(e){ /* noop */ }
}
function stopCineAudio(){ if(cineAudio){ try{ cineAudio.pause(); cineAudio.currentTime = 0; }catch(e){} } }

// 数字滚动：setTimeout 驱动（后台标签页 rAF 会被节流，收尾可能卡住——沿用 EVA 主题的教训）
function cineCount(id, from, to, dur, digits, suffix){
  const node = document.getElementById(id);
  if(!node) return;
  const g = cineGen, t0 = performance.now();
  const step = () => {
    if(g !== cineGen) return;
    const p = Math.min(1, Math.max(0, (performance.now() - t0) / dur));
    const v = from + (to - from) * (1 - Math.pow(1 - p, 3));
    node.textContent = v.toFixed(digits) + (suffix || "");
    if(p < 1) bootTimers.push(setTimeout(step, 66));
  };
  step();
}

// 左上任务列表：is-on 点亮当前步，is-done 标记已完成
function cineStep(idx){
  const steps = document.querySelectorAll("#bootCine .cine-step");
  steps.forEach((s, j)=>{
    s.classList.toggle("is-on", j === idx);
    s.classList.toggle("is-done", j < idx);
  });
  cineTone(660 + idx * 40, .045, "square", .2);
}

// 打字行：循环打出流程日志（机构面板出现后由 CSS 自动淡出）
function cineTypeLoop(g){
  const LINES = ["插入栓投放", "LCL 注入", "神经接驳", "同步率 98.4%"];
  let li = 0;
  (function typeLine(){
    if(g !== cineGen) return;
    const line = LINES[li % LINES.length]; li += 1;
    let i = 0;
    const el = document.getElementById("cineLog");
    (function tick(){
      if(g !== cineGen) return;
      i += 1;
      el.textContent = line.slice(0, i);
      if(i < line.length) bootTimers.push(setTimeout(tick, 42));
      else bootTimers.push(setTimeout(typeLine, 900));
    })();
  })();
}

// 尘埃粒子：缓慢上浮的微光，rAF 渲染（装饰层，后台被节流无碍）
function cineDust(box){
  const canvas = box.querySelector(".cine-dust");
  const ctx2d = canvas.getContext("2d");
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  let W = 0, H = 0;
  const parts = [];
  const resize = () => {
    const rect = box.getBoundingClientRect();
    W = Math.max(1, Math.round(rect.width)); H = Math.max(1, Math.round(rect.height));
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    parts.length = 0;
    const count = Math.max(36, Math.min(120, Math.round((W * H) / 24000)));
    for(let i = 0; i < count; i++) parts.push({
      x: Math.random()*W, y: Math.random()*H, r: .6 + Math.random()*1.6,
      vy: -.06 - Math.random()*.22, vx: (Math.random()-.5)*.08,
      a: .15 + Math.random()*.5, tw: Math.random()*Math.PI*2
    });
  };
  resize();
  const draw = () => {
    if(!ctx2d) return;
    ctx2d.clearRect(0, 0, W, H);
    for(const p of parts){
      p.y += p.vy; p.x += p.vx; p.tw += .02;
      if(p.y < -6){ p.y = H + 6; p.x = Math.random()*W; }
      if(p.x < -6) p.x = W + 6;
      if(p.x > W + 6) p.x = -6;
      ctx2d.beginPath();
      ctx2d.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx2d.fillStyle = "rgba(190,232,255," + (p.a * (.6 + .4*Math.sin(p.tw))).toFixed(3) + ")";
      ctx2d.fill();
    }
    cineDustRaf = requestAnimationFrame(draw);
  };
  draw();
}

// 起播门「开始」：关门 → 放启动音频 → 跑时间轴
function beginCineSeq(){
  if(cineStarted) return;
  cineStarted = true;
  const gate = document.getElementById("cineGate");
  gate.classList.add("is-out");
  startCineAudio();
  runCineTimeline();
}

function runCineTimeline(){
  const g = cineGen, box = document.getElementById("bootCine");
  const at = (ms, fn) => bootTimers.push(setTimeout(()=>{ if(g !== cineGen) return; fn(); }, ms));
  const plug = document.getElementById("cinePPlug"),
        lcl = document.getElementById("cinePLcl"),
        sync = document.getElementById("cinePSync"),
        lineart = box.querySelector(".cine-lineart"),
        bg = box.querySelector(".cine-bg");
  at(0, ()=>{ box.classList.add("is-hud","is-backdrop"); cineTone(146.83, .26, "sawtooth", .32); });
  at(600, ()=>{   // 02 字标擦除揭幕 + 横穿光带 + 打字行
    box.classList.add("is-mark");
    cineTone(196, .3, "triangle", .42);
    bootTimers.push(setTimeout(()=>{ if(g === cineGen) cineTypeLoop(g); }, 260));
  });
  at(1900, ()=>{  // 插入栓投放：栓体下行 + 深度读数
    box.classList.add("is-stage");
    cineStep(0); plug.classList.add("is-on");
    cineTone(82, .5, "sawtooth", .34);
    cineCount("cineDepth", 0, 2.4, 1500, 1, " m");
  });
  at(3800, ()=>{  // LCL 注入：液面上升 + 四项参数滚动
    plug.classList.remove("is-on"); lcl.classList.add("is-on");
    cineStep(1); cineSwell(220, 1.2);
    cineCount("cinePressure", 0, .98, 1700, 2);
    cineCount("cineTemp", 0, 22.4, 1700, 1, "℃");
    cineCount("cineDensity", 0, 100, 1700, 0, "%");
    cineCount("cineNeuro", 0, 98, 1700, 0, "%");
  });
  at(5900, ()=>{  // 神经接驳：同步率弧 0 → 98.4
    lcl.classList.remove("is-on"); sync.classList.add("is-on");
    cineStep(2); cineTone(300, .7, "sine", .3);
    cineCount("cineSyncVal", 0, 98.4, 2000, 1);
  });
  at(8200, ()=>{ sync.classList.remove("is-on"); box.classList.add("is-stage-out"); });
  at(8400, ()=>{  // 线稿层遮罩横扫
    box.classList.add("is-line"); lineart.classList.add("is-in");
    cineStep(3);
  });
  at(10300, ()=>{ // 海报层淡入（线稿随之退场）
    lineart.classList.remove("is-in");
    box.classList.remove("is-line"); box.classList.add("is-poster");
    bg.classList.add("is-in");
    cineStep(4); cineSwell(110, 1.0);
  });
  at(12000, ()=>{ // 金属字标 + 扫光
    box.classList.add("is-logo");
    cineTone(293.66, .6, "sine", .5);
    bootTimers.push(setTimeout(()=>{ if(g === cineGen) cineTone(440, .8, "sine", .32); }, 260));
  });
  at(14600, ()=>{ if(g === cineGen) finishBoot(); });
}

function runBootCine(){
  // 电影感主题固定是 UNIT-02（明日香）：登记驾驶员，finishBoot 时应用 eva-asuka 双生皮肤
  //（明日香红配色 + 线稿聊天背景 + 02 水印 + 时钟），与 eva 主题选明日香后的效果一致
  localStorage.setItem("evaPilot", "asuka");
  const box = document.getElementById("bootCine");
  const g = ++cineGen;
  cineStarted = false;
  stopCineAudio();
  box.className = "";                       // 清掉全部阶段类，防重播残留
  // 复位面板 / 读数 / 打字行 / 任务列表
  ["cinePPlug","cinePLcl","cinePSync"].forEach(id=>document.getElementById(id).classList.remove("is-on"));
  document.getElementById("cineDepth").textContent = "0.0 m";
  document.getElementById("cinePressure").textContent = "0.00";
  document.getElementById("cineTemp").textContent = "0.0";
  document.getElementById("cineDensity").textContent = "0";
  document.getElementById("cineNeuro").textContent = "0";
  document.getElementById("cineSyncVal").textContent = "0.0";
  document.getElementById("cineArc").style.strokeDashoffset = "351.86";
  document.getElementById("cineLog").textContent = "";
  document.querySelectorAll("#bootCine .cine-step").forEach(s=>s.classList.remove("is-on","is-done"));
  document.getElementById("cineGate").classList.remove("is-out");
  cancelAnimationFrame(cineDustRaf);
  cineDust(box);                            // 尘埃在起播门阶段就开始飘
}

// ================= 酒德麻衣主题 · PV 视频直播 =================
// 原理：不做 CSS 复刻，直接全屏播放 PV 视频（22.8s H.264）。
// 播完 onended 自动 finishBoot；点击/ESC 跳过由 #boot 全局 skipBoot 处理（finishBoot 内 pause 并归零视频）。
let mdGen = 0;
function runBootMd(){
  const g = ++mdGen;
  const v = document.getElementById("mdVideo");
  v.onended = () => { if(g === mdGen) finishBoot(); };
  try{ v.currentTime = 0; }catch(_){}
  const p = v.play();
  if(p && p.catch) p.catch(()=>{});   // 自动播放被策略拦截时静默；用户点击/重播时有手势，能正常起播
}

function finishBoot(){
  cdxAnimGen++;   // 杀掉可能在跑的粒子描线动画（跳过/收尾时立即停止）
  evaGen++;       // 作废 EVA 主题在跑的等高线/同步 rAF 与语音定时
  cineGen++;      // 作废 Cine 主题在跑的时间轴/打字/数字滚动
  mdGen++;        // 作废酒德麻衣主题的播放回调
  const mdVideo = document.getElementById("mdVideo");
  if(mdVideo){ mdVideo.pause(); mdVideo.currentTime = 0; }   // 停掉 PV 播放（跳过/收尾时）
  cancelAnimationFrame(evaContoursRaf);
  cancelAnimationFrame(evaSyncRaf);
  cancelAnimationFrame(cineDustRaf);
  stopEvaAudio();
  stopCineAudio();
  evaTick.clearAll();                              // Worker 计时器一并作废（点击跳过/收尾时防止后台残留回调）
  // EVA 双生皮肤：本次启动若选过驾驶员，进入聊天时整个界面换装（时钟/线稿背景/水印/横幅）
  const ep = localStorage.getItem("evaPilot");
  if(ep && EVA_PILOTS[ep]) applyEvaSkin(ep);
  bootTimers.forEach(clearTimeout); bootTimers = [];
  const boot = document.getElementById("boot");
  boot.classList.add("done");
  // 隐藏定时器同样纳入统一管理，避免与"重启动画"竞态把新动画藏掉
  bootTimers.push(setTimeout(()=>{
    boot.style.display = "none";
    // 首次启动结束后再打欢迎语，避免和聊天记录重复
    if(!document.querySelector("#msgs .row"))
      addMsg("ai", "我是小狐，毒舌但暖的那种。今天想聊点啥？", null);
  }, 700));
}
function skipBoot(e){
  // 点在控制按钮/下拉框上永不触发"点击跳过"（声音开关、跳过按钮、主题选择等）——
  // cine 主题"声音"与"跳过"按钮相邻，点偏或按钮被动画图层短暂遮挡时，误触会直接结束动画
  if(e && e.target && e.target.closest && e.target.closest("button,select,input,label")) return;
  // EVA 认证的选择/装载/舱门阶段禁止点击跳过：
  // 这三段点空白误触会直接 finishBoot 进聊天（无驾驶员→默认金色皮肤），且拖动卡片会吞掉 click 造成"点了没反应"错觉
  const eva = document.getElementById("bootEva");
  if(eva && eva.style.display === "block"){
    const p = eva.getAttribute("data-phase");
    if(p === "select" || p === "loading" || p === "handoff") return;
  }
  finishBoot();
}
function replayBoot(){ runBoot(); }

document.getElementById("inp").addEventListener("keydown", e=>{ if(e.key==="Enter") send(); });
document.getElementById("send").addEventListener("click", send);
document.getElementById("replayBtn").addEventListener("click", replayBoot);
document.getElementById("switchBtn").addEventListener("click", switchUser);
document.getElementById("boot").addEventListener("click", skipBoot);
// ESC 键跳过启动动画（同参考视频右下角"ESC 跳过"提示）
document.addEventListener("keydown", e=>{
  if(e.key === "Escape"){
    const b = document.getElementById("boot");
    if(b && b.style.display !== "none" && !b.classList.contains("done")) skipBoot();
  }
});
// 狐仙动态壁纸：视频能播放时标记 has（淡入显示）并给 body 加 videoBg（淡出静态插画）；404 则静默回退
const spiritVideo = document.getElementById("spiritVideo");
spiritVideo.addEventListener("loadeddata", ()=>{
  spiritVideo.classList.add("has");
  document.body.classList.add("videoBg");
});
// 粒子动画主题视频壁纸：同上，加载成功淡入视频、淡出静态呼吸背景；404 则保持静态回退
const codexVideo = document.getElementById("codexVideo");
codexVideo.addEventListener("loadeddata", ()=>{
  codexVideo.classList.add("has");
  document.body.classList.add("videoBg");
});
// 启动主题选择：切换后立即用新主题重播启动动画
const themeSel = document.getElementById("themeSel");
themeSel.value = bootTheme();
themeSel.addEventListener("change", ()=>{ localStorage.setItem("bootTheme", themeSel.value); runBoot(); });
// EVA 声音开关：阻止冒泡，避免触发 #boot 的"点击跳过"
document.getElementById("evaMuteBtn").addEventListener("click", e=>{
  e.stopPropagation();
  evaSound = !evaSound;
  document.getElementById("bootEva").setAttribute("data-sound", evaSound ? "on" : "off");
  document.getElementById("evaMuteBtn").textContent = evaSound ? "声音：开" : "声音：关";
  if(evaSound){ evaBgmStart(); } else { stopEvaAudio(); }
});
// 按钮上的按下不参与"首次手势补启 BGM"（pointerdown 先于 click：evaSound 还没翻转就先拉起 BGM，
// 紧接着 click 关声音又全停，徒增 ERR_ABORTED 报错）
document.getElementById("evaMuteBtn").addEventListener("pointerdown", e=>e.stopPropagation());
// 默认开声的自动播放补救：页面刚加载、无用户手势时 BGM play() 会被浏览器静默拦截，
// 首次点击/按键（boot 未结束）时重新拉起 BGM；cine 主题同理补放启动音频
function unlockBootAudio(){
  const boot = document.getElementById("boot");
  if(boot.classList.contains("done") || boot.style.display === "none") return;
  const eva = document.getElementById("bootEva");
  if(eva.style.display === "block" && evaSound && !evaBgm) evaBgmStart();
  const cine = document.getElementById("bootCine");
  if(cine.style.display === "block" && cineSound && cineStarted && (!cineAudio || cineAudio.paused)) startCineAudio();
}
document.addEventListener("pointerdown", unlockBootAudio);
document.addEventListener("keydown", unlockBootAudio);
// EVA 驾驶员卡片：点击选择 + 拖拽头像进插入栓（dsh-plugin-eva-theme 核心交互）
(function(){
  const box = document.getElementById("bootEva");
  const bay = box.querySelector(".eva-entry-bay");
  let drag = null, suppressClick = false;   // drag:{card,pid,pointerId,x,y,ghost,moved,over}
  box.querySelectorAll(".eva-pilot-card").forEach(card=>{
    card.addEventListener("pointerdown", e=>{
      if(box.getAttribute("data-phase") !== "select") return;
      drag = { card, pid: card.dataset.pilot, pointerId: e.pointerId, x: e.clientX, y: e.clientY, ghost: null, moved: false, over: false };
      try{ card.setPointerCapture(e.pointerId); }catch(_){}
    });
    card.addEventListener("click", e=>{
      e.stopPropagation();
      if(suppressClick){ suppressClick = false; return; }   // 拖动后抑制这次点击
      pickPilot(card.dataset.pilot);
    });
  });
  document.addEventListener("pointermove", e=>{
    if(!drag || drag.pointerId !== e.pointerId) return;
    if(!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 8) return;
    drag.moved = true;
    if(!drag.ghost){
      drag.ghost = document.createElement("div");
      drag.ghost.className = "eva-pilot-ghost";
      drag.ghost.style.width = drag.card.offsetWidth + "px";
      drag.ghost.style.height = drag.card.offsetHeight + "px";
      // 拖拽幻影用闭眼头像（素材已随包），随光标移动
      drag.ghost.style.backgroundImage = "url(/static/eva/" + drag.pid + "-avatar-closed-eyes.png)";
      box.appendChild(drag.ghost);
    }
    drag.ghost.style.transform = "translate(" + (e.clientX - drag.ghost.offsetWidth/2) + "px," + (e.clientY - drag.ghost.offsetHeight/2) + "px)";
    const r = bay.getBoundingClientRect();
    drag.over = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    bay.setAttribute("data-over", drag.over ? "1" : "0");
  });
  const endDrag = (commit)=>{
    if(!drag) return;
    if(drag.ghost) drag.ghost.remove();
    bay.setAttribute("data-over", "0");
    try{ drag.card.releasePointerCapture(drag.pointerId); }catch(_){}
    const pid = drag.pid, moved = drag.moved, over = drag.over;
    drag = null;
    suppressClick = commit ? moved : false;   // 仅 pointerup 后可能跟一次 click；取消/失焦不产生 click
    if(commit && moved && over) pickPilot(pid);   // 拖入插入栓 = 装载
  };
  document.addEventListener("pointerup", e=>{ if(drag && drag.pointerId === e.pointerId) endDrag(true); });
  document.addEventListener("pointercancel", e=>{ if(drag && drag.pointerId === e.pointerId) endDrag(false); });
  window.addEventListener("blur", ()=>endDrag(false));
})();
// EVA 选择页键盘 1/2 快捷选择（仅在选择阶段且 EVA 主题显示时生效）
document.addEventListener("keydown", e=>{
  const boot = document.getElementById("boot");
  if(boot.classList.contains("done")) return;
  const box = document.getElementById("bootEva");
  if(box.style.display !== "block") return;
  if(box.getAttribute("data-phase") !== "select") return;
  if(e.key === "1") pickPilot("asuka");
  else if(e.key === "2") pickPilot("rei");
});
// Cine 起播门：开始（解锁音频）/ 跳过；均阻止冒泡，避免立刻触发 #boot 的点击跳过
document.getElementById("cineStartBtn").addEventListener("click", e=>{
  e.stopPropagation(); beginCineSeq();
});
document.getElementById("cineGateSkip").addEventListener("click", e=>{
  e.stopPropagation(); finishBoot();
});
document.getElementById("cineSkipBtn").addEventListener("click", e=>{
  e.stopPropagation(); finishBoot();
});
// Cine 播放中按 ESC 跳过（起播门未开始时忽略）
document.addEventListener("keydown", e=>{
  if(e.key !== "Escape") return;
  const boot = document.getElementById("boot");
  if(boot.classList.contains("done")) return;
  const box = document.getElementById("bootCine");
  if(box.style.display !== "block" || !cineStarted) return;
  finishBoot();
});
refresh();
setInterval(refresh, 5000);
runBoot();
</script>
<script>
// ---------------- 小狐电台 · Lattice 播放器 ----------------
// 注意用 var：需要挂到 window.Fox 供前一个 script 块的事件委托调用
var Fox = (function(){
  let items = [], decoImgs = [], cur = -1, lines = [], lyricEl = null, playSeq = 0;
  const audio = new Audio();
  const $ = id => document.getElementById(id);
  const fmt = s => isFinite(s) ? Math.floor(s/60) + ":" + String(Math.floor(s%60)).padStart(2,"0") : "0:00";

  async function lib(){
    if(!items.length){
      try{
        const d = await (await fetch("/api/library")).json();
        items = d.items || []; decoImgs = d.deco || [];
      }catch(e){ items = []; }
    }
    return items;
  }

  function grad(s){ // 无封面时按歌名生成暖色渐变块
    let h = 0; for(const c of s.title) h = (h*31 + c.charCodeAt(0)) % 360;
    return "linear-gradient(135deg,hsl(" + h + ",45%,26%),hsl(" + ((h+50)%360) + ",55%,14%))";
  }
  function cover(s){ return s.cover ? "<img src='" + s.cover + "' alt='' onerror='this.remove()'>" : ""; }

  function grid(){
    // 装饰插画均匀穿插进拼贴网格（上下左右错落分布，而非堆在末尾）
    const N = items.length, D = decoImgs.length, total = N + D;
    const decoPos = new Set();
    for(let d = 1; d <= D; d++){
      let p = Math.round(d * total / (D + 1)) - 1;
      while(decoPos.has(p)) p = (p + 1) % total;   // 撞位则顺移
      decoPos.add(p);
    }
    let html = "", di = 0;
    for(let slot = 0; slot < total; slot++){
      if(decoPos.has(slot)){                        // 装饰位：纯插画，不可点
        html += "<div class='fpTile deco'><img src='" + decoImgs[di++] + "' alt=''><span></span></div>";
      }else{
        const i = slot - di, s = items[i];
        html += "<div class='fpTile" + (i===cur?" on":"") + "' data-i='" + i + "' title='" + esc(s.title) + "'>"
             + (s.cover ? cover(s) : "<div style='width:100%;height:100%;background:" + grad(s) + "'></div>")
             + "<span>" + esc(s.title) + "</span></div>";
      }
    }
    $("foxLattice").innerHTML = html;
    syncUI();
  }

  function lyrics(s){
    lines = (s.lyrics && s.lyrics.length) ? s.lyrics.map(l => ({t:l.t, text:l.text})) : [];
    if(lines.length && s.duration){
      // 无时间戳的纯文本歌词：按曲长均匀分布（演示用近似同步）
      let unset = lines.filter(l => l.t === null);
      if(unset.length === lines.length)
        lines.forEach((l,i) => l.t = (i + 1) * s.duration / (lines.length + 2));
    }
    const box = $("foxLyrics");
    box.innerHTML = lines.length
      ? lines.map((l,i) => "<div class='fpLine' data-i='" + i + "'>" + esc(l.text) + "</div>").join("")
      : "<div class='fpLine on'>♪ " + (s.note ? esc(s.note) : "纯音乐，请欣赏～") + "</div>";
    box.scrollTop = 0;   // 切歌后回到顶部：清掉上一首遗留的滚动位置
  }

  function lyricTick(t){
    if(!lines.length) return;
    let idx = -1;
    for(let i=0;i<lines.length;i++){ if(lines[i].t !== null && lines[i].t <= t) idx = i; }
    const box = $("foxLyrics"), el = box.children[idx];
    if(el && el !== lyricEl){
      if(lyricEl) lyricEl.classList.remove("on");
      // Folia 式远近层次：距当前句越远越淡越虚
      for(let i=0;i<box.children.length;i++){
        const c = box.children[i], d = Math.abs(i - idx);
        c.classList.toggle("near", d === 1);
        c.classList.toggle("far", d >= 3);
      }
      lyricEl = el; el.classList.add("on");
      el.classList.remove("far");
      box.scrollTop = el.offsetTop - box.clientHeight/2 + el.offsetHeight/2;
    }
  }

  function syncUI(){  // 播放状态 -> 底栏按钮 + 当前封面上的 ⏸/▶ 角标 + 宠物联动
    const playing = !!audio.src && !audio.paused && !audio.ended;
    $("foxPlay").textContent = playing ? "⏸" : "▶";
    const tile = document.querySelector(".fpTile.on");
    if(tile) tile.classList.toggle("paused", !playing);
    document.dispatchEvent(new CustomEvent("fox-audio", {detail:{playing:playing}}));
  }
  audio.addEventListener("play", syncUI);
  audio.addEventListener("pause", syncUI);

  async function play(i){
    if(!items.length) return;
    cur = ((i % items.length) + items.length) % items.length;
    const my = ++playSeq;                 // 序号守卫：快速连点时丢弃过期响应
    const s = items[cur];
    $("foxTitle").textContent = "《" + s.title + "》";
    $("foxArtist").textContent = s.artist + (s.tags.length ? " · " + s.tags.join("/") : "");
    $("foxNote").textContent = s.note ? "小狐私评：" + s.note : "";
    $("foxBg").style.backgroundImage = s.cover ? "url(" + s.cover + ")" : "none";
    lyricEl = null; lyrics(s); grid();
    const url = "/api/audio?file=" + encodeURIComponent(s.file);
    try{
      // 整体取回再播：切歌不再中断旧请求流，控制台不会有 ERR_ABORTED
      const blob = await (await fetch(url)).blob();
      if(my !== playSeq) return;
      if(audio.src.startsWith("blob:")){
        const old = audio.src;              // 延迟释放：立即 revoke 会触发控制台 ERR_ABORTED
        setTimeout(function(){ URL.revokeObjectURL(old); }, 8000);
      }
      audio.src = URL.createObjectURL(blob);
    }catch(e){
      if(my !== playSeq) return;
      audio.src = url;                    // 兜底：直接流式播放
    }
    audio.play().catch(function(){});
  }

  function open(i){
    $("fox").classList.add("open");
    lib().then(function(){
      grid();
      if(typeof i === "number") play(i);
      else if(cur >= 0) grid();
    });
  }

  // ---- 事件 ----
  $("foxClose").onclick = () => $("fox").classList.remove("open");
  $("foxPlay").onclick = function(){
    if(cur < 0){ play(0); return; }
    if(audio.paused) audio.play().catch(function(){}); else audio.pause();
  };
  $("foxNext").onclick = () => play(cur+1);
  $("foxPrev").onclick = () => play(cur-1);
  $("foxLattice").onclick = function(e){
    const t = e.target.closest(".fpTile");
    if(!t || t.classList.contains("deco")) return;
    const i = +t.dataset.i;
    if(i === cur){  // 点当前封面 = 播放/暂停开关
      if(audio.paused) audio.play().catch(function(){}); else audio.pause();
    } else play(i);
  };
  $("foxLyrics").onclick = function(e){ const l = e.target.closest(".fpLine"); if(l && lines[+l.dataset.i] && lines[+l.dataset.i].t !== null) audio.currentTime = lines[+l.dataset.i].t; };
  $("foxProg").onclick = function(e){
    if(!isFinite(audio.duration)) return;
    const r = this.getBoundingClientRect();
    audio.currentTime = (e.clientX - r.left) / r.width * audio.duration;
  };
  audio.addEventListener("timeupdate", function(){
    $("foxTime").textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
    $("foxProgFill").style.width = (audio.currentTime / (audio.duration||1) * 100) + "%";
    lyricTick(audio.currentTime);
  });
  audio.addEventListener("ended", () => play(cur+1));  // 自动连播 = 队列拼贴的队列语义
  document.addEventListener("keydown", function(e){ if(e.key === "Escape") $("fox").classList.remove("open"); });

  return { open: open, play: play,
    playByTitle: function(title){
      lib().then(function(){
        const i = items.findIndex(s => s.title === title || title.indexOf(s.title) >= 0 || s.title.indexOf(title) >= 0);
        open(i >= 0 ? i : 0);
        if(i >= 0) play(i);
      });
    } };
})();

// ---------------- 白龙酱 · 网页宠物（透明 WebM + 状态机联动 + 拖动 + 点击反应） ----------------
// 素材：bailong-desktop-pet v0.5.1 发布包（github.com/jingh12312-rgb/bailong-desktop-pet）
// 台词沿用其素材清单的官方台词；动画切换/状态联动/拖拽行为为本项目原创实现
var Pet = (function(){
  const pet = document.getElementById("pet"), bubble = document.getElementById("petBubble"),
        vid = document.getElementById("petVid"), P = "/static/pet/";
  // 语义表（对应素材清单.json）：动作 -> 文件
  const MOOD_FILE = { crisis: "26.webm",      // 逆鳞信任：守护陪伴
                      empathy: "idle04.webm", // 贴贴枕头：安静安抚
                      sing:    "05.webm",     // 得意摇摆：放歌打节拍
                      happy:   "20.webm",     // 比心
                      idle:    null };        // idle -> 待机轮换
  const IDLE_LOOP = ["idle.webm", "idle2.webm"];
  const IDLE_ONCE = [ ["idle03.webm","翻绘本中……"], ["idle05.webm","玩掌机，别打扰我"], ["idle06.webm","贴尾巴嘿嘿"],
                      ["14.webm","哈啊……借桌角打个小盹。"], ["25.webm","呼——小龙吐息！只烤棉花糖。"] ];
  const TAPS = [ ["08.webm","给主人一个小小的龙龙抱抱。"], ["09.webm","才没有一直等主人……就一小会儿。"],
                 ["13.webm","主人别急！这个坏问题，我要拆成小块解掉！"], ["17.webm","主人，这块饼干……是思考用的燃料！"],
                 ["25.webm","呼——这是小龙吐息！只烤棉花糖，不烤主人。"], ["18.webm","完成啦！给主人和我各贴一颗小星星！"],
                 ["20.webm","今日份喜欢，已经送到主人的桌面啦。"] ];
  let mood = "idle", playing = false, busy = false, idleIdx = 0,
      bubbleTimer = null, noteTimer = null, idleTimer = null;

  function say(t, ms){
    bubble.textContent = t; bubble.classList.add("show");
    clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(function(){ bubble.classList.remove("show"); }, ms || 3200);
  }
  function play(f, loop){                       // 切换动画段
    vid.onended = null;
    vid.loop = !!loop;
    const src = P + f;
    if(vid.src !== location.origin + src){ vid.src = src; }
    vid.play().catch(function(){});
  }
  function curMood(){                           // 优先级：危机守护 > 唱歌 > 轮询情绪
    if(mood === "crisis") return "crisis";
    if(playing) return "sing";
    return mood;
  }
  function base(){                              // 回到"当前情绪"的基础循环动画
    busy = false;
    const m = curMood();
    if(m !== "idle") return play(MOOD_FILE[m], true);
    idleIdx = (idleIdx + 1) % IDLE_LOOP.length;
    play(IDLE_LOOP[idleIdx], true);
  }
  function once(f, line){                       // 播一段一次性动作，播完自动回基础动画
    busy = true;
    play(f, false);
    vid.onended = base;
    if(line) say(line);
  }
  // 空闲小剧场：待机时每隔一阵随机演一段（翻绘本/玩掌机/打盹……）
  idleTimer = setInterval(function(){
    if(mood === "idle" && !playing && !busy && Math.random() < .6){
      const it = IDLE_ONCE[Math.floor(Math.random() * IDLE_ONCE.length)];
      once(it[0], Math.random() < .5 ? it[1] : null);
    }
  }, 14000);
  function notes(on){                           // 唱歌时飘 ♪ 音符
    clearInterval(noteTimer); noteTimer = null;
    if(on) noteTimer = setInterval(function(){
      const n = document.createElement("span");
      n.className = "petNote"; n.textContent = Math.random() < .5 ? "♪" : "♫";
      n.style.left = (52 + Math.random() * 46) + "px";
      n.style.bottom = (58 + Math.random() * 22) + "px";
      pet.appendChild(n);
      setTimeout(function(){ n.remove(); }, 1700);
    }, 850);
  }
  // 轮询 Agent 状态：危机守护 -> 逆鳞守护动画；共情倾听 -> 贴贴枕头；幽默闲聊 -> 比心
  setInterval(async function(){
    try{
      const uidEl = document.querySelector(".uid input");
      const uid = (uidEl && uidEl.value || "demo").trim() || "demo";
      const s = await (await fetch("/api/state?user_id=" + encodeURIComponent(uid))).json();
      const sk = s.last_skill || "";
      mood = s.crisis_mode ? "crisis"
        : (sk.indexOf("共情") >= 0 || sk.indexOf("倾听") >= 0) ? "empathy"
        : (sk.indexOf("幽默") >= 0 || sk.indexOf("闲聊") >= 0) ? "happy" : "idle";
      if(s.crisis_mode && curMood() === "crisis" && !busy){ say("别怕，我一直都在。", 5000); }
      if(!busy) base();
      notes(playing && mood !== "crisis");
    }catch(e){}
  }, 5000);
  // 播放器联动（syncUI 派发的自定义事件）：放歌 -> 得意摇摆
  document.addEventListener("fox-audio", function(e){
    playing = !!e.detail.playing;
    if(playing && mood !== "crisis"){ say("跟着节奏摇～♪", 2500); if(!busy) base(); }
    notes(playing && mood !== "crisis");
  });
  // 拖动（拖动中播 drag.webm，松手播 landing.webm）+ 点击卖萌
  let sx = 0, sy = 0, ox = 0, oy = 0, moved = false, dragging = false;
  pet.addEventListener("pointerdown", function(e){
    dragging = true; moved = false; sx = e.clientX; sy = e.clientY;
    const r = pet.getBoundingClientRect(); ox = r.left; oy = r.top;
    pet.setPointerCapture(e.pointerId);
  });
  pet.addEventListener("pointermove", function(e){
    if(!dragging) return;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if(Math.abs(dx) + Math.abs(dy) > 6){
      if(!moved){ moved = true; play("drag.webm", true); }   // 拖拽挣扎动画
      pet.style.left = Math.max(0, ox + dx) + "px";
      pet.style.top = Math.max(0, oy + dy) + "px";
      pet.style.bottom = "auto";
    }
  });
  function petDrop(){
    dragging = false;
    if(moved){ once("landing.webm"); }                       // 落地动画 -> 回基础动画
    else petTap();
  }
  function petTap(){                                         // 点击：随机一段互动动画 + 官方台词
    const now = Date.now();
    if(now - petTap._last < 500) return;                     // 与 pointerup 去重
    petTap._last = now;
    const t = TAPS[Math.floor(Math.random() * TAPS.length)];
    once(t[0], t[1]);
  }
  pet.addEventListener("pointerup", petDrop);
  pet.addEventListener("click", function(){ if(petTap._last && Date.now() - petTap._last < 500) return; if(!dragging) petTap(); });
  return { say: say, once: once };
})();
Pet.say("龙酱上线啦～点我试试看");
</script>
</body>
</html>"""


# ---------------- 路由 ----------------

@app.route("/")
def index():
    # no-store：页面HTML含全部内联CSS/JS且迭代频繁，禁止浏览器缓存，避免拿到旧版页面
    resp = app.make_response(INDEX_HTML)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "消息不能为空"}), 400
    agent = get_agent((data.get("user_id") or "demo").strip())
    return jsonify(agent.handle(text))


@app.route("/api/state")
def api_state():
    agent = get_agent((request.args.get("user_id") or "demo").strip())
    return jsonify(agent.get_state())


@app.route("/api/logs")
def api_logs():
    uid = (request.args.get("user_id") or "demo").strip()
    return jsonify(read_recent(n=40, user_id=uid))


# ---------------- 网页播放器（Lattice 队列拼贴 + 歌词浮现） ----------------

@app.route("/image/<path:name>")
def image_file(name):
    """image/ 文件夹里的封面插画"""
    from flask import send_from_directory
    return send_from_directory(IMAGE_DIR, name, max_age=86400)


@app.route("/api/library")
def api_library():
    """曲库列表（含封面/歌词/时长，懒提取缓存）；deco 为未用作封面的装饰插画"""
    items = []
    for s in load_library():
        m = extract_media(s)
        items.append({"file": s["file"], "title": s["title"], "artist": s["artist"],
                      "tags": s["tags"], "note": s["note"],
                      "cover": s["cover"] or m["cover"],
                      "duration": m["duration"], "lyrics": m["lyrics"]})
    used = {i["cover"] for i in items if i["cover"]}
    try:
        deco = ["/image/" + f for f in sorted(os.listdir(IMAGE_DIR))
                if f.lower().endswith((".jpg", ".png")) and not f.startswith("头像")
                and "/image/" + f not in used]
    except OSError:
        deco = []
    return jsonify({"items": items, "deco": deco})


@app.route("/api/audio")
def api_audio():
    """音频文件流（conditional=True 支持 Range，可拖进度条）"""
    from flask import send_file
    fn = os.path.basename(request.args.get("file", ""))  # basename 防目录穿越
    path = os.path.join(MUSIC_DIR, fn)
    if not fn or not os.path.isfile(path):
        return jsonify({"error": "歌曲不存在"}), 404
    mime = "audio/flac" if fn.lower().endswith(".flac") else "audio/mpeg"
    return send_file(path, mimetype=mime, conditional=True)


if __name__ == "__main__":
    print("小狐已启动：打开 http://127.0.0.1:5000 开始对话")
    app.run(host="127.0.0.1", port=5000, debug=False)
