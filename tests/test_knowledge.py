"""知识库结构校验：目录完整、每份都能被按需加载、索引不漏项

知识库最容易烂的方式不是写错，是**慢慢长出没人读的文件**，或者索引和正文脱节。
这组测试钉住三件事：必读文件在、每份都有触发条件、索引里出现的文件名真实存在。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "references" / "knowledge"

REQUIRED = (
    "00-索引与用法.md",
    "01-证据分级与分寸.md",
    "02-依恋类型在对话里的样子.md",
    "03-情绪承接的分寸.md",
    "04-冲突与修复.md",
    "05-边界尺度与同意.md",
    "06-危机识别与转介.md",
    "07-关系节奏与依赖.md",
    "08-关系信号误读清单.md",
)

MAX_CHARS = 7000      # 单份上限：再长就没人读了，也吃 token
MIN_CHARS = 900       # 下限：太短说明只是占位


class TestKnowledgeBase(unittest.TestCase):
    def test_dir_exists(self):
        self.assertTrue(KB.is_dir(), f"知识库目录不存在: {KB}")

    def test_required_files(self):
        for name in REQUIRED:
            with self.subTest(name=name):
                self.assertTrue((KB / name).is_file(), f"缺少 {name}")

    def test_every_file_has_trigger(self):
        """每份都要写「什么时候读」，否则它永远不会被加载"""
        for path in sorted(KB.glob("*.md")):
            if path.name == "00-索引与用法.md":
                continue
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("什么时候读", text, f"{path.name} 没写触发条件")

    def test_size_within_range(self):
        for path in sorted(KB.glob("*.md")):
            with self.subTest(file=path.name):
                n = len(path.read_text(encoding="utf-8"))
                self.assertLessEqual(n, MAX_CHARS, f"{path.name} 过长（{n} 字）")
                self.assertGreaterEqual(n, MIN_CHARS, f"{path.name} 过短（{n} 字）")

    def test_index_covers_all(self):
        """索引表里必须出现每一份的文件名，不允许有孤儿文件"""
        index = (KB / "00-索引与用法.md").read_text(encoding="utf-8")
        for path in sorted(KB.glob("*.md")):
            if path.name == "00-索引与用法.md":
                continue
            with self.subTest(file=path.name):
                self.assertIn(path.name, index, f"索引里没列 {path.name}")

    def test_index_links_exist(self):
        """索引里提到的 .md 文件名必须真实存在，防手滑改名"""
        index = (KB / "00-索引与用法.md").read_text(encoding="utf-8")
        for name in re.findall(r"`(\d{2}-[^`]+\.md)`", index):
            with self.subTest(name=name):
                self.assertTrue((KB / name).is_file(), f"索引指向不存在的 {name}")

    def test_one_at_a_time_rule(self):
        """按需加载是设计约束，不是建议——必须明文写出来"""
        index = (KB / "00-索引与用法.md").read_text(encoding="utf-8")
        self.assertIn("一次只读一份", index)

    def test_three_hard_rules(self):
        index = (KB / "00-索引与用法.md").read_text(encoding="utf-8")
        for kw in ("不诊断", "不替代专业帮助", "证据分级"):
            with self.subTest(kw=kw):
                self.assertIn(kw, index, f"三条硬规矩缺「{kw}」")

    def test_skill_md_points_to_kb(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/knowledge/", skill)
        self.assertIn("一次只读一份", skill)

    def test_crisis_file_has_no_invented_hotline(self):
        """不许凭记忆写热线号码——报错了比不给更糟"""
        text = (KB / "06-危机识别与转介.md").read_text(encoding="utf-8")
        self.assertIn("以当地官方公布为准", text)
        # 连续 7 位以上数字视为疑似电话 / 热线号码
        self.assertIsNone(re.search(r"\d{7,}", text), "出现疑似具体号码")


class TestGenericToEveryone(unittest.TestCase):
    """发布物是给所有人的，不能混进某一段具体关系的私货"""

    PRIVATE = ("阿岁", "许楹", "贾思颖", "范俊杰", "三蹦子")

    def test_no_private_names_in_references(self):
        for path in (ROOT / "references").rglob("*.md"):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                for name in self.PRIVATE:
                    self.assertNotIn(name, text, f"{path} 混入个人化专名「{name}」")

    def test_generic_note_present(self):
        for path in (KB / "00-索引与用法.md", ROOT / "references" / "strategy" / "00-导读与模式边界.md"):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("通用性约定", text)

    def test_user_role_is_not_gendered(self):
        """「她」曾被用来指用户，等于默认用户是女性。知识库与军师模式里应已清空"""
        for path in list(KB.glob("*.md")) + list((ROOT / "references" / "strategy").glob("*.md")):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("她", text, f"{path.name} 仍有「她」指代用户")


if __name__ == "__main__":
    unittest.main()
