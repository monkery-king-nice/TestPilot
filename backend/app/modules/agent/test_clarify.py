import unittest
from unittest.mock import Mock
from .clarify import ModelError, clarify


class ClarifyTest(unittest.TestCase):
    def test_questions_keep_source_text(self):
        text = "登录后显示我的信息"
        item = {"quote": "我的信息", "question": "具体显示哪些字段？"}
        self.assertEqual(clarify(text, lambda _: {"questions": [item, item]}),
                         {"status": "NEEDS_INFO", "questions": [item]})

    def test_answered(self):
        self.assertEqual(clarify("显示用户编号", lambda _: {"questions": []}),
                         {"status": "READY", "questions": []})

    def test_invalid_response_never_means_ready(self):
        for response in ({}, {"questions": None}, {"questions": [{"quote": "邮箱", "question": "哪个邮箱？"}]}):
            with self.subTest(response=response), self.assertRaises(ModelError):
                clarify("登录", lambda _: response)

    def test_empty_input_does_not_call_model(self):
        provider = Mock()
        with self.assertRaises(ValueError):
            clarify(" ", provider)
        provider.assert_not_called()
