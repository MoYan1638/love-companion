"""军师模式结构校验

恋人模式与军师模式互斥，最容易出的事故是「军师常开，恋人开始分析用户」，
或者「军师读了人格库，用她的口吻给用户的现实关系提建议」。
这组测试把两件事钉住：模块默认关闭、边界写在文档里。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / "references" / "strategy"

REQUIRED = (
    "00-导读与模式边界.md",
    "01-关系判断五步.md",
    "02-一句话与推进.md",
    "03-投入多人与退出.md",
    "04-档案与评分.md",
)

MAX_CHARS = 7000
MIN_CHARS = 900


class TestStrategyDir(unittest.TestCase):
    def test_dir_exists(self):
        self.assertTrue(STRATEGY.is_dir(), f"军师模式目录不存在: {STRATEGY}")

    def test_required_files(self):
        for name in REQUIRED:
            with self.subTest(name=name):
                self.assertTrue((STRATEGY / name).is_file(), f"缺少 {name}")

    def test_every_file_has_trigger(self):
        for path in sorted(STRATEGY.glob("*.md")):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("什么时候读", text, f"{path.name} 没写触发条件")

    def test_size_within_range(self):
        for path in sorted(STRATEGY.glob("*.md")):
            with self.subTest(file=path.name):
                n = len(path.read_text(encoding="utf-8"))
                self.assertLessEqual(n, MAX_CHARS, f"{path.name} 过长（{n} 字）")
                self.assertGreaterEqual(n, MIN_CHARS, f"{path.name} 过短（{n} 字）")


class TestModeBoundary(unittest.TestCase):
    def setUp(self):
        self.intro = (STRATEGY / "00-导读与模式边界.md").read_text(encoding="utf-8")

    def test_default_off_is_documented(self):
        """默认关闭是设计约束：军师常开会让恋人开始分析用户"""
        self.assertIn("默认", self.intro)
        self.assertIn("关闭", self.intro)

    def test_does_not_read_persona(self):
        """不读 persona / 不读恋人记忆——最容易被实现漏掉的一条"""
        self.assertIn("不读 persona", self.intro)

    def test_three_bottom_lines(self):
        for kw in ("不教操控", "不替人做决定", "明确拒绝就停"):
            with self.subTest(kw=kw):
                self.assertIn(kw, self.intro, f"缺底线「{kw}」")

    def test_not_only_goal_is_winning_her(self):
        self.assertIn("唯一", self.intro)

    def test_never_pressures(self):
        """绝不能把「让她难拒绝」写成技巧"""
        text = self.intro + (STRATEGY / "02-一句话与推进.md").read_text(encoding="utf-8")
        for bad in ("假想敌", "制造嫉妒"):
            if bad in text:
                # 只允许出现在否定语境里
                for m in re.finditer(bad, text):
                    window = text[max(0, m.start() - 40):m.start()]
                    self.assertTrue(
                        any(k in window for k in ("不", "禁止", "一律")),
                        f"「{bad}」出现在非否定语境"
                    )


class TestModuleSwitch(unittest.TestCase):
    def test_module_registered(self):
        from scripts.panel.controls import MODULES
        self.assertIn("军师模式", MODULES)

    def test_default_off_in_template(self):
        from scripts.core.schema import settings_template
        switches = settings_template()["模块开关"]
        self.assertIn("军师模式", switches)
        self.assertFalse(switches["军师模式"], "军师模式默认必须关闭")

    def test_toggle_works(self):
        import os
        import tempfile
        from unittest import mock

        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"LOVE_COMPANION_DATA_DIR": d}):
            from scripts.panel.controls import Controls
            c = Controls()
            self.assertFalse(c.enabled("军师模式"))
            self.assertTrue(c.toggle("军师模式", True))
            self.assertTrue(c.enabled("军师模式"))
            c.toggle("军师模式", False)
            self.assertFalse(c.enabled("军师模式"))


class TestSkillMentions(unittest.TestCase):
    def test_skill_md_points_to_strategy(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/strategy/", skill)
        self.assertIn("/恋人军师", skill)


if __name__ == "__main__":
    unittest.main()
