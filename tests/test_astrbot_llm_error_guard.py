"""Focused regression tests for group LLM error owner notifications."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.llm_error_guard import LlmErrorNoticeCooldown
from astrbot_plugin_qqbot_features.llm_error_guard import build_llm_error_notice
from astrbot_plugin_qqbot_features.llm_error_guard import sanitize_llm_error_text


class LlmErrorGuardTest(unittest.TestCase):
    """Verify safe classification and process-local notification cooldown behavior."""

    def test_core_llm_error_is_recognized_without_exposing_raw_detail(self) -> None:
        """Core error text becomes a fixed safe owner notice."""
        notice = build_llm_error_notice(
            "LLM 响应错误: All chat models failed: APITimeoutError: Request timed out. prompt=私密原话",
            self_id="1443944862",
            group_id="123456",
        )

        self.assertIsNotNone(notice)
        assert notice is not None
        self.assertEqual(notice.category, "APITimeoutError")
        self.assertIn("机器人 QQ: 1443944862", notice.message)
        self.assertIn("来源群: 123456", notice.message)
        self.assertIn("摘要: 上游请求超时", notice.message)
        self.assertNotIn("私密原话", notice.message)
        self.assertNotIn("Request timed out", notice.message)

    def test_non_core_text_is_not_intercepted(self) -> None:
        """Ordinary replies and text that merely mentions the prefix pass through."""
        self.assertIsNone(
            build_llm_error_notice(
                "这是普通回复。",
                self_id="1443944862",
                group_id="123456",
            )
        )
        self.assertIsNone(
            build_llm_error_notice(
                "用户引用了 LLM 响应错误: 但这不是 Core 错误结果",
                self_id="1443944862",
                group_id="123456",
            )
        )

    def test_known_error_class_normalizes_volatile_details(self) -> None:
        """Request IDs and provider wording do not split one timeout issue."""
        first = build_llm_error_notice(
            "LLM 响应错误: APITimeoutError: request_id=req-one timeout",
            self_id="1443944862",
            group_id="100",
        )
        second = build_llm_error_notice(
            "LLM 响应错误: All models failed; APITimeoutError trace_id=req-two",
            self_id="2629227874",
            group_id="200",
        )

        assert first is not None and second is not None
        self.assertEqual(first.key, second.key)
        self.assertNotEqual(first.message, second.message)

    def test_distinct_error_classes_have_independent_keys(self) -> None:
        """Authentication and timeout failures remain separately eligible."""
        timeout = build_llm_error_notice(
            "LLM 响应错误: APITimeoutError: timeout",
            self_id="1",
            group_id="2",
        )
        auth = build_llm_error_notice(
            "LLM 响应错误: AuthenticationError: invalid credentials",
            self_id="1",
            group_id="2",
        )

        assert timeout is not None and auth is not None
        self.assertNotEqual(timeout.key, auth.key)
        self.assertIn("上游鉴权失败", auth.message)

    def test_http_status_is_a_safe_deduplication_discriminator(self) -> None:
        """Status failures retain only the safe numeric HTTP status."""
        notice = build_llm_error_notice(
            "LLM 响应错误: APIStatusError: HTTP 503 body=private",
            self_id="1",
            group_id="2",
        )

        assert notice is not None
        self.assertEqual(notice.category, "APIStatusError (HTTP 503)")
        self.assertIn("上游返回 HTTP 503", notice.message)
        self.assertNotIn("private", notice.message)

    def test_credentials_are_removed_before_fallback_normalization(self) -> None:
        """Common key and authorization forms cannot survive sanitization."""
        sanitized = sanitize_llm_error_text(
            "api_key=sk-example123456 Authorization: Bearer bearer-secret "
            "password='password-secret' token=token-secret"
        )

        self.assertNotIn("sk-example123456", sanitized)
        self.assertNotIn("bearer-secret", sanitized)
        self.assertNotIn("password-secret", sanitized)
        self.assertNotIn("token-secret", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_unknown_error_key_ignores_volatile_ids_and_credentials(self) -> None:
        """Unknown failures deduplicate after redaction without exposing source text."""
        first = build_llm_error_notice(
            "LLM 响应错误: provider unavailable request_id=req-one api_key=sk-example123456",
            self_id="1",
            group_id="2",
        )
        second = build_llm_error_notice(
            "LLM 响应错误: provider unavailable request_id=req-two api_key=sk-another123456",
            self_id="3",
            group_id="4",
        )

        assert first is not None and second is not None
        self.assertEqual(first.key, second.key)
        self.assertEqual(first.category, "UnknownLlmError")
        self.assertNotIn("provider unavailable", first.message)
        self.assertNotIn("sk-", first.message)

    def test_cooldown_is_global_per_key_and_expires_at_600_seconds(self) -> None:
        """One limiter shares claims across bot/group context and reopens at expiry."""
        now = [1000.0]
        limiter = LlmErrorNoticeCooldown(clock=lambda: now[0])

        self.assertTrue(limiter.claim("classes:apitimeouterror"))
        self.assertFalse(limiter.claim("classes:apitimeouterror"))
        self.assertTrue(limiter.claim("classes:authenticationerror"))
        now[0] += 599.999
        self.assertFalse(limiter.claim("classes:apitimeouterror"))
        now[0] += 0.001
        self.assertTrue(limiter.claim("classes:apitimeouterror"))


if __name__ == "__main__":
    unittest.main()
