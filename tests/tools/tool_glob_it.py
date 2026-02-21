"""Glob Tool 集成测试 - 对齐 opencode 设计

测试 GlobTool 的各种场景：
1. 正常 glob 搜索（如 *.py）
2. 递归 glob（如 **/*.py）
3. 指定搜索路径
4. 无匹配结果
5. 结果截断（>100 个文件）
6. 相对路径搜索
7. 绝对路径搜索
8. 无效路径处理
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dm_cc.tools.glob import GlobTool, GlobParams


class TestGlobTool:
    """Glob Tool 测试类"""

    def __init__(self):
        self.tool = GlobTool()
        self.test_dir = Path(tempfile.mkdtemp(prefix="dm_cc_glob_test_"))
        print(f"测试目录: {self.test_dir}")

    def setup_test_files(self):
        """创建测试文件结构"""
        os.chdir(self.test_dir)

        # 1. 创建一些 Python 文件
        (self.test_dir / "main.py").write_text("print('main')")
        (self.test_dir / "utils.py").write_text("def utils(): pass")
        (self.test_dir / "README.md").write_text("# README")
        (self.test_dir / "config.json").write_text('{"key": "value"}')

        # 2. 创建子目录结构
        (self.test_dir / "src").mkdir()
        (self.test_dir / "src" / "app.py").write_text("# app")
        (self.test_dir / "src" / "models.py").write_text("# models")

        (self.test_dir / "tests").mkdir()
        (self.test_dir / "tests" / "test_main.py").write_text("# test main")
        (self.test_dir / "tests" / "test_utils.py").write_text("# test utils")

        # 3. 创建嵌套目录
        (self.test_dir / "src" / "utils").mkdir()
        (self.test_dir / "src" / "utils" / "helpers.py").write_text("# helpers")
        (self.test_dir / "src" / "utils" / "constants.py").write_text("# constants")

        # 4. 设置不同的修改时间（用于测试排序）
        # 最先创建的文件（最旧）
        oldest = self.test_dir / "oldest.py"
        oldest.write_text("# oldest")
        time.sleep(0.1)

        middle = self.test_dir / "middle.py"
        middle.write_text("# middle")
        time.sleep(0.1)

        # 最后创建的文件（最新）
        newest = self.test_dir / "newest.py"
        newest.write_text("# newest")

        print(f"创建测试文件完成，共 {len(list(self.test_dir.rglob('*')))} 个文件/目录")

    def setup_many_files(self):
        """创建大量文件用于测试截断"""
        many_dir = self.test_dir / "many_files"
        many_dir.mkdir()

        for i in range(150):
            (many_dir / f"file_{i:03d}.txt").write_text(f"content {i}")

        print(f"创建 150 个测试文件用于截断测试")

    async def test_01_glob_normal_pattern(self):
        """测试1: 正常 glob 搜索（*.py）"""
        print("\n" + "="*60)
        print("测试1: 正常 glob 搜索 (*.py)")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="*.py")
        result = await self.tool.execute(params)

        assert "title" in result, "返回应包含 title"
        assert "output" in result, "返回应包含 output"
        assert "metadata" in result, "返回应包含 metadata"

        # 应该找到根目录下的 .py 文件
        output = result["output"]
        assert "main.py" in output, "应找到 main.py"
        assert "utils.py" in output, "应找到 utils.py"
        # 不应包含子目录中的文件（非递归）
        assert "src/app.py" not in output.replace("\\", "/"), "非递归模式不应包含子目录文件"

        print("✅ 通过")
        print(f"找到 {result['metadata']['count']} 个文件")
        print(f"输出预览:\n{output[:500]}...")

    async def test_02_glob_recursive_pattern(self):
        """测试2: 递归 glob 搜索（**/*.py）"""
        print("\n" + "="*60)
        print("测试2: 递归 glob 搜索 (**/*.py)")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="**/*.py")
        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result

        output = result["output"]
        # 应该包含所有层级的 .py 文件
        assert "main.py" in output, "应找到 main.py"
        assert "src/app.py" in output.replace("\\", "/") or "src\\app.py" in output, "应找到 src/app.py"
        assert "tests/test_main.py" in output.replace("\\", "/") or "tests\\test_main.py" in output, "应找到 tests/test_main.py"

        print("✅ 通过")
        print(f"找到 {result['metadata']['count']} 个文件")

    async def test_03_glob_with_specific_path(self):
        """测试3: 指定搜索路径"""
        print("\n" + "="*60)
        print("测试3: 指定搜索路径")
        print("="*60)

        os.chdir(self.test_dir)

        # 只在 src 目录搜索
        params = GlobParams(pattern="*.py", path="src")
        result = await self.tool.execute(params)

        assert "title" in result
        output = result["output"]

        # 应该只找到 src 目录下的文件
        assert "app.py" in output, "应找到 app.py"
        assert "models.py" in output, "应找到 models.py"
        # 不应找到根目录的文件
        assert "main.py" not in output, "不应包含根目录的 main.py"

        print("✅ 通过")
        print(f"输出:\n{output}")

    async def test_04_glob_no_results(self):
        """测试4: 无匹配结果"""
        print("\n" + "="*60)
        print("测试4: 无匹配结果")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="*.nonexistent")
        result = await self.tool.execute(params)

        assert "output" in result
        assert "No files found" in result["output"], "应提示未找到文件"
        assert result["metadata"]["count"] == 0, "count 应为 0"
        assert result["metadata"]["truncated"] is False, "未截断"

        print("✅ 通过")
        print(f"输出: {result['output']}")

    async def test_05_glob_truncation(self):
        """测试5: 结果截断（>100 个文件）"""
        print("\n" + "="*60)
        print("测试5: 结果截断（>100 个文件）")
        print("="*60)

        self.setup_many_files()
        os.chdir(self.test_dir)

        params = GlobParams(pattern="many_files/*.txt")
        result = await self.tool.execute(params)

        assert "metadata" in result
        assert result["metadata"]["count"] == 100, "应返回 100 个文件"
        assert result["metadata"]["truncated"] is True, "应标记为截断"

        output = result["output"]
        assert "truncated" in output.lower() or "Results are truncated" in output, "应提示截断"

        print("✅ 通过")
        print(f"返回数量: {result['metadata']['count']}")
        print(f"截断提示: {'truncated' in output}")

    async def test_06_glob_sorted_by_mtime(self):
        """测试6: 按修改时间排序（最新的在前）"""
        print("\n" + "="*60)
        print("测试6: 按修改时间排序（最新的在前）")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="*.py")
        result = await self.tool.execute(params)

        output = result["output"]
        lines = [l for l in output.split("\n") if l.strip() and not l.startswith("(")]

        # newest.py 应该在最前面
        if len(lines) >= 3:
            # 找到 newest.py 和 oldest.py 的位置
            newest_pos = next((i for i, l in enumerate(lines) if "newest.py" in l), -1)
            oldest_pos = next((i for i, l in enumerate(lines) if "oldest.py" in l), -1)

            if newest_pos >= 0 and oldest_pos >= 0:
                assert newest_pos < oldest_pos, "newest.py 应该在 oldest.py 前面"
                print("✅ 通过 - 按修改时间排序正确")
            else:
                print(f"⚠️ 跳过 - 未找到测试文件 (newest: {newest_pos}, oldest: {oldest_pos})")
        else:
            print(f"⚠️ 跳过 - 文件数量不足 ({len(lines)})")

    async def test_07_glob_relative_path(self):
        """测试7: 相对路径搜索"""
        print("\n" + "="*60)
        print("测试7: 相对路径搜索")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="tests/*.py")
        result = await self.tool.execute(params)

        assert "output" in result
        output = result["output"]

        assert "test_main.py" in output, "应找到 test_main.py"
        assert "test_utils.py" in output, "应找到 test_utils.py"

        print("✅ 通过")
        print(f"输出:\n{output}")

    async def test_08_glob_absolute_path(self):
        """测试8: 绝对路径搜索"""
        print("\n" + "="*60)
        print("测试8: 绝对路径搜索")
        print("="*60)

        abs_path = str(self.test_dir / "src")
        params = GlobParams(pattern="*.py", path=abs_path)
        result = await self.tool.execute(params)

        assert "output" in result
        output = result["output"]

        assert "app.py" in output, "应找到 app.py"

        print("✅ 通过")
        print(f"输出:\n{output}")

    async def test_09_glob_nonexistent_directory(self):
        """测试9: 无效路径处理（目录不存在）"""
        print("\n" + "="*60)
        print("测试9: 无效路径处理（目录不存在）")
        print("="*60)

        params = GlobParams(pattern="*.py", path="/nonexistent/directory")

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError as e:
            assert "Directory not found" in str(e), f"错误消息应包含 'Directory not found': {e}"
            print("✅ 通过 - 正确抛出 FileNotFoundError")
            print(f"错误信息: {e}")

    async def test_10_glob_file_as_path(self):
        """测试10: 用文件作为路径（应报错）"""
        print("\n" + "="*60)
        print("测试10: 用文件作为路径（应报错）")
        print("="*60)

        os.chdir(self.test_dir)

        # 尝试用一个文件作为搜索路径
        params = GlobParams(pattern="*.py", path="main.py")

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 NotADirectoryError"
        except NotADirectoryError as e:
            assert "Path is not a directory" in str(e), f"错误消息应包含 'Path is not a directory': {e}"
            print("✅ 通过 - 正确抛出 NotADirectoryError")
            print(f"错误信息: {e}")

    async def test_11_glob_all_files(self):
        """测试11: 搜索所有文件（*）"""
        print("\n" + "="*60)
        print("测试11: 搜索所有文件（*）")
        print("="*60)

        os.chdir(self.test_dir)

        params = GlobParams(pattern="*")
        result = await self.tool.execute(params)

        assert "output" in result
        output = result["output"]

        # 应该找到根目录下的所有文件和目录（但只返回文件）
        assert "main.py" in output, "应找到 main.py"
        assert "README.md" in output, "应找到 README.md"

        print("✅ 通过")
        print(f"找到 {result['metadata']['count']} 个文件")

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("开始 Glob Tool 集成测试")
        print("="*60)

        self.setup_test_files()

        tests = [
            self.test_01_glob_normal_pattern,
            self.test_02_glob_recursive_pattern,
            self.test_03_glob_with_specific_path,
            self.test_04_glob_no_results,
            self.test_05_glob_truncation,
            self.test_06_glob_sorted_by_mtime,
            self.test_07_glob_relative_path,
            self.test_08_glob_absolute_path,
            self.test_09_glob_nonexistent_directory,
            self.test_10_glob_file_as_path,
            self.test_11_glob_all_files,
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
    tester = TestGlobTool()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
