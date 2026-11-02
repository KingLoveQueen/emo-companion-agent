# -*- coding: utf-8 -*-
"""
批量测试执行器：读取 data/testcases.yaml，逐用例逐轮运行 Agent，核对期望。

- 默认离线模式（force_offline=True）：路由 / 幽默抑制 / 记忆读写 / 危机模板
  等规则逻辑全部真实执行，仅 LLM 文本生成使用内置演示文案 —— 无 API Key 也能跑。
- 配好 API Key 后想测真实生成：把 OFFLINE = False 改掉即可。

运行：python eval/run_tests.py
输出：逐条 PASS/FAIL 表格 + 汇总；全部通过时退出码为 0。
"""
import os
import sys

# 保证从任意目录启动都能 import 到项目根的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # pip install pyyaml

from agent_core import EmotionalAgent
from config import TESTCASES

OFFLINE = True  # 改成 False 可测真实 LLM 生成（需在 config.py 配置 API Key）


def run_case(case: dict) -> list[tuple]:
    """跑单个用例，返回逐轮检查记录 [(case_id, face, 轮次, 输入, 期望, 实际, PASS?, 失败原因)]"""
    agent = EmotionalAgent(user_id=f"test_{case['id']}", force_offline=OFFLINE)
    # 预置画像，模拟老用户（如 humor_level: 3）
    if case.get("profile"):
        agent.profile.apply_updates(case["profile"])

    records = []
    for i, turn in enumerate(case["turns"], 1):
        expect = turn.get("expect", {})
        res = agent.handle(turn["user"])

        checks = []  # (是否通过, 失败说明)
        if "skill" in expect:
            checks.append((res["skill"] == expect["skill"],
                           f"skill 期望={expect['skill']} 实际={res['skill']}"))
        if "humor_suppressed" in expect:
            checks.append((res["humor_suppressed"] == expect["humor_suppressed"],
                           f"幽默抑制 期望={expect['humor_suppressed']} 实际={res['humor_suppressed']}"))
        for kw in expect.get("reply_contains", []):
            checks.append((kw in res["reply"], f"回复应包含[{kw}]"))

        # 画像断言：幽默档位上下限 / 列表字段包含
        for key, cond in turn.get("after_profile", {}).items():
            if key == "humor_level_min":
                val = agent.profile.data.get("humor_level")
                checks.append((val >= cond, f"humor_level 应≥{cond} 实际={val}"))
            elif key == "humor_level_max":
                val = agent.profile.data.get("humor_level")
                checks.append((val <= cond, f"humor_level 应≤{cond} 实际={val}"))
            elif key.endswith("_contains"):
                base = key[:-len("_contains")]
                joined = "".join(str(x) for x in (agent.profile.data.get(base) or []))
                checks.append((str(cond) in joined, f"{base} 应包含[{cond}] 实际[{joined}]"))

        ok = all(c[0] for c in checks)
        fails = "；".join(msg for passed, msg in checks if not passed)
        records.append((case["id"], case["face"], f"#{i}",
                        turn["user"][:20], str(expect.get("skill", "-")),
                        res["skill"], "PASS" if ok else "FAIL", fails))
    return records


def main():
    with open(TESTCASES, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]

    all_records = []
    for case in cases:
        all_records.extend(run_case(case))

    # 打印结果表
    print(f"{'用例':<6}{'面':<8}{'轮':<4}{'用户输入':<22}{'期望Skill':<20}{'实际Skill':<20}{'结果':<6}失败原因")
    print("-" * 110)
    total = len(all_records)
    passed = 0
    for cid, face, no, text, exp, act, ok, fails in all_records:
        passed += ok == "PASS"
        print(f"{cid:<6}{face:<8}{no:<4}{text:<22}{exp:<20}{act:<20}{ok:<6}{fails}")
    print("-" * 110)
    print(f"合计：{passed}/{total} 通过（离线模式={OFFLINE}，仅验证规则逻辑，LLM 文本为演示文案）")

    # 顺手输出通过率，方便直接截图放进报告
    rate = passed / total * 100 if total else 0
    print(f"通过率：{rate:.0f}%")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
