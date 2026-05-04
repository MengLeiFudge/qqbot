from pathlib import Path
import asyncio
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_actions import AiActionExecutor
from qqbot.services.ai_group_context_store import AiGroupContextStore
import qqbot.services.ai_orchestrator as ai_orchestrator_module
from qqbot.services.ai_orchestrator import AiOrchestrator, AiOrchestratorContext
from qqbot.services.codex_task_service import CodexProjectBinding, get_codex_project_by_id
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.message_normalizer import NormalizedMessage, NormalizedReply
from qqbot.services.settings_store import SettingsStore


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))


def test_orchestrator_schedules_private_message_to_self(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def run():
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            sleep=lambda seconds: asyncio.sleep(0),
            task_factory=task_factory,
        )
        orchestrator = AiOrchestrator(data_root=tmp_path, action_executor=executor)
        result = await orchestrator.handle(
            "1分钟后向我私聊“测试消息”",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="1分钟后向我私聊“测试消息”", outline="1分钟后向我私聊“测试消息”"),
        )
        assert result.handled is True
        assert "已安排" in result.text
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert bot.calls == [("send_private_msg", {"user_id": 10001, "message": "测试消息"})]


def test_orchestrator_records_user_style_preference(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "以后回复不要 markdown，短一点",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="以后回复不要 markdown，短一点", outline="以后回复不要 markdown，短一点"),
        )
    )

    assert result.handled is True
    assert "已记住" in result.text
    assert "不要 markdown，短一点" in "\n".join(result.extra_context)


def test_orchestrator_lists_enabled_group_plugins_locally(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    group_assistant = get_feature_by_menu_key("群管助手")
    assert group_assistant is not None
    store.set_group_feature_state(1163635014, group_assistant, True)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "本群启用了哪些插件",
            AiOrchestratorContext(actor_user_id="605738729", group_id="1163635014", is_admin=True),
            NormalizedMessage(text="本群启用了哪些插件", outline="本群启用了哪些插件"),
        )
    )

    assert result.handled is True
    assert "当前启用插件：" in result.text
    assert "群管助手" in result.text
    assert "智能问答" not in result.text


def test_orchestrator_uploads_latest_project_zip_for_admin_group(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bot = FakeBot()
    package = tmp_path / "repo" / "ModZips" / "FractionateEverything_2.3.0.zip"
    wrong_package = tmp_path / "repo" / "ModZips" / "GetDspData_1.0.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"zip")
    wrong_package.write_bytes(b"wrong")
    os.utime(package, (1000, 1000))
    os.utime(wrong_package, (2000, 2000))
    project = CodexProjectBinding(
        project_id="mlj_dspmods",
        display_name="MLJ_DSPmods",
        repo_path=str(tmp_path / "repo"),
    )

    def fake_resolve(*_args, **_kwargs):
        return type("Match", (), {"project": project})()

    monkeypatch.setattr(ai_orchestrator_module, "resolve_codex_project_for_text", fake_resolve)
    orchestrator = AiOrchestrator(
        data_root=tmp_path,
        action_executor=AiActionExecutor(bot=bot, data_root=tmp_path),
    )

    result = asyncio.run(
        orchestrator.handle(
            "上传最新分馏压缩包到群里",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="上传最新分馏压缩包到群里", outline="上传最新分馏压缩包到群里"),
        )
    )

    assert result.handled is True
    assert "已上传最新压缩包：FractionateEverything_2.3.0.zip" in result.text
    assert bot.calls == [
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        )
    ]


def test_orchestrator_rejects_latest_zip_upload_for_non_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "上传最新分馏压缩包到群里",
            AiOrchestratorContext(actor_user_id="10001", group_id="319567534", is_admin=False),
            NormalizedMessage(text="上传最新分馏压缩包到群里", outline="上传最新分馏压缩包到群里"),
        )
    )

    assert result.handled is True
    assert "只有作者或 Bot 管理员" in result.text


def test_orchestrator_requires_group_for_latest_zip_upload(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "上传最新分馏压缩包到群里",
            AiOrchestratorContext(actor_user_id="605738729", is_admin=True),
            NormalizedMessage(text="上传最新分馏压缩包到群里", outline="上传最新分馏压缩包到群里"),
        )
    )

    assert result.handled is True
    assert "需要在群聊里使用" in result.text


def test_orchestrator_requires_project_after_codex_keyword(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex", outline="codex"),
        )
    )

    assert result.handled is True
    assert "必须在 codex 后面写项目" in result.text
    assert "MLJ_DSPmods" in result.text


def test_orchestrator_rejects_unknown_codex_session_project(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex 不存在项目",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 不存在项目", outline="codex 不存在项目"),
        )
    )

    assert result.handled is True
    assert "没有找到 Codex 项目：不存在项目" in result.text


