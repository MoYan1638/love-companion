#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
care 话术拼接回归测试

这三类问题都只在「模板 + 声线 + 依恋后缀」三层拼起来之后才出现，
单测每个函数都测不到，所以单独成文件钉住：

1. 叠句：主体已经说了「我在」，后缀又接一遍「我在，看到就回你」
2. 标点错位：句中问号被当成追问换成了句号（「小美。有点想你了」像在生气）
3. 一坨：三条话术糊成一条，微信里没人一次发三句

运行：python -m unittest discover -s tests -t .
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.care import templates as t              # noqa: E402


class TestTailStitching(unittest.TestCase):
    def test_no_duplicated_wo_zai(self):
        """「我在」只留一次"""
        out = t.apply_attachment("别熬了，闭上眼睛，我在。", "焦虑型", seed=0)
        self.assertEqual(out.count("我在"), 1, out)
        self.assertIn("我在，看到就回你", out)

    def test_body_kept_when_tail_arrives(self):
        out = t.apply_attachment("别熬了，闭上眼睛，我在。", "恐惧型", seed=0)
        self.assertIn("闭上眼睛", out)
        self.assertIn("我在，但你不用马上回", out)

    def test_all_templates_all_attachments_clean(self):
        """全模板 × 全依恋，不允许出现 。。 / ，。 / 前导标点"""
        for kind, pool in t.TEMPLATES.items():
            for tpl in pool:
                base = tpl.format(nick="小美", detail="你说过想去看海",
                                  topic="你说过想去看海")
                for att in t.ATTACHMENT_TWEAK:
                    out = t.apply_attachment(base, att, 0)
                    self.assertNotIn("。。", out, f"{kind}/{att}: {out}")
                    self.assertNotIn("，。", out, f"{kind}/{att}: {out}")
                    self.assertFalse(out.startswith(("，", "？", "。")),
                                     f"{kind}/{att}: {out}")


class TestQuestionMark(unittest.TestCase):
    def test_mid_sentence_question_becomes_comma(self):
        out = t.apply_attachment("小美？有点想你了。", "焦虑型", seed=0)
        self.assertIn("小美，有点想你了", out)
        self.assertNotIn("小美。", out)

    def test_trailing_question_becomes_full_stop(self):
        out = t.apply_attachment("今天累不累？", "焦虑型", seed=1)
        self.assertIn("今天累不累。", out)

    def test_no_leading_question_with_empty_nick(self):
        out = t.render("久未联系", nickname="", detail="", attachment="焦虑型", seed=0)
        self.assertFalse(out.startswith(("？", "?")))
        self.assertTrue(out)


class TestSplitMessages(unittest.TestCase):
    def test_returns_several_parts(self):
        out = t.render_messages("低落陪伴", nickname="小美", detail="今天加班很累吧", seed=2)
        self.assertIsInstance(out, list)
        self.assertGreaterEqual(len(out), 1)

    def test_tail_stays_in_last_part(self):
        """依恋后缀必须留在最后一条，不能被拆掉"""
        parts = t.render_messages("深夜晚安", nickname="小美", max_parts=2,
                                  attachment="焦虑型", seed=0)
        self.assertTrue(any("我在，看到就回你" in p for p in parts[-1:]), parts)

    def test_max_parts_respected(self):
        parts = t.split_messages("先别说话。靠一下。我在。", max_parts=2)
        self.assertEqual(len(parts), 2)
        self.assertIn("我在", parts[-1])

    def test_unknown_kind_gives_empty_list(self):
        self.assertEqual(t.render_messages("不存在的类型", nickname="小美"), [])

    def test_empty_text(self):
        self.assertEqual(t.split_messages(""), [])


if __name__ == "__main__":
    unittest.main()
