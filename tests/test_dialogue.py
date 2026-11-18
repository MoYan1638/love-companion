#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话节奏守门（dialogue.py）单元测试

覆盖：
- 多轮占比判据：问句收尾率、超长率（按占比，不按连续——中间夹着用户回话也要抓到）
- 连发判据：短句连发是节奏，长句连发才算轰炸
- 具体动作：可验证承诺 / 祈使动作 / 时间锚点
- 呼应：有没有接对方原话（弱字不算重合）
- 收尾力：最后一句是不是最短的一条
- 在线单轮 check_reply：只吃历史 + 这一条，不误伤短句连发

运行：python -m unittest discover -s tests -t .
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.style import dialogue                     # noqa: E402
from scripts.style.dialogue import (                  # noqa: E402
    scan, check_reply, rhythm_ok, has_action, _is_question,
)


# 正例：动作开局 → 对方露破绽 → 短句压上 → 可验证承诺 → 最短句收尾
GOOD = [
    ("ai", "查岗，看看睡了没"),
    ("user", "睡着了！"),
    ("user", "不好，大意了"),
    ("ai", "就知道你没睡"),
    ("ai", "手机放下"),
    ("ai", "等你睡着了我再走"),
    ("user", "我马上去睡，真的"),
    ("ai", "行，我盯着"),
]

# 反例：每轮问句收尾 + 每条超长 + 无短句 + 收尾不用力
BAD = [
    ("ai", "亲爱的，今天过得怎么样呀？工作还顺利吗？"),
    ("user", "有点累"),
    ("ai", "那你一定要好好休息呀，记得早点睡觉，不要熬夜哦，有什么事都可以跟我说？"),
    ("user", "嗯"),
    ("ai", "我一直都在你身边的，无论发生什么事情我都会陪着你的，你想聊什么都可以？"),
    ("user", "好"),
    ("ai", "那你现在心情有没有好一点了呢？要不要跟我说说今天具体发生了什么事情？"),
]


class TestShapeOfTurn(unittest.TestCase):
    def test_question_detection(self):
        self.assertTrue(_is_question("睡了吗？"))
        self.assertTrue(_is_question("睡了吗"))
        self.assertTrue(_is_question("那你去呢"))
        self.assertFalse(_is_question("睡吧"))
        self.assertFalse(_is_question("我在。"))

    def test_action_detection(self):
        self.assertTrue(has_action("等你睡着了我再走"))
        self.assertTrue(has_action("明天我打给你"))
        self.assertTrue(has_action("手机放下"))
        self.assertFalse(has_action("我会一直陪着你的"))