def test_orchestrator_enters_codex_session_mode_with_explicit_project(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )

    assert result.handled is True
    assert "已进入 Codex 模式 CODEX-S0001" in result.text
    assert "MLJ_DSPmods" in result.text
    assert "不走普通 AI" in result.text


def test_orchestrator_bot_admins_share_active_codex_session(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "共享会话回复。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        await orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
        result = await orchestrator.handle(
            "另一个管理员继续讨论",
            AiOrchestratorContext(actor_user_id="10001", group_id="319567534", is_admin=True),
            NormalizedMessage(text="另一个管理员继续讨论", outline="另一个管理员继续讨论"),
        )
        assert result.handled is True
        assert "共享会话回复" in result.text

    asyncio.run(run())

    assert requests[0].session_id == "CODEX-S0001"
    assert requests[0].project.project_id == "mlj_dspmods"


def test_orchestrator_rejects_new_project_when_group_session_is_active(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)

    asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            context,
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )
    result = asyncio.run(
        orchestrator.handle(
            "codex qqbot",
            context,
            NormalizedMessage(text="codex qqbot", outline="codex qqbot"),
        )
    )

    assert result.handled is True
    assert "本群已有 Codex 模式 CODEX-S0001" in result.text
    assert "退出codex" in result.text


def test_orchestrator_lets_non_admin_chat_fall_back_during_active_group_codex_session(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )
    result = asyncio.run(
        orchestrator.handle(
            "我也说一句",
            AiOrchestratorContext(actor_user_id="10002", group_id="319567534", is_admin=False),
            NormalizedMessage(text="我也说一句", outline="我也说一句"),
        )
    )

    assert result.handled is False
    assert result.text == ""


def test_orchestrator_rejects_non_admin_codex_control_in_active_group_session(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )
    result = asyncio.run(
        orchestrator.handle(
            "执行",
            AiOrchestratorContext(actor_user_id="10002", group_id="319567534", is_admin=False),
            NormalizedMessage(text="执行", outline="执行"),
        )
    )

    assert result.handled is True
    assert "只有作者或 Bot 管理员才能使用 Codex 模式" in result.text


