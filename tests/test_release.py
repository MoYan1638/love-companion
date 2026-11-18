# -*- coding: utf-8 -*-
"""发布质量：许可证一致性 + Windows 控制台兼容

这两类问题不会让功能测试失败，但会直接伤到使用者：

1. **许可证自相矛盾**：LICENSE 写 CC BY-NC 4.0，而 SKILL.md / README / manager.py
   写 MIT。使用者按 MIT 理解就会把非商用项目打包进付费产品，出事时双方都站不住。
   许可证只有一份真相源：仓库根目录的 LICENSE，其余位置必须与它一致。

2. **Windows 控制台崩掉**：cmd / PowerShell 默认代码页 936（GBK），而人设里
   出现 emoji 是常态。print 含 emoji 的 JSON 会抛 UnicodeEncodeError，
   用户看到的是 traceback 而不是结果。修复方式是只改 errors 不改编码。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestLicenseConsistency(unittest.TestCase):
    """许可证只有一份真相源，别处必须与它一致"""

    def test_license_file_declares_cc_by_nc(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("CC BY-NC 4.0", text)
        self.assertIn("NonCommercial", text)

    def test_package_json_matches_license(self):
        pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg.get("license"), "CC-BY-NC-4.0")

    def test_skill_md_license_section_matches(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("CC BY-NC 4.0", skill)
        self.assertNotIn("MIT License", skill, "SKILL.md 仍写着 MIT，与 LICENSE 冲突")

    def test_references_do_not_claim_mit(self):
        for path in (ROOT / "references").rglob("*.md"):
            with self.subTest(file=path.name):
                self.assertNotIn("MIT License", path.read_text(encoding="utf-8"))

    def test_manager_header_matches(self):
        head = (ROOT / "scripts" / "manager.py").read_text(encoding="utf-8")[:2000]
        self.assertIn("CC BY-NC 4.0", head)
        self.assertNotIn("MIT License", head)


class TestWindowsConsole(unittest.TestCase):
    """GBK 终端下打印含 emoji 的人设不能崩——崩了用户拿不到任何结果"""

    def _run_with_persona(self, io_encoding: str):
        data_dir = tempfile.mkdtemp()
        with open(os.path.join(data_dir, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"合规": {"已满18周岁确认": True}}, fh, ensure_ascii=False)
        with open(os.path.join(data_dir, "persona.json"), "w", encoding="utf-8") as fh:
            json.dump({"名字": "小满", "口头禅": ["好呀😊", "晚安🌙"]}, fh, ensure_ascii=False)

        env = dict(os.environ)
        env["LOVE_COMPANION_DATA_DIR"] = data_dir
        env["PYTHONIOENCODING"] = io_encoding
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "manager.py"), "get"],
            capture_output=True, env=env, cwd=str(ROOT),
        )

    def test_gbk_console_does_not_crash(self):
        proc = self._run_with_persona("gbk")
        self.assertEqual(proc.returncode, 0,
                         "GBK 控制台下崩溃了：" + proc.stderr.decode("gbk", "replace")[-400:])
        self.assertIn("小满", proc.stdout.decode("gbk", "replace"))

    def test_utf8_console_keeps_emoji(self):
        proc = self._run_with_persona("utf-8")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("好呀😊", proc.stdout.decode("utf-8", "replace"))


class TestDocConsistency(unittest.TestCase):
    """文档之间不许互相矛盾——对外发布时，每个人只会看到其中一页

    这三类矛盾都真实出现过：版本号三个地方各写各的、合规声明只写进了
    README 而手册里没有、SKILL.md 教了 13 条指令但「完整指令手册」里查不到。
    """

    def _version(self) -> str:
        return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]

    def test_version_matches_everywhere(self):
        ver = self._version()
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"version: {ver}", skill, "SKILL.md 的 version 与 package.json 不一致")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"Version-{ver}-", readme, "README 版本徽章没跟上")

    def test_public_docs_state_age_gate(self):
        """年龄门槛是对外承诺，不能只写在首页"""
        for name in ("README.md", "SKILL.md",
                     os.path.join("references", "commands.md"),
                     os.path.join("references", "instructions.md")):
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertRegex(text, r"18\s*周岁", f"{name} 没写 18+ 门槛")

    def test_commands_manual_covers_skill_commands(self):
        """SKILL.md 教的每条指令，手册里都得查得到——手册标题写着「完整」"""
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        manual = (ROOT / "references" / "commands.md").read_text(encoding="utf-8")
        cmds = set(re.findall(r"`(/恋人[^`\]\s]*)", skill))
        cmds |= set(re.findall(r"`(/查看记忆|/删除记忆)", skill))
        self.assertTrue(cmds, "没从 SKILL.md 抽到任何指令，正则失效了")
        missing = sorted(c for c in cmds if c not in manual)
        self.assertFalse(missing, "完整指令手册里缺：" + "、".join(missing))

    def test_dsh_bridge_not_stale(self):
        """dsh/index.js 会在系统提示里自报版本与能力，过期等于对模型说谎"""
        ver = self._version()
        js = (ROOT / "dsh" / "index.js").read_text(encoding="utf-8")
        self.assertIn(f"v{ver}", js, "dsh/index.js 头部版本号过期")
        self.assertIn("军师模式", js, "dsh/index.js 的能力说明没跟上 v2.4")

    def test_docs_test_count_matches_reality(self):
        """README 拿测试数量当质量背书，就必须是真的——写多了是吹牛，写少了是白干"""
        total = 0
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            total += len(re.findall(r"^    def test_", path.read_text(encoding="utf-8"), re.M))
        for name in ("README.md", "SKILL.md", os.path.join("docs", "architecture.md")):
            with self.subTest(file=name):
                self.assertIn(f"{total} 项", (ROOT / name).read_text(encoding="utf-8"),
                              f"{name} 的测试数量与实际的 {total} 项不一致")


if __name__ == "__main__":
    unittest.main()
