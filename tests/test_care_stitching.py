#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
care 话术拼接回归测试

这三类问题都只在「模板 + 声线 + 依恋后缀」三层拼起来之后才出现，
单测每个函数都测不到，所以单独成文件钉住：

1. 叠句：主体已经说了「我在」，后缀又接一遍「我在 看到就回你」
2. 标点错位：句中问号被当成追问处理，或删标点后留一地对不齐的空格
3. 一坨：三条话术糊成一条，微信里没人一次发三句

标点口径以 `references/reply-rules.md` 第 6 条为准：不留断句标点，句子之间用空格。

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
        self.assertIn("我在 看到就回你", out)

    def test_body_kept_when_tail_arrives(self):
        out = t.apply_attachment("别熬了，闭上眼睛，我在。", "恐惧型", seed=0)
        self.assertIn("闭上眼睛", out)
        self.assertIn("我在 但你不用马上回", out)

    def test_all_templates_all_attachments_clean(self):
        """全模板 × 全依恋：不允许出现任何断句标点（第 6 条）"""
        for kind, pool in t.TEMPLATES.items():
            for tpl in pool:
                base = tpl.format(nick="小美", detail="你说过想去看海",
                                  topic="你说过想去看海")
                for att in t.ATTACHMENT_TWEAK:
                    out = t.apply_attachment(base, att, 0)
                    bad = [c for c in out if c in t._BREAK_PUNCT]
                    self.assertEqual(bad, [], f"{kind}/{att}: {out}")
                    self.assertNotIn("  ", out, f"{kind}/{att}: {out}")
                    self.assertFalse(out.startswith((" ", "，", "？", "。")),
                                     f"{kind}/{att}: {out}")

    def test_render_never_emits_break_punct(self):
        """最后一米：render 出来的整句也不能帶标点（模板干净但拼接环节可能添）"""
        for kind in t.TEMPLATES:
            for att in t.ATTACHMENT_TWEAK:
                for pref in ("", "短"):
                    out = t.render(kind, nickname="小美", detail="今天加班很累吧",
                                   attachment=att, length_pref=pref, seed=3)
                    bad = [c for c in out if c in t._BREAK_PUNCT]
                    self.assertEqual(bad, [], f"{kind}/{att}/{pref}: {out}")

    def test_short_pref_keeps_a_name_plus_one_sentence(self):
        """长度偏好=短 不能只剩一个称呼"""
        out = t.render("低落陪伴", nickname="小美", detail="今天加班很累吧",
                       length_pref="短", seed=2)
        self.assertTrue(out.startswith("小美 "), out)
        self.assertGreater(len(out.split()), 1, out)


class TestQuestionMark(unittest.TestCase):
    def test_mid_sentence_question_becomes_space(self):
        """句中的问号是呼唤，不是追问——按第 6 条改空格，不要改成句号（像在生气）"""
        out = t.apply_attachment("小美？有点想你了。", "焦虑型", seed=0)
        self.assertIn("小美 有点想你了", out)
        self.assertNotIn("小美。", out)
        self.assertNotIn("小美，", out)

    def test_trailing_question_removed(self):
        out = t.apply_attachment("今天累不累？", "焦虑型", seed=1)
        self.assertIn("今天累不累", out)
        self.assertFalse(out.rstrip().endswith(("？", "?", "。")), out)

    def test_no_leading_question_with_empty_nick(self):
        out = t.render("久未联系", nickname="", detail="", attachment="焦虑型", seed=0)
        self.assertFalse(out.startswith(("？", "?", " ")))
        self.assertTrue(out)


class TestSplitMessages(unittest.TestCase):
    def test_returns_several_parts(self):
        out = t.render_messages("低落陪伴", nickname="小美", detail="今天加班很累吧", seed=2)
        self.assertIsInstance(out, list)
        self.assertGreaterEqual(len(out), 1)

    def test_tail_stays_in_last_part(self):
        """依恋后缀是最后的确定性信号，必须落在末尾几条里，不能被并到开头"""
        parts = t.render_messages("深夜晚安", nickname="小美", max_parts=4,
                                  attachment="焦虑型", seed=0)
        self.assertIn("看到就回你", " ".join(parts[-2:]), parts)
        self.assertNotIn("看到就回你", parts[0], parts)

    def test_max_parts_respected(self):
        """条数上限是防刷屏的，超了就把相邻两条并起来（宁可长一点也不发八条）"""
        parts = t.split_messages(
            "先别说话 靠一下 今天不想说也行 我在 看到就回你", max_parts=2)
        self.assertEqual(len(parts), 2, parts)

    def test_split_no_longer_needs_punct(self):
        """第 6 条之后文本本来就没标点，拆分得按空格走"""
        parts = t.split_messages("先别说话 靠一下 今天不想说也行 我在", max_parts=4)
        self.assertGreater(len(parts), 1, parts)
        self.assertEqual(" ".join(parts).replace(" ", ""),
                         "先别说话靠一下今天不想说也行我在", "断条不能丢字")

    def test_every_part_fits_one_line(self):
        """第 8 条：一条十来字顶天，碎碎念是多条短句，不是一条长句"""
        for kind in t.TEMPLATES:
            for att in ("焦虑型", "回避型", "安全型", "恐惧型"):
                parts = t.render_messages(kind, nickname="小美",
                                          detail="我们在一起三百天",
                                          attachment=att, seed=0)
                for p in parts:
                    self.assertLessEqual(len(p), t.MAX_LINE_CHARS,
                                         f"{kind}/{att}: {p}")

    def test_short_words_get_merged(self):
        """十个字以内就该是一条，别为了「多条」硬拆"""
        self.assertEqual(t.split_messages("先别说话 靠一下 我在"), ["先别说话 靠一下 我在"])

    def test_never_cuts_mid_word(self):
        """两个空格段之间不会半字切开（「我一直记着 我」这种半句比超长更糟）"""
        words = ["小美", "我一直记着", "我在", "看到就回你"]
        parts = t.split_messages(" ".join(words))
        for p in parts:
            for w in p.split():
                self.assertIn(w, words, f"切到了词中间：{p}")

    def test_unknown_kind_gives_empty_list(self):
        self.assertEqual(t.render_messages("不存在的类型", nickname="小美"), [])

    def test_empty_text(self):
        self.assertEqual(t.split_messages(""), [])


if __name__ == "__main__":
    unittest.main()
