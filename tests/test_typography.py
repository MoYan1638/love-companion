# -*- coding: utf-8 -*-
"""排版层（typography.py）—— 回复十条里第 6、8 条的机械部分

这两条是十条规矩里唯一能被脚本判的，也就最容易写歪：

1. **去标点不能去过头**：省略号是留白、括号是补白、引号是引用原话——
   它们和句号逗号不是一类东西。一刀切全删，句子会变硬变呆。
2. **删标点不能改意思**：只允许「标点 → 空格」，一个字都不许动。
3. **断条不能断坏语气**：优先在空格处断（那是上一句留下的断点），
   单个词超长才硬切，否则会产出一条永远发不出去的消息。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.style import typography  # noqa: E402

from scripts.core import schema  # noqa: E402


class TestStripPunct(unittest.TestCase):
    def test_removes_sentence_punctuation(self):
        self.assertEqual(typography.strip_punct("我在。你说。"), "我在 你说")

    def test_removes_all_break_marks(self):
        out = typography.strip_punct("不是，算了；先睡：明天再说！真的？")
        self.assertNotIn("，", out)
        self.assertNotIn("；", out)
        self.assertNotIn("：", out)
        self.assertNotIn("！", out)
        self.assertNotIn("？", out)

    def test_keeps_tone_parts(self):
        """省略号/括号/引号/破折号是语气零件，删了意思会变"""
        src = "我……算了（小声）「晚安」——明天见"
        out = typography.strip_punct(src)
        for mark in ("……", "（", "）", "「", "」", "——"):
            self.assertIn(mark, out, f"把 {mark} 删掉了，这不是断句标点")

    def test_removes_ascii_punctuation(self):
        self.assertEqual(typography.strip_punct("ok. fine, sure"), "ok fine sure")

    def test_no_semantic_change(self):
        """去掉标点后，剩下的字必须和原文一致——只许换空格"""
        src = "今天好累。你早点睡，别熬夜了。"
        out = typography.strip_punct(src)
        expected = "".join(ch for ch in src if ch not in typography.TERMINAL)
        self.assertEqual(out.replace(" ", ""), expected.replace(" ", ""))

    def test_collapses_whitespace(self):
        self.assertEqual(typography.strip_punct("  我在。。  你说  "), "我在 你说")

    def test_empty(self):
        self.assertEqual(typography.strip_punct(""), "")
        self.assertEqual(typography.strip_punct("   "), "")

    def test_newlines_become_spaces(self):
        self.assertEqual(typography.strip_punct("我在\n你说"), "我在 你说")


class TestSplitByLength(unittest.TestCase):
    def test_short_stays_one(self):
        self.assertEqual(typography.split_by_length("我在 你说", 40), ["我在 你说"])

    def test_splits_on_space(self):
        text = " ".join(["一二三四五"] * 12)   # 12 个 5 字词，共 71 字
        parts = typography.split_by_length(text, 20)
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertLessEqual(len(p), 20)
        self.assertEqual(" ".join(parts), text, "断条不能丢字或改字")

    def test_hard_split_long_word(self):
        parts = typography.split_by_length("啊" * 90, 40)
        self.assertEqual(len(parts), 3)
        self.assertEqual("".join(parts), "啊" * 90)

    def test_hard_split_balances_two_pieces(self):
        """13 字上限 12，不能切成 12+1（读起来像手滑），要均分"""
        parts = typography.split_by_length("啊" * 13, 12)
        self.assertEqual(len(parts), 2)
        self.assertEqual("".join(parts), "啊" * 13)
        self.assertLessEqual(max(len(p) for p in parts), 8)

    def test_empty(self):
        self.assertEqual(typography.split_by_length("", 40), [])

    def test_zero_limit_disables(self):
        self.assertEqual(typography.split_by_length("我在 你说", 0), ["我在 你说"])


class TestAudit(unittest.TestCase):
    def test_flags_punctuation(self):
        r = typography.audit("我在。你说。")
        self.assertFalse(r["ok"])
        self.assertEqual(r["punct"], 2)
        self.assertTrue(any("第 6 条" in i for i in r["issues"]))

    def test_flags_long_message(self):
        r = typography.audit(" ".join(["一二三四五"] * 12), max_chars=20)
        self.assertFalse(r["ok"])
        self.assertTrue(any("第 8 条" in i for i in r["issues"]))
        self.assertGreater(r["parts"], 1)

    def test_long_check_uses_original_length(self):
        """断条是补救手段，需要补救就说明原文太长——不能因为断完每条都短就判合格"""
        r = typography.audit("啊" * 60, max_chars=40)
        self.assertFalse(r["ok"])
        self.assertEqual(r["chars"], 60)

    def test_clean_passes(self):
        r = typography.audit("先别说话 靠一下")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["parts"], 1)


class TestFormatReply(unittest.TestCase):
    def test_default_reads_settings(self):
        data_dir = tempfile.mkdtemp()
        out = typography.format_reply("我在。你说。", data_dir=data_dir)
        self.assertEqual(out, ["我在 你说"])

    def test_settings_can_turn_it_off(self):
        data_dir = tempfile.mkdtemp()
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"回复风格": {"无标点": False, "单条字数上限": 40}},
                      fh, ensure_ascii=False)
        out = typography.format_reply("我在。你说。", data_dir=data_dir)
        self.assertEqual(out, ["我在。你说。"])

    def test_explicit_override_wins(self):
        out = typography.format_reply("我在。你说。", no_punct=False)
        self.assertEqual(out, ["我在。你说。"])

    def test_returns_list_for_bad_input(self):
        self.assertEqual(typography.format_reply(""), [])
        self.assertEqual(typography.format_reply(None), [])


class TestShortReplyStop(unittest.TestCase):
    """短回应句号：第 6 条的例外，默认关

    「哦哦。」「嗯嗯。」「呃。」——极短回应末尾的那个句号是语气（收得干净、有点冷淡），
    不是作文感。但这条不能放宽：多一个字、句中还有标点、或者整句在说话，都不能留。
    """

    def test_short_reply_keeps_stop_when_enabled(self):
        for src in ("哦哦。", "嗯嗯。", "呃。", "好。", "行。"):
            with self.subTest(src=src):
                self.assertEqual(typography.strip_punct(src, keep_short_stop=True), src)

    def test_short_reply_default_drops_stop(self):
        self.assertEqual(typography.strip_punct("哦哦。"), "哦哦")

    def test_not_short_enough_is_still_stripped(self):
        """超过 4 字就不是短回应了，句号该去"""
        out = typography.strip_punct("我知道了。", keep_short_stop=True)
        self.assertEqual(out, "我知道了")
        self.assertNotIn("。", out)

    def test_two_stops_not_kept(self):
        """「嗯。好。」是两个动作，不是短回应，照常去掉"""
        out = typography.strip_punct("嗯。好。", keep_short_stop=True)
        self.assertNotIn("。", out)

    def test_audit_respects_short_stop(self):
        r = typography.audit("哦哦。", keep_short_stop=True)
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["punct"], 0)
        self.assertFalse(typography.audit("哦哦。")["ok"])

    def test_format_reply_reads_setting(self):
        data_dir = tempfile.mkdtemp()
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"回复风格": {"无标点": True, "单条字数上限": 12, "短回应句号": True}},
                      fh, ensure_ascii=False)
        self.assertEqual(typography.format_reply("嗯嗯。", data_dir=data_dir), ["嗯嗯。"])


class TestSettingsWiring(unittest.TestCase):
    def test_template_has_reply_style(self):
        style = schema.settings_template()["回复风格"]
        self.assertTrue(style["无标点"], "默认应该是「不带标点」，这是聊天窗里的常态")
        self.assertEqual(style["单条字数上限"], 12, "一条十字顶天，留两字余量给语气词")
        self.assertFalse(style["短回应句号"], "短回应默认不加句号，要加自己开")

    def test_legacy_settings_get_migrated(self):
        """老 settings.json 存的是旧默认 40 字，深合并会盖掉新默认——要迁到 12"""
        data_dir = tempfile.mkdtemp()
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"回复风格": {"无标点": True, "单条字数上限": 40}},
                      fh, ensure_ascii=False)
        cfg = typography.style_config(data_dir)
        self.assertEqual(cfg["单条字数上限"], 12)
        self.assertFalse(cfg["短回应句号"])

    def test_new_settings_keep_manual_limit(self):
        """新结构里手动设的 40 是人家的选择，不许动"""
        data_dir = tempfile.mkdtemp()
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"回复风格": {"无标点": True, "单条字数上限": 40,
                                    "短回应句号": False}},
                      fh, ensure_ascii=False)
        self.assertEqual(typography.style_config(data_dir)["单条字数上限"], 40)

    def test_cli_prints_json(self):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "style" / "typography.py"), "我在。你说。"],
            capture_output=True, env=env, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace")[-300:])
        data = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(data["messages"], ["我在 你说"])
        self.assertEqual(data["audit"]["punct"], 2)


if __name__ == "__main__":
    unittest.main()
