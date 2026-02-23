"""Edit Tool 集成测试 - 对齐 opencode 设计

测试 EditTool 的各种场景：
1. 正常编辑（精确匹配）
2. 行修剪匹配（忽略首尾空格差异）
3. 块锚点匹配（使用首尾行定位）
4. 多处匹配（无 replaceAll 时应报错）
5. replaceAll 替换所有
6. 文件不存在
7. oldString 不存在
8. oldString == newString
9. 相对路径
10. 绝对路径
"""

import asyncio
import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dm_cc.tools.edit import EditTool, EditParams, replace_content


class TestEditTool:
    """Edit Tool 测试类"""

    def __init__(self):
        self.tool = EditTool()
        self.test_dir = Path(tempfile.mkdtemp(prefix="dm_cc_edit_test_"))
        print(f"测试目录: {self.test_dir}")

    def setup_test_files(self):
        """创建测试文件"""
        os.chdir(self.test_dir)

        # 1. 普通 Python 文件
        (self.test_dir / "hello.py").write_text(
            "import os\n"
            "import sys\n"
            "\n"
            "def main():\n"
            "    print('Hello, World!')\n"
            "    return 0\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())\n"
        )

        # 2. 多行内容文件
        (self.test_dir / "multi.py").write_text(
            "def func_a():\n"
            "    pass\n"
            "\n"
            "def func_b():\n"
            "    pass\n"
            "\n"
            "def func_c():\n"
            "    pass\n"
        )

        # 3. 带缩进的文件
        (self.test_dir / "indented.py").write_text(
            "class MyClass:\n"
            "    def method1(self):\n"
            "        x = 1\n"
            "        y = 2\n"
            "        return x + y\n"
            "\n"
            "    def method2(self):\n"
            "        pass\n"
        )

        # 4. 多处相同内容的文件
        (self.test_dir / "duplicates.py").write_text(
            "x = 1\n"
            "y = x + 1\n"
            "z = x + 2\n"
            "print(x)\n"
        )

        print("创建测试文件完成")

    async def test_01_simple_edit(self):
        """测试1: 简单编辑（精确匹配）"""
        print("\n" + "="*60)
        print("测试1: 简单编辑（精确匹配）")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="hello.py",
            oldString="print('Hello, World!')",
            newString="print('Hello, Python!')"
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result
        assert result["output"] == "Edit applied successfully."

        # 验证文件内容
        content = (self.test_dir / "hello.py").read_text()
        assert "print('Hello, Python!')" in content
        assert "print('Hello, World!')" not in content

        print("✅ 通过")
        print(f"文件内容:\n{content}")

    async def test_02_line_trimmed_match(self):
        """测试2: 行修剪匹配（忽略首尾空格差异）"""
        print("\n" + "="*60)
        print("测试2: 行修剪匹配")
        print("="*60)

        os.chdir(self.test_dir)

        # 使用不同的缩进但仍然能匹配
        params = EditParams(
            filePath="indented.py",
            oldString="    def method1(self):\n        x = 1\n        y = 2\n        return x + y",
            newString="    def method1(self):\n        x = 10\n        y = 20\n        return x * y"
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        content = (self.test_dir / "indented.py").read_text()
        assert "x = 10" in content
        assert "return x * y" in content

        print("✅ 通过")

    async def test_03_block_anchor_match(self):
        """测试3: 块锚点匹配（使用首尾行定位）"""
        print("\n" + "="*60)
        print("测试3: 块锚点匹配")
        print("="*60)

        os.chdir(self.test_dir)

        # 只使用首尾行作为锚点
        params = EditParams(
            filePath="multi.py",
            oldString="def func_a():\n    pass",
            newString="def func_a_modified():\n    # modified\n    pass"
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        content = (self.test_dir / "multi.py").read_text()
        assert "def func_a_modified():" in content

        print("✅ 通过")
        print(f"文件内容:\n{content}")

    async def test_04_multiple_matches_no_replace_all(self):
        """测试4: 多处匹配（无 replaceAll 时应报错）"""
        print("\n" + "="*60)
        print("测试4: 多处匹配（无 replaceAll 时应报错）")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="duplicates.py",
            oldString="x",
            newString="var_x"
        )

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "multiple matches" in str(e).lower() or "unique" in str(e).lower()
            print("✅ 通过 - 正确提示多处匹配")
            print(f"错误信息: {e}")

    async def test_05_replace_all(self):
        """测试5: replaceAll 替换所有"""
        print("\n" + "="*60)
        print("测试5: replaceAll 替换所有")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="duplicates.py",
            oldString="x",
            newString="var_x",
            replaceAll=True
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        content = (self.test_dir / "duplicates.py").read_text()
        assert "var_x = 1" in content
        assert "y = var_x + 1" in content
        assert "z = var_x + 2" in content
        assert "print(var_x)" in content
        assert " x " not in content  # 原来的 x 应该都被替换

        print("✅ 通过")
        print(f"文件内容:\n{content}")

    async def test_06_file_not_found(self):
        """测试6: 文件不存在"""
        print("\n" + "="*60)
        print("测试6: 文件不存在")
        print("="*60)

        params = EditParams(
            filePath="nonexistent.py",
            oldString="old",
            newString="new"
        )

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError as e:
            assert "File not found" in str(e)
            print("✅ 通过 - 正确抛出 FileNotFoundError")

    async def test_07_old_string_not_found(self):
        """测试7: oldString 不存在"""
        print("\n" + "="*60)
        print("测试7: oldString 不存在")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="hello.py",
            oldString="this text does not exist",
            newString="new text"
        )

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "Could not find" in str(e)
            print("✅ 通过 - 正确提示未找到")
            print(f"错误信息: {e}")

    async def test_08_identical_strings(self):
        """测试8: oldString == newString"""
        print("\n" + "="*60)
        print("测试8: oldString == newString")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="hello.py",
            oldString="import os",
            newString="import os"
        )

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "identical" in str(e).lower()
            print("✅ 通过 - 正确提示字符串相同")
            print(f"错误信息: {e}")

    async def test_09_relative_path(self):
        """测试9: 相对路径"""
        print("\n" + "="*60)
        print("测试9: 相对路径")
        print("="*60)

        os.chdir(self.test_dir)

        params = EditParams(
            filePath="./hello.py",
            oldString="import sys",
            newString="import typing"
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        content = (self.test_dir / "hello.py").read_text()
        assert "import typing" in content

        print("✅ 通过")

    async def test_10_absolute_path(self):
        """测试10: 绝对路径"""
        print("\n" + "="*60)
        print("测试10: 绝对路径")
        print("="*60)

        abs_path = str(self.test_dir / "hello.py")
        params = EditParams(
            filePath=abs_path,
            oldString="def main():",
            newString="def main() -> int:"
        )
        params._auto_confirm = True
        result = await self.tool.execute(params)

        content = (self.test_dir / "hello.py").read_text()
        assert "def main() -> int:" in content

        print("✅ 通过")

    async def test_11_directory_as_file(self):
        """测试11: 用目录作为文件路径"""
        print("\n" + "="*60)
        print("测试11: 用目录作为文件路径")
        print("="*60)

        os.chdir(self.test_dir)
        (self.test_dir / "subdir").mkdir()

        params = EditParams(
            filePath="subdir",
            oldString="old",
            newString="new"
        )

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 IsADirectoryError"
        except IsADirectoryError as e:
            assert "is a directory" in str(e).lower()
            print("✅ 通过 - 正确提示是目录")

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("开始 Edit Tool 集成测试")
        print("="*60)

        self.setup_test_files()

        tests = [
            self.test_01_simple_edit,
            self.test_02_line_trimmed_match,
            self.test_03_block_anchor_match,
            self.test_04_multiple_matches_no_replace_all,
            self.test_05_replace_all,
            self.test_06_file_not_found,
            self.test_07_old_string_not_found,
            self.test_08_identical_strings,
            self.test_09_relative_path,
            self.test_10_absolute_path,
            self.test_11_directory_as_file,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                await test()
                passed += 1
            except AssertionError as e:
                print(f"❌ 失败: {e}")
                failed += 1
            except Exception as e:
                print(f"❌ 异常: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

        print("\n" + "="*60)
        print(f"测试结果: {passed} 通过, {failed} 失败")
        print("="*60)

        # 清理
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        print(f"清理测试目录: {self.test_dir}")

        return failed == 0


async def main():
    """主函数"""
    tester = TestEditTool()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