def test_orchestrator_forwards_active_codex_session_turn_to_codex(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "我需要先看版本文件和 R2 兼容约束。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        result = await orchestrator.handle(
            "分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            context,
            NormalizedMessage(
                text="分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
                outline="分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            ),
        )
        assert result.handled is True
        assert "我需要先看版本文件" in result.text

    asyncio.run(run())

    assert requests[0].mode == "discuss"
    assert requests[0].project.project_id == "mlj_dspmods"
    assert "修订版本号" in requests[0].prompt


def test_orchestrator_forwards_reply_anchored_group_context_to_codex(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "我会看引用上下文。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        store = AiGroupContextStore(tmp_path)
        for index, text in enumerate(
            [
                "前置消息A",
                "前置消息B",
                "上传最新分馏压缩包到群里",
                "机器人上传了 GetDspData",
                "后续追问",
            ],
            start=1,
        ):
            store.append_message(
                group_id="319567534",
                user_id=f"1000{index}",
                sender_name=f"玩家{index}",
                text=text,
                timestamp=index,
                message_id=200 + index,
            )
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        result = await orchestrator.handle(
            "看一下聊天记录，为什么传错了？",
            context,
            NormalizedMessage(
                text="看一下聊天记录，为什么传错了？",
                outline="看一下聊天记录，为什么传错了？",
                reply=NormalizedReply(
                    user_id="10003",
                    sender_name="玩家3",
                    message=NormalizedMessage(text="上传最新分馏压缩包到群里", outline="上传最新分馏压缩包到群里"),
                    message_id="203",
                ),
            ),
        )
        assert result.handled is True

    asyncio.run(run())

    assert requests[0].source_context[0] == "引用消息及其附近群聊记录："
    assert "前置消息B" in "\n".join(requests[0].source_context)
    assert "【引用】玩家3(10003): 上传最新分馏压缩包到群里" in requests[0].source_context
    assert "机器人上传了 GetDspData" in "\n".join(requests[0].source_context)


def test_orchestrator_executes_active_codex_session_with_same_transcript(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "已修改并验证。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        await orchestrator.handle(
            "先讨论版本号策略",
            context,
            NormalizedMessage(text="先讨论版本号策略", outline="先讨论版本号策略"),
        )
        result = await orchestrator.handle(
            "执行",
            context,
            NormalizedMessage(text="执行", outline="执行"),
        )
        assert result.handled is True
        assert "已修改并验证" in result.text

    asyncio.run(run())

    assert requests[-1].mode == "execute"
    assert ("user", "先讨论版本号策略") in requests[-1].transcript


def test_orchestrator_rejects_execute_when_same_project_is_running(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    store = orchestrator._codex_session_store()
    dsp_project = get_codex_project_by_id("mlj_dspmods")
    assert dsp_project is not None
    running = store.create_session(
        project=dsp_project,
        actor_user_id="605738729",
        group_id="100",
    )
    store.mark_status(running.session_id, "running")

    asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="10001", group_id="200", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )
    result = asyncio.run(
        orchestrator.handle(
            "执行",
            AiOrchestratorContext(actor_user_id="10001", group_id="200", is_admin=True),
            NormalizedMessage(text="执行", outline="执行"),
        )
    )

    assert result.handled is True
    assert "已有 Codex 会话正在执行" in result.text
    assert "CODEX-S0001" in result.text


def test_orchestrator_restarts_after_successful_qqbot_session_execute(tmp_path: Path) -> None:
    tasks = []
    restart_calls = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_codex_runner(request):
        return type("Result", (), {"ok": True, "message": "已修改并提交。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(
            data_root=tmp_path,
            codex_session_runner=fake_codex_runner,
            self_restart_scheduler=lambda: restart_calls.append("restart"),
            sleep=lambda _seconds: asyncio.sleep(0),
            task_factory=task_factory,
        )
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="1163635014", is_admin=True)
        await orchestrator.handle("codex qqbot", context, NormalizedMessage(text="codex qqbot", outline="codex qqbot"))
        result = await orchestrator.handle(
            "执行",
            context,
            NormalizedMessage(text="执行", outline="执行"),
        )
        assert result.handled is True
        assert "已安排 Bot 重启" in result.text
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert restart_calls == ["restart"]
    notices = tmp_path / "ai" / "codex_self_update_notices.json"
    assert "1163635014" in notices.read_text(encoding="utf-8")


def test_orchestrator_uploads_codex_zip_artifacts_after_execute(tmp_path: Path) -> None:
    bot = FakeBot()
    package = tmp_path / "repo" / "ModZips" / "FractionateEverything_2.3.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"zip")
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": f"已生成产物：{package}", "exit_code": 0})()

    async def run() -> None:
        executor = AiActionExecutor(bot=bot, data_root=tmp_path)
        orchestrator = AiOrchestrator(
            data_root=tmp_path,
            action_executor=executor,
            codex_session_runner=fake_codex_runner,
        )
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        # 测试用临时目录覆盖项目路径，避免依赖真实 MLJ_DSPmods 产物。
        active = orchestrator._codex_session_store().get_active_session(
            actor_user_id="605738729",
            group_id="319567534",
        )
        assert active is not None
        result = await orchestrator._upload_codex_artifacts_from_text(
            text=f"已生成产物：{package}",
            project_repo_path=str(tmp_path / "repo"),
            context=context,
        )
        assert result == 1

    asyncio.run(run())

    assert bot.calls == [
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        )
    ]


def test_orchestrator_exits_codex_session_mode(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
    asyncio.run(orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏")))

    result = asyncio.run(
        orchestrator.handle(
            "退出codex",
            context,
            NormalizedMessage(text="退出codex", outline="退出codex"),
        )
    )

    assert result.handled is True
    assert "已退出 Codex 模式" in result.text


def test_orchestrator_creates_codex_draft_for_bound_dsp_group(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(_request):
        return type("Result", (), {"ok": True, "message": "完成", "exit_code": 0})()

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        orchestrator = AiOrchestrator(data_root=tmp_path, action_executor=executor)
        result = await orchestrator.handle(
            "看一下这个",
            AiOrchestratorContext(
                actor_user_id="605738729",
                group_id="319567534",
                is_admin=True,
            ),
            NormalizedMessage(
                text="看一下这个",
                outline="[@1443944862] 看一下这个",
                reply=NormalizedReply(
                    user_id="568930249",
                    sender_name="玩家",
                    message=NormalizedMessage(
                        text="",
                        outline=(
                            "System.IndexOutOfRangeException "
                            "at FE.Logic.Manager.BuildingManager.GetExtraState "
                            "FractionateEverything"
                        ),
                    ),
                ),
            ),
        )
        assert result.handled is True
        assert "已创建 Codex 草稿 CODEX-0001" in result.text
        assert "MLJ_DSPmods" in result.text
        assert tasks == []

    asyncio.run(run())

    assert bot.calls == []


def test_orchestrator_routes_factorio_quality_ship_request_to_factorio_repo(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []
    requests = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "完成", "exit_code": 0})()

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        orchestrator = AiOrchestrator(data_root=tmp_path, action_executor=executor)
        result = await orchestrator.handle(
            "异星模组品质飞船的计算公式改成新的倍率",
            AiOrchestratorContext(
                actor_user_id="605738729",
                group_id="319567534",
                is_admin=True,
            ),
            NormalizedMessage(
                text="异星模组品质飞船的计算公式改成新的倍率",
                outline="异星模组品质飞船的计算公式改成新的倍率",
            ),
        )
        assert result.handled is True
        assert "已创建 Codex 草稿 CODEX-0001" in result.text

    asyncio.run(run())

    assert requests == []


def test_orchestrator_executes_existing_codex_draft_when_confirmed(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []
    requests = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "完成", "exit_code": 0})()

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        orchestrator = AiOrchestrator(data_root=tmp_path, action_executor=executor)
        context = AiOrchestratorContext(
            actor_user_id="605738729",
            group_id="319567534",
            is_admin=True,
        )
        first = await orchestrator.handle(
            "异星模组品质飞船的计算公式改成新的倍率",
            context,
            NormalizedMessage(
                text="异星模组品质飞船的计算公式改成新的倍率",
                outline="异星模组品质飞船的计算公式改成新的倍率",
            ),
        )
        assert "CODEX-0001" in first.text
        result = await orchestrator.handle(
            "执行 CODEX-0001",
            context,
            NormalizedMessage(text="执行 CODEX-0001", outline="执行 CODEX-0001"),
        )
        assert result.handled is True
        assert "已启动 Codex 修复任务" in result.text
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert requests[0].project.project_id == "factorio_mods"
    assert "异星模组品质飞船" in requests[0].prompt
    assert bot.calls[0][0] == "send_group_msg"
    assert "Codex 修复任务成功" in bot.calls[0][1]["message"]


def test_orchestrator_appends_followup_to_recent_codex_draft(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)

    first = asyncio.run(
        orchestrator.handle(
            "改一下分馏，先讨论计算公式",
            context,
            NormalizedMessage(text="改一下分馏，先讨论计算公式", outline="改一下分馏，先讨论计算公式"),
        )
    )
    second = asyncio.run(
        orchestrator.handle(
            "补充一下，公式具体改成 A/B",
            context,
            NormalizedMessage(text="补充一下，公式具体改成 A/B", outline="补充一下，公式具体改成 A/B"),
        )
    )

    assert "CODEX-0001" in first.text
    assert "已补充 Codex 草稿 CODEX-0001" in second.text


def test_orchestrator_treats_revision_version_request_as_codex_draft(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(
                text="分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
                outline="分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            ),
        )
    )

    assert result.handled is True
    assert "已创建 Codex 草稿 CODEX-0001" in result.text
    assert "MLJ_DSPmods" in result.text
    assert "当前不会执行" in result.text
    assert "先确认" in result.text
    assert "继续补充需求" in result.text


def test_orchestrator_learns_codex_project_alias_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "品质飞船是MLJ_Factorio_Mods的一个内容",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(
                text="品质飞船是MLJ_Factorio_Mods的一个内容",
                outline="品质飞船是MLJ_Factorio_Mods的一个内容",
            ),
        )
    )

    assert result.handled is True
    assert "已记住" in result.text


