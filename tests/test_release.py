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


if __name__ == "__main__":
    unittest.main()
