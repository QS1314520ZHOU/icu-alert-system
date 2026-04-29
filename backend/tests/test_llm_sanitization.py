import unittest

from app.services.llm_runtime import sanitize_llm_text


class LlmSanitizationTest(unittest.TestCase):
    def test_removes_complete_and_dangling_think_blocks(self):
        self.assertEqual(sanitize_llm_text("<think>hidden</think>\n临床结论"), "临床结论")
        self.assertEqual(sanitize_llm_text("临床意义\n<think\nhidden"), "临床意义")
        self.assertEqual(sanitize_llm_text("&lt;think&gt;hidden&lt;/think&gt;\n建议复查乳酸"), "建议复查乳酸")


if __name__ == "__main__":
    unittest.main()