def test_orchestrator_creates_requirement_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "记一下这个需求：shapez 支持 /chart 短代码",
            AiOrchestratorContext(actor_user_id="605738729", group_id="1163635014", is_admin=True),
            NormalizedMessage(
                text="记一下这个需求：shapez 支持 /chart 短代码",
                outline="记一下这个需求：shapez 支持 /chart 短代码",
            ),
        )
    )

    assert result.handled is True
    assert "REQ-0001" in result.text
    assert "shapez" in result.text


def test_orchestrator_lists_requirements_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", is_admin=True)
    asyncio.run(
        orchestrator.handle(
            "记录需求：shapez 支持 /chart",
            context,
            NormalizedMessage(text="记录需求：shapez 支持 /chart", outline="记录需求：shapez 支持 /chart"),
        )
    )

    result = asyncio.run(
        orchestrator.handle(
            "需求列表",
            context,
            NormalizedMessage(text="需求列表", outline="需求列表"),
        )
    )

    assert result.handled is True
    assert "REQ-0001" in result.text
    assert "shapez 支持 /chart" in result.text


def test_orchestrator_renders_shapez_code(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "帮我画一下 CrRgSbWy",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="帮我画一下 CrRgSbWy", outline="帮我画一下 CrRgSbWy"),
        )
    )

    assert result.handled is True
    assert result.image_path is not None
    assert Path(result.image_path).exists()
    assert "CrRgSbWy" in result.text


def test_orchestrator_returns_unhandled_for_general_chat(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "今天聊什么",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="今天聊什么", outline="今天聊什么"),
        )
    )

    assert result.handled is False
