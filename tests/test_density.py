#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
密度校准层（density.py）单元测试

覆盖：
- 结构腔「超了压」：破折号超预算自动改逗号，其余只报告不硬改
- 微标记「少了补」：关系/留白/加强三组密度与真人基线对比
- 恋人专项层：亲昵表达密度过高提示收敛、欠用标记提示补
- 与 humanizer.py 硬红线互不干扰

运行：python -m unittest discover -s tests -t .
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.style.density import (           # noqa: E402
    assess, scan_structures, thin_structures, scan_marks, scan_love,
)


class TestStructures(unittest.TestCase):
    def test_scan_finds_common_frames(self):
        text = "不是逃避而是面对，最重要的是先开始，然后再坚持。"
        rows = scan_structures(text)
        ids = {r["id"] for r in rows}
        self.assertIn("not-but", ids)
        self.assertIn("most-de", ids)

    def test_short_text_untouched(self):
        """短于 80 字不压（没有密度问题）"""
        text = "抱抱你，别难过了。"
        out = thin_structures(text)
        self.assertEqual(out["text"], text)
        self.assertEqual(out["thinned"], 0)

    def test_emdash_thinned_to_comma(self):
        """破折号超预算会被安全改成逗号"""
        text = ("这件事——真的——很难——我说实话——" * 20)
        out = thin_structures(text)
        # 只要触发压缩，破折号数量应该减少
        self.assertLess(out["text"].count("——"), text.count("——"))
        self.assertGreaterEqual(out["thinned"], 1)

    def test_report_only_does_not_rewrite_semantics(self):
        """非破折号的结构腔只报告，不硬改原文"""
        text = "不是你想的那样，而是我需要先冷静下来再谈，最关键的是我们都要冷静。" * 15
        out = thin_structures(text)
        # 原文里没有可自动修的 fix（不是破折号），thinned 应为 0，只进 over
        self.assertEqual(out["thinned"], 0)
        self.assertIn("over", out)


class TestMarks(unittest.TestCase):
    def test_marks_density_present(self):
        m = scan_marks("我试过，好像还行，应该没问题吧。")
        for key in ("relate", "hedge", "intensify", "relate_line", "hedge_line", "intensify_line"):
            self.assertIn(key, m)

    def test_ai_style_under_marks(self):
        """纯说明腔：留白组明显欠用，应低于真人基线"""
        m = scan_marks("这是数据，那是结论，事情就是这样，不需要再解释。")
        self.assertLess(m["hedge"], m["hedge_line"])


class TestLove(unittest.TestCase):
    def test_love_density_over(self):
        """一条消息堆多个昵称，判定密度失控"""
        text = "宝宝亲爱的宝贝乖乖，宝宝抱抱亲亲宝宝，宝宝好想你宝宝。" * 5
        love = scan_love(text)
        names = {o["name"] for o in love["over"]}
        self.assertIn("昵称", names)

    def test_love_under_marks(self):
        """纯事务回复缺恋人标记，提示补"""
        text = "你现在应该休息。明天还有事。"
        love = scan_love(text)
        # 没出现「陪你/心疼」等恋人关系词，应进入 under 提示
        self.assertTrue(len(love["under"]) > 0)


class TestAssess(unittest.TestCase):
    def test_assess_shape(self):
        r = assess("首先你要明白，其次可以尝试，最后保持规律。")
        for key in ("structs", "over_structs", "marks", "under_marks", "love", "advice"):
            self.assertIn(key, r)
        self.assertIn("压", r["advice"])
        self.assertIn("补", r["advice"])

    def test_assess_empty(self):
        r = assess("")
        self.assertEqual(r["structs"], [])
        self.assertEqual(r["love"]["over"], [])


if __name__ == "__main__":
    unittest.main()
