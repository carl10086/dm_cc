"""Read Tool 集成测试 - 对齐 opencode 异常处理风格

测试 ReadTool 的各种场景：
1. 正常读取文件
2. 读取目录
3. 范围限制 (offset/limit)
4. 错误处理（通过异常）
5. 边界情况
"""

import asyncio
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dm_cc.tools.read import ReadTool, ReadParams


class TestReadTool:
    """Read Tool 测试类"""

    def __init__(self):
        self.tool = ReadTool()
        self.test_dir = Path(tempfile.mkdtemp(prefix="dm_cc_test_"))
        print(f"测试目录: {self.test_dir}")

    def setup_test_files(self):
        """创建测试文件"""
        os.chdir(self.test_dir)

        # 1. 普通文本文件
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

        # 2. 大文件 (用于测试截断)
        large_content = "\n".join([f"Line {i:04d}: This is test content" for i in range(1, 2500)])
        (self.test_dir / "large.txt").write_text(large_content)

        # 3. 超长行文件
        long_line = "A" * 3000
        (self.test_dir / "long_line.txt").write_text(f"Short line\n{long_line}\nAnother line")

        # 4. 二进制文件 (用于测试拒绝)
        (self.test_dir / "binary.bin").write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        # 5. 子目录结构
        (self.test_dir / "subdir").mkdir()
        (self.test_dir / "subdir" / "nested.py").write_text("# nested file")
        (self.test_dir / "subdir" / "data.json").write_text('{"key": "value"}')

        # 6. 空文件
        (self.test_dir / "empty.txt").write_text("")

    async def test_01_read_normal_file(self):
        """测试1: 正常读取文件"""
        print("\n" + "="*60)
        print("测试1: 正常读取文件")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="hello.py")
        result = await self.tool.execute(params)

        assert "title" in result, "返回应包含 title"
        assert "output" in result, "返回应包含 output"
        assert result["title"] == "hello.py", f"title 应为 hello.py, 实际是 {result['title']}"
        assert "<path>" in result["output"], "output 应包含 <path> 标签"
        assert "<type>file</type>" in result["output"], "output 应包含 <type>file</type>"
        assert "<content>" in result["output"], "output 应包含 <content> 标签"
        assert "1: import os" in result["output"], "应包含行号"
        assert "(End of file - total 10 lines)" in result["output"], "应显示总行数"

        print("✅ 通过")
        print(f"输出预览:\n{result['output'][:500]}...")

    async def test_02_read_directory(self):
        """测试2: 读取目录"""
        print("\n" + "="*60)
        print("测试2: 读取目录")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="subdir")
        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result
        assert "<type>directory</type>" in result["output"], "output 应标识为目录"
        assert "<entries>" in result["output"], "output 应包含 <entries>"
        assert "nested.py" in result["output"], "应包含嵌套文件"
        assert "data.json" in result["output"], "应包含 json 文件"

        print("✅ 通过")
        print(f"输出:\n{result['output']}")

    async def test_03_offset_and_limit(self):
        """测试3: offset 和 limit 参数"""
        print("\n" + "="*60)
        print("测试3: offset 和 limit 参数")
        print("="*60)

        os.chdir(self.test_dir)

        # 测试 offset
        params = ReadParams(filePath="hello.py", offset=3, limit=5)
        result = await self.tool.execute(params)

        assert "output" in result
        # 第3行是空行，第4行是 def main()
        assert "4: def main():" in result["output"] or "3: " in result["output"], "应包含偏移后的内容"
        assert "1: import" not in result["output"], "不应包含第1行"

        print("✅ offset 测试通过")

        # 测试 limit 截断
        params = ReadParams(filePath="large.txt", offset=1, limit=100)
        result = await self.tool.execute(params)

        assert "output" in result
        assert "Line 0100:" in result["output"], "应读到第100行"
        assert "Line 0101:" not in result["output"], "不应包含第101行"

        print("✅ limit 测试通过")

    async def test_04_file_not_found(self):
        """测试4: 文件不存在（应抛出异常）"""
        print("\n" + "="*60)
        print("测试4: 文件不存在")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="nonexistent.py")

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError as e:
            assert "File not found" in str(e), f"错误消息应包含 'File not found': {e}"
            print("✅ 通过 - 正确抛出 FileNotFoundError")
            print(f"错误信息: {e}")

    async def test_05_binary_file(self):
        """测试5: 二进制文件（应抛出异常）"""
        print("\n" + "="*60)
        print("测试5: 二进制文件")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="binary.bin")

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "Cannot read binary file" in str(e), f"错误消息应包含 'Cannot read binary file': {e}"
            print("✅ 通过 - 正确拒绝二进制文件")
            print(f"错误信息: {e}")

    async def test_06_long_line_truncation(self):
        """测试6: 超长行截断"""
        print("\n" + "="*60)
        print("测试6: 超长行截断")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="long_line.txt")
        result = await self.tool.execute(params)

        assert "output" in result
        # 检查是否处理了超长行（应该有 ...）
        assert "..." in result["output"], "超长行应被截断并显示 ..."
        print("✅ 通过")
        print(f"输出:\n{result['output'][:300]}...")

    async def test_07_large_file_truncation(self):
        """测试7: 大文件截断提示"""
        print("\n" + "="*60)
        print("测试7: 大文件截断提示")
        print("="*60)

        os.chdir(self.test_dir)

        # 读取大文件但不限制（默认2000行）
        params = ReadParams(filePath="large.txt")
        result = await self.tool.execute(params)

        assert "output" in result
        # 应该提示还有更多内容或被截断
        content_lower = result["output"].lower()
        assert any(word in content_lower for word in ["more", "total", "truncated"]), "应提示截断或总行数"

        print("✅ 通过")
        # 显示最后几行
        lines = result["output"].split("\n")
        print(f"最后几行:\n{'\n'.join(lines[-5:])}")

    async def test_08_relative_path(self):
        """测试8: 相对路径"""
        print("\n" + "="*60)
        print("测试8: 相对路径")
        print("="*60)

        # 在子目录中运行
        os.chdir(self.test_dir / "subdir")

        params = ReadParams(filePath="../hello.py")
        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result
        assert "hello.py" in result["output"], "应包含文件名"

        print("✅ 通过")

    async def test_09_absolute_path(self):
        """测试9: 绝对路径"""
        print("\n" + "="*60)
        print("测试9: 绝对路径")
        print("="*60)

        os.chdir(self.test_dir)

        abs_path = str(self.test_dir / "hello.py")
        params = ReadParams(filePath=abs_path)
        result = await self.tool.execute(params)

        assert "title" in result
        assert "output" in result

        print("✅ 通过")

    async def test_10_offset_out_of_range(self):
        """测试10: offset 超出范围（应抛出异常）"""
        print("\n" + "="*60)
        print("测试10: offset 超出范围")
        print("="*60)

        os.chdir(self.test_dir)

        params = ReadParams(filePath="hello.py", offset=100)

        try:
            await self.tool.execute(params)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "out of range" in str(e).lower(), f"错误消息应包含 'out of range': {e}"
            print("✅ 通过 - 正确抛出 ValueError")
            print(f"错误信息: {e}")

    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("开始 Read Tool 集成测试")
        print("="*60)

        self.setup_test_files()

        tests = [
            self.test_01_read_normal_file,
            self.test_02_read_directory,
            self.test_03_offset_and_limit,
            self.test_04_file_not_found,
            self.test_05_binary_file,
            self.test_06_long_line_truncation,
            self.test_07_large_file_truncation,
            self.test_08_relative_path,
            self.test_09_absolute_path,
            self.test_10_offset_out_of_range,
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
    tester = TestReadTool()
    success = await tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
