from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_diagnostics import (
    AiAttemptDiagnostics,
    AiDiagnosticsStore,
    build_ai_diagnostics_record,
)


def test_ai_diagnostics_store_appends_and_summarizes_recent_records(tmp_path: Path) -> None:
    store = AiDiagnosticsStore(tmp_path, max_records=2)

    store.append(
        build_ai_diagnostics_record(
            profile="xiaomi",
            provider="xiaomi_mimo",
            model="mimo-v2.5-pro",
            scope="private",
            group_id="",
            user_id="10001",
            fallback=False,
            fallback_reason="",
            prompt_chars=10,
            context_chars=20,
            history_messages=2,
            image_count=1,
            local_prepare_seconds=0.2,
            total_seconds=1.2,
            attempts=(
                AiAttemptDiagnostics(
                    attempt=1,
                    timeout_seconds=12.0,
                    result="success",
                    total_seconds=1.0,
                    first_token_seconds=0.4,
                    completion_tokens=5,
                    output_chars=20,
                ),
            ),
            now=100,
        )
    )
    store.append(
        build_ai_diagnostics_record(
            profile="xiaomi",
            provider="xiaomi_mimo",
            model="mimo-v2.5-pro",
            scope="group",
            group_id="20002",
            user_id="10001",
            fallback=False,
            fallback_reason="",
            prompt_chars=8,
            context_chars=16,
            history_messages=1,
            image_count=0,
            local_prepare_seconds=0.4,
            total_seconds=1.4,
            queue_wait_seconds=0.3,
            prepare_stages={"context": 0.2, "history": 0.1},
            attempts=(
                AiAttemptDiagnostics(
                    attempt=1,
                    timeout_seconds=0.01,
                    result="timeout",
                    total_seconds=0.01,
                    error_type="TimeoutError",
                ),
                AiAttemptDiagnostics(
                    attempt=2,
                    timeout_seconds=45.0,
                    result="success",
                    total_seconds=1.0,
                    first_token_seconds=0.2,
                    completion_tokens=10,
                    output_chars=30,
                ),
            ),
            now=101,
        )
    )
    store.append(
        build_ai_diagnostics_record(
            profile="hicode",
            provider="openai_compatible",
            model="gpt-5.5",
            scope="private",
            group_id="",
            user_id="10002",
            fallback=True,
            fallback_reason="empty",
            prompt_chars=6,
            context_chars=0,
            history_messages=0,
            image_count=0,
            local_prepare_seconds=0.6,
            total_seconds=0.8,
            queue_wait_seconds=0.7,
            prepare_stages={"context": 0.4, "history": 0.2},
            attempts=(
                AiAttemptDiagnostics(
                    attempt=1,
                    timeout_seconds=12.0,
                    result="empty",
                    total_seconds=0.8,
                    first_token_seconds=None,
                    completion_tokens=0,
                    output_chars=0,
                ),
            ),
            now=102,
        )
    )

    summary = store.summary(limit=10)

    assert summary["count"] == 2
    assert summary["success_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["retry_success_count"] == 1
    assert summary["empty_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["avg_local_prepare_seconds"] == 0.5
    assert summary["avg_queue_wait_seconds"] == 0.5
    assert summary["avg_prepare_stages"] == {"context": 0.30000000000000004, "history": 0.15000000000000002}
    assert summary["avg_total_seconds"] == 1.1
    assert summary["avg_first_token_seconds"] == 0.2
    assert summary["p95_first_token_seconds"] == 0.2
    assert summary["avg_tokens_per_second"] == 10.0
    assert [record["timestamp"] for record in summary["records"]] == [102, 101]
    assert [record["queue_wait_seconds"] for record in summary["records"]] == [0.7, 0.3]
    assert summary["records"][0]["prepare_stages"] == {"context": 0.4, "history": 0.2}