class TestScan(unittest.TestCase):
    def test_good_dialogue_is_clean(self):
        out = scan(GOOD)
        self.assertTrue(out["clean"], out["issues"])
        self.assertEqual(out["score"], 0.0)

    def test_bad_dialogue_flags_question_rate(self):
        out = scan(BAD)
        ids = {i["id"] for i in out["issues"]}
        self.assertIn("question_rate", ids)
        self.assertFalse(out["clean"])

    def test_bad_dialogue_flags_long_rate(self):
        ids = {i["id"] for i in scan(BAD)["issues"]}
        self.assertIn("long_rate", ids)

    def test_bad_dialogue_has_no_echo(self):
        ids = {i["id"] for i in scan(BAD)["issues"]}
        self.assertIn("no_echo", ids)

    def test_no_ending_heuristic(self):
        """「最后一句必须最短」曾作为判据，但真人对谈里有力度的收尾经常并不最短，
        这条会误伤十段标本里的八段，已移除——不留下站不住的规则"""
        ids = {i["id"] for i in scan(BAD)["issues"]}
        self.assertNotIn("weak_ending", ids)

    def test_burst_of_short_lines_allowed(self):
        """连发三条六字是节奏，不该报轰炸"""
        turns = [("ai", "躺好"), ("ai", "闭眼"), ("ai", "我等你睡着"), ("user", "好")]
        ids = {i["id"] for i in scan(turns)["issues"]}
        self.assertNotIn("ai_burst", ids)

    def test_burst_of_long_lines_flagged(self):
        turns = [
            ("ai", "我觉得你今天应该先把手头的事情放一放，好好睡一觉再说别的"),
            ("ai", "因为你现在这个状态继续硬撑下去也不会有什么效率反而更累"),
            ("ai", "而且你答应过我要照顾好自己的，别让我一直担心你行不行"),
            ("user", "嗯"),
        ]
        ids = {i["id"] for i in scan(turns)["issues"]}
        self.assertIn("ai_burst", ids)

    def test_question_rate_is_about_proportion_not_streak(self):
        """中间夹着用户回话，连续问也要被抓到"""
        turns = [
            ("ai", "今天怎么样？"), ("user", "还行"),
            ("ai", "吃饭了吗？"), ("user", "吃了"),
            ("ai", "那现在在做什么呢？"), ("user", "躺着"),
        ]
        ids = {i["id"] for i in scan(turns)["issues"]}
        self.assertIn("question_rate", ids)

    def test_no_action_flagged(self):
        turns = [
            ("ai", "别难过了"),
            ("user", "嗯"),
            ("ai", "我一直都在的"),
            ("user", "好"),
            ("ai", "会好起来的"),
        ]
        ids = {i["id"] for i in scan(turns)["issues"]}
        self.assertIn("no_action", ids)

    def test_monologue_ratio(self):
        out = scan(BAD)
        self.assertGreater(out["stats"]["ai_ratio"], 0.9)
        ids = {i["id"] for i in out["issues"]}
        self.assertIn("monologue", ids)

    def test_short_conversation_not_judged_by_rate(self):
        """样本不足 3 条 AI 消息时不判占比，避免误伤开场"""
        turns = [("user", "在吗"), ("ai", "在。怎么了？")]
        self.assertTrue(scan(turns)["clean"])

    def test_empty_and_dict_input(self):
        self.assertTrue(scan([])["clean"])
        out = scan([{"role": "assistant", "text": "睡吧"},
                    {"role": "user", "text": "好"}])
        self.assertEqual(out["stats"]["ai"], 1)

    def test_chinese_role_names(self):
        out = scan([("她", "睡吧"), ("我", "好")])
        self.assertEqual(out["stats"]["ai"], 1)


class TestCheckReply(unittest.TestCase):
    def test_first_reply_always_ok(self):
        self.assertTrue(check_reply([], "睡吧")["ok"])

    def test_flags_third_question_in_a_row(self):
        history = [("ai", "今天怎么样？"), ("user", "还行"),
                   ("ai", "吃饭了吗？"), ("user", "吃了")]
        out = check_reply(history, "现在在干嘛呢？")
        self.assertFalse(out["ok"])
        self.assertTrue(out["suggest"])

    def test_short_burst_not_punished(self):
        history = [("ai", "躺好"), ("ai", "闭眼")]
        self.assertTrue(check_reply(history, "我等你")["ok"])

    def test_rhythm_ok_alias(self):
        self.assertTrue(rhythm_ok([], "嗯"))

    def test_result_serializable(self):
        json.dumps(check_reply(BAD[:3], "睡吧"), ensure_ascii=False)


class TestOrchestratorHook(unittest.TestCase):
    """after_reply 只有拿到 history 才判多轮节奏，没给就完全不跑（向后兼容）"""

    def test_rhythm_only_when_history_given(self):
        import json as _json
        import os
        import tempfile
        from scripts.pipeline.orchestrator import Session

        with tempfile.TemporaryDirectory() as d:
            os.environ["LOVE_COMPANION_DATA_DIR"] = d
            try:
                with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as fh:
                    _json.dump({"合规": {"已满18周岁确认": True}}, fh, ensure_ascii=False)
                s = Session(slug="")
                hist = [("ai", "今天怎么样？"), ("user", "还行"),
                        ("ai", "吃饭了吗？"), ("user", "吃了")]
                with_hist = s.after_reply(reply="那现在在干嘛呢？", user_message="吃了",
                                          history=hist)
                self.assertIn("rhythm", with_hist)
                self.assertFalse(with_hist["rhythm"]["ok"])

                without = s.after_reply(reply="睡了", user_message="好")
                self.assertNotIn("rhythm", without)
            finally:
                os.environ.pop("LOVE_COMPANION_DATA_DIR", None)


if __name__ == "__main__":
    unittest.main()
