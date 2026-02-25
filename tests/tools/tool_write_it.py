"""Write Tool 集成测试 - 对齐 opencode 设计

测试 WriteTool 的各种场景：
1. 创建新文件
2. 覆盖现有文件
3. 父目录不存在错误
4. 路径是目录错误
5. 用户取消操作
6. 二进制文件保护
"""

import asyncio
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dm_cc.tools.write import WriteTool, WriteParams, UserCancelledError


class TestWriteTool:
    """Write Tool 测试类"""

    def __init__(self):
        self.tool = WriteTool()
        self.test_dir = Path(tempfile.mkdtemp(prefix="dm_cc_test_"))
        print(f"测试目录: {self.test_dir}")

    def setup_test_files(self):
        """创建测试文件"""
        os.chdir(self.test_dir)

        # 1. 现有文件（用于测试覆盖）
        (self.test_dir / "existing.txt").write_text(
            "This is the original content.\nLine 2\nLine 3"
        )

        # 2. 子目录
        (self.test_dir / "subdir").mkdir()
        (self.test_dir / "subdir" / "nested.txt").write_text("nested content")

    async def test_01_create_new_file(self):
        """测试1: 创建新文件"""
        print("\n" + "="*60)
        print("测试1: 创建新文件")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(filePath="newfile.txt", content="Hello, World!\n")
        params._auto_confirm = True  # 自动确认

        result = await self.tool.execute(params)

        assert "title" in result, "返回应包含 title"
        assert "output" in result, "返回应包含 output"
        assert result["title"] == "newfile.txt", f"title 应为 newfile.txt, 实际是 {result['title']}"
        assert "created" in result["output"].lower(), "output 应包含 'created'"
        assert result["metadata"]["exists"] is False, "exists 应为 False"

        # 验证文件内容
        content = (self.test_dir / "newfile.txt").read_text()
        assert content == "Hello, World!\n", f"文件内容不匹配: {content}"

        print("✅ 通过")
        print(f"结果: {result}")

    async def test_02_overwrite_existing_file(self):
        """测试2: 覆盖现有文件"""
        print("\n" + "="*60)
        print("测试2: 覆盖现有文件")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(
            filePath="existing.txt",
            content="This is the NEW content.\nReplaced!"
        )
        params._auto_confirm = True

        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result
        assert "overwritten" in result["output"].lower(), "output 应包含 'overwritten'"
        assert result["metadata"]["exists"] is True, "exists 应为 True"

        # 验证文件内容已被覆盖
        content = (self.test_dir / "existing.txt").read_text()
        assert "NEW content" in content, f"文件内容未被覆盖: {content}"

        print("✅ 通过")
        print(f"结果: {result}")

    async def test_03_parent_directory_not_exists(self):
        """测试3: 父目录不存在（应抛出异常）"""
        print("\n" + "="*60)
        print("测试3: 父目录不存在")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(
            filePath="nonexistent_dir/file.txt",
            content="content"
        )
        params._auto_confirm = True

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError as e:
            assert "Directory does not exist" in str(e), f"错误消息不匹配: {e}"
            print("✅ 通过 - 正确抛出 FileNotFoundError")
            print(f"错误信息: {e}")

    async def test_04_path_is_directory(self):
        """测试4: 路径是目录（应抛出异常）"""
        print("\n" + "="*60)
        print("测试4: 路径是目录")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(filePath="subdir", content="content")
        params._auto_confirm = True

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 IsADirectoryError"
        except IsADirectoryError as e:
            assert "Path is a directory" in str(e), f"错误消息不匹配: {e}"
            print("✅ 通过 - 正确抛出 IsADirectoryError")
            print(f"错误信息: {e}")

    async def test_05_user_cancel(self):
        """测试5: 用户取消（模拟）"""
        print("\n" + "="*60)
        print("测试5: 用户取消")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(filePath="cancel_test.txt", content="won't be written")
        # 不设置 _auto_confirm，模拟用户取消

        # 创建文件以便有 diff 显示
        (self.test_dir / "cancel_test.txt").write_text("original")

        # 通过 monkey patch 模拟用户输入 'n'
        import builtins
        original_input = builtins.input
        builtins.input = lambda: "n"

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 UserCancelledError"
        except UserCancelledError as e:
            assert "cancelled" in str(e).lower(), f"错误消息不匹配: {e}"
            print("✅ 通过 - 正确抛出 UserCancelledError")
            print(f"错误信息: {e}")
        finally:
            builtins.input = original_input

    async def test_06_absolute_path(self):
        """测试6: 绝对路径"""
        print("\n" + "="*60)
        print("测试6: 绝对路径")
        print("="*60)

        os.chdir(self.test_dir)

        abs_path = str(self.test_dir / "abs_test.txt")
        params = WriteParams(filePath=abs_path, content="absolute path content")
        params._auto_confirm = True

        result = await self.tool.execute(params)

        print(f"结果: {result}")
        assert "title" in result, f"结果缺少 title: {result.keys()}"
        # macOS 上 /var 是 /private/var 的符号链接，使用 Path.resolve() 比较
        actual_path = Path(result["metadata"]["filepath"]).resolve()
        expected_path = Path(abs_path).resolve()
        assert actual_path == expected_path, f"filepath 不匹配: {actual_path} != {expected_path}"

        # 验证文件
        content = (self.test_dir / "abs_test.txt").read_text()
        assert content == "absolute path content", f"文件内容不匹配: {content}"

        print("✅ 通过")

    async def test_07_relative_path(self):
        """测试7: 相对路径"""
        print("\n" + "="*60)
        print("测试7: 相对路径")
        print("="*60)

        os.chdir(self.test_dir / "subdir")

        params = WriteParams(filePath="../relative_test.txt", content="relative content")
        params._auto_confirm = True

        result = await self.tool.execute(params)

        assert "title" in result

        # 验证文件在正确的位置
        content = (self.test_dir / "relative_test.txt").read_text()
        assert content == "relative content"

        print("✅ 通过")

    async def test_08_write_empty_file(self):
        """测试8: 写入空文件"""
        print("\n" + "="*60)
        print("测试8: 写入空文件")
        print("="*60)

        os.chdir(self.test_dir)

        params = WriteParams(filePath="empty.txt", content="")
        params._auto_confirm = True

        result = await self.tool.execute(params)

        assert "title" in result

        # 验证文件存在且为空
        content = (self.test_dir / "empty.txt").read_text()
        assert content == ""

        print("✅ 通过")

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("开始 Write Tool 集成测试")
        print("="*60)

        self.setup_test_files()

        tests = [
            self.test_01_create_new_file,
            self.test_02_overwrite_existing_file,
            self.test_03_parent_directory_not_exists,
            self.test_04_path_is_directory,
            self.test_05_user_cancel,
            self.test_06_absolute_path,
            self.test_07_relative_path,
            self.test_08_write_empty_file,
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
    tester = TestWriteTool()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
