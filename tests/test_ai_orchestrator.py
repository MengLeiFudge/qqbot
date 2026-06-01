from pathlib import Path
import asyncio
import hashlib
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
from qqbot.services.ai_orchestrator import STYLE_CONTROL_REPLY_MESSAGE
from qqbot.services.codex_task_service import (
    CodexProgressEvent,
    CodexProjectBinding,
    CodexTaskResult,
    get_codex_project_by_id,
)
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.message_normalizer import NormalizedMessage, NormalizedReply
from qqbot.services.settings_store import SettingsStore


class FakeDrawClient:
    requests = []

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def draw(self, request):
        FakeDrawClient.requests.append((self.api_key, request))
        return type(
            "DrawResult",
            (),
            {
                "image_url": "https://example.com/generated.png",
                "text": "",
                "total_seconds": 1.0,
            },
        )()


class FakeBot:
    self_id = "114514"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.group_files: list[dict[str, object]] = []

    async def call_api(self, api: str, **data: object) -> object:
        self.calls.append((api, data))
        if api == "get_group_root_files":
            return {"files": list(self.group_files)}
        if api == "upload_group_file":
            return {"message_id": 24680}
        return None


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


def test_orchestrator_rejects_user_style_preference_update(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "以后回复不要 markdown，短一点",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="以后回复不要 markdown，短一点", outline="以后回复不要 markdown，短一点"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "预设" not in result.text
    assert "人格" not in result.text
    assert "全局随机轮换" not in result.text
    assert "4:00" not in result.text
    assert orchestrator.styles.get_user_preferences("10001") == ()
    assert "当前用户回复偏好" not in "\n".join(result.extra_context)


def test_orchestrator_rejects_group_style_preference_update(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    update = asyncio.run(
        orchestrator.handle(
            "你要说话结尾带一个喵",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="你要说话结尾带一个喵", outline="你要说话结尾带一个喵"),
        )
    )
    later = asyncio.run(
        orchestrator.handle(
            "今天天气怎么样",
            AiOrchestratorContext(actor_user_id="10002", group_id="516286670"),
            NormalizedMessage(text="今天天气怎么样", outline="今天天气怎么样"),
        )
    )

    assert update.handled is True
    assert update.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "预设" not in update.text
    assert "人格" not in update.text
    assert "全局随机轮换" not in update.text
    assert later.handled is False
    joined = "\n".join(later.extra_context)
    assert "身份设定：" in joined
    assert "本群回复偏好" not in joined
    assert "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则" in joined


def test_orchestrator_rejects_user_style_control_request(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "切换御姐风格",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="切换御姐风格", outline="切换御姐风格"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "12:00" not in result.text
    assert "可切换" not in result.text
    assert "人格" not in result.text


def test_orchestrator_rejects_unknown_style_control_without_alias_resolution(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "切换侦探风格",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="切换侦探风格", outline="切换侦探风格"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "侦探风格" not in result.text
    assert "可切换" not in result.text
    assert "人格" not in result.text


def test_orchestrator_rejects_group_style_control(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "设置本群风格谜语人",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670", is_admin=False),
            NormalizedMessage(text="设置本群风格谜语人", outline="设置本群风格谜语人"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "20:00" not in result.text


def test_orchestrator_rejects_group_style_control_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "设置本群风格谜语人",
            AiOrchestratorContext(actor_user_id="605738729", group_id="516286670", is_admin=True),
            NormalizedMessage(text="设置本群风格谜语人", outline="设置本群风格谜语人"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE


def test_orchestrator_rejects_style_control_with_extra_preference(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "猫娘风格，但是回复短一点",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="猫娘风格，但是回复短一点", outline="猫娘风格，但是回复短一点"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE


def test_orchestrator_rejects_style_control_list_request(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "你现在可预设的风格有哪些？",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="你现在可预设的风格有哪些？", outline="你现在可预设的风格有哪些？"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "猫娘风格" not in result.text
    assert "侦探风格" not in result.text
    assert "切换时间点" not in result.text
    assert "关键词：" not in result.text
    assert "用法：" not in result.text
    assert "常规风格" not in result.text
    assert "切换御姐风格" not in result.text


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


def test_orchestrator_routes_orbital_ring_domain_question_to_readonly_codex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests = []
    project = CodexProjectBinding(
        project_id="orbital_ring",
        display_name="OrbitalRing-MOD",
        repo_path=str(tmp_path / "OrbitalRing-MOD"),
    )

    def fake_resolve(*_args, **_kwargs):
        return type("Match", (), {"project": project})()

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "DOMAIN-QA Codex：\n隐藏科技要按 data/techs.json 里的 IsHiddenTech 字段查喵"})()

    monkeypatch.setattr(ai_orchestrator_module, "resolve_codex_project_for_text", fake_resolve)
    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)

    result = asyncio.run(
        orchestrator.handle(
            "隐藏科技都有什么",
            AiOrchestratorContext(actor_user_id="10001", group_id="1035445959"),
            NormalizedMessage(text="隐藏科技都有什么", outline="隐藏科技都有什么"),
        )
    )

    assert result.handled is True
    assert result.text == "隐藏科技要按 data/techs.json 里的 IsHiddenTech 字段查喵"
    assert len(requests) == 1
    request = requests[0]
    assert request.project.project_id == "orbital_ring"
    assert request.group_id == "1035445959"
    assert request.mode == "discuss"
    assert request.timeout_seconds == 120
    assert request.progress_callback is None
    assert "只读资料查询" in request.prompt
    assert "当前项目目录" in request.prompt
    assert "源码" in request.prompt
    assert "data" in request.prompt
    assert "最终只输出可以直接发到 QQ 群里的答案" in request.prompt
    assert "隐藏科技都有什么" in request.prompt


def test_orchestrator_routes_fe_domain_question_to_readonly_codex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests = []
    project = CodexProjectBinding(
        project_id="mlj_dspmods",
        display_name="MLJ_DSPmods",
        repo_path=str(tmp_path / "MLJ_DSPmods"),
    )

    def fake_resolve(*_args, **_kwargs):
        return type("Match", (), {"project": project})()

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "物品堆叠升级要查 MLJ_DSPmods 源码里的堆叠科技逻辑喵"})()

    monkeypatch.setattr(ai_orchestrator_module, "resolve_codex_project_for_text", fake_resolve)
    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)

    result = asyncio.run(
        orchestrator.handle(
            "物品堆叠怎么升级",
            AiOrchestratorContext(actor_user_id="10001", group_id="319567534"),
            NormalizedMessage(text="物品堆叠怎么升级", outline="物品堆叠怎么升级"),
        )
    )

    assert result.handled is True
    assert result.text == "物品堆叠升级要查 MLJ_DSPmods 源码里的堆叠科技逻辑喵"
    assert len(requests) == 1
    request = requests[0]
    assert request.project.project_id == "mlj_dspmods"
    assert request.group_id == "319567534"
    assert request.mode == "discuss"
    assert request.timeout_seconds == 120
    assert request.progress_callback is None
    assert "只读资料查询" in request.prompt
    assert "当前项目目录" in request.prompt
    assert "最终只输出可以直接发到 QQ 群里的答案" in request.prompt
    assert "物品堆叠怎么升级" in request.prompt


def test_orchestrator_domain_codex_failure_does_not_fall_back_to_plain_llm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = CodexProjectBinding(
        project_id="orbital_ring",
        display_name="OrbitalRing-MOD",
        repo_path=str(tmp_path / "OrbitalRing-MOD"),
    )

    def fake_resolve(*_args, **_kwargs):
        return type("Match", (), {"project": project})()

    async def fake_codex_runner(request):
        return CodexTaskResult(False, "Codex 会话超时。", exit_code=None)

    monkeypatch.setattr(ai_orchestrator_module, "resolve_codex_project_for_text", fake_resolve)
    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)

    result = asyncio.run(
        orchestrator.handle(
            "星环隐藏科技有哪些",
            AiOrchestratorContext(actor_user_id="10001", group_id="1035445959"),
            NormalizedMessage(text="星环隐藏科技有哪些", outline="星环隐藏科技有哪些"),
        )
    )

    assert result.handled is True
    assert "只读查询失败" in result.text
    assert "我先不按通用机制乱猜" in result.text


def test_orchestrator_routes_project_genesis_domain_question_to_readonly_codex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests = []
    project = CodexProjectBinding(
        project_id="project_genesis",
        display_name="ProjectGenesis",
        repo_path=str(tmp_path / "ProjectGenesis"),
    )

    def fake_resolve(*_args, **_kwargs):
        return type("Match", (), {"project": project})()

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "这个配方要按 ProjectGenesis data 里的科技解锁关系查喵"})()

    monkeypatch.setattr(ai_orchestrator_module, "resolve_codex_project_for_text", fake_resolve)
    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)

    result = asyncio.run(
        orchestrator.handle(
            "氯化钠堵了怎么还在生产？",
            AiOrchestratorContext(actor_user_id="10001", group_id="991895539"),
            NormalizedMessage(text="氯化钠堵了怎么还在生产？", outline="氯化钠堵了怎么还在生产？"),
        )
    )

    assert result.handled is True
    assert result.text == "这个配方要按 ProjectGenesis data 里的科技解锁关系查喵"
    assert len(requests) == 1
    request = requests[0]
    assert request.project.project_id == "project_genesis"
    assert request.group_id == "991895539"
    assert request.mode == "discuss"
    assert request.timeout_seconds == 120
    assert request.progress_callback is None
    assert "只读资料查询" in request.prompt
    assert "ProjectGenesis" in request.prompt
    assert "氯化钠堵了怎么还在生产？" in request.prompt


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
    bot.group_files = [
        {
            "file_id": "old-fe",
            "busid": 1,
            "file_name": "FractionateEverything_2.2.9.zip",
            "uploader": 114514,
        },
        {
            "file_id": "keep-get-data",
            "busid": 2,
            "file_name": "GetDspData_1.0.0.zip",
            "uploader": 114514,
        },
    ]
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
    assert "已清理旧包 1 个" in result.text
    assert bot.calls == [
        (
            "get_group_root_files",
            {
                "group_id": 319567534,
            },
        ),
        (
            "delete_group_file",
            {
                "group_id": 319567534,
                "file_id": "old-fe",
                "busid": 1,
            },
        ),
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        )
    ]


def test_orchestrator_skips_latest_fe_zip_upload_when_sha_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bot = FakeBot()
    package = tmp_path / "repo" / "ModZips" / "FractionateEverything_2.3.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"same-fe-content")
    state_path = tmp_path / "fe_artifacts" / "319567534.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        '{"sha256": "' + hashlib.sha256(package.read_bytes()).hexdigest() + '"}',
        encoding="utf-8",
    )
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
    assert result.text == "FE 压缩包内容没有变化，已跳过上传。"
    assert bot.calls == []


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


def test_orchestrator_enters_group_bound_project_after_codex_keyword(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex", outline="codex"),
        )
    )

    assert result.handled is True
    assert "MLJ_DSPmods" in result.text
    assert "已进入 Codex 模式 CODEX-S0001" in result.text


def test_orchestrator_enters_current_qqbot_project_without_group_binding(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex",
            AiOrchestratorContext(actor_user_id="605738729", is_admin=True),
            NormalizedMessage(text="codex", outline="codex"),
        )
    )

    assert result.handled is True
    assert "已进入 Codex 模式 CODEX-S0001" in result.text
    assert "qqbot" in result.text


def test_orchestrator_uses_bound_project_for_initial_prompt(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "收到。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        result = await orchestrator.handle(
            "codex 不存在项目",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 不存在项目", outline="codex 不存在项目"),
        )

        assert result.handled is True
        assert "已进入 Codex 模式 CODEX-S0001" in result.text
        assert "收到" in result.text

    asyncio.run(run())

    assert requests[0].project.project_id == "mlj_dspmods"
    assert requests[0].prompt == "不存在项目"


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


def test_orchestrator_enters_codex_mode_and_forwards_initial_prompt(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "收到首条需求。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        result = await orchestrator.handle(
            "codex 看一下这个报错",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 看一下这个报错", outline="codex 看一下这个报错"),
        )

        assert result.handled is True
        assert "已进入 Codex 模式 CODEX-S0001" in result.text
        assert "收到首条需求" in result.text

    asyncio.run(run())

    assert requests[0].project.project_id == "mlj_dspmods"
    assert requests[0].prompt == "看一下这个报错"
    assert requests[0].mode == "discuss"


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


def test_orchestrator_forwards_codex_prefixed_message_inside_active_session(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "收到。", "exit_code": 0})()

    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
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
    assert requests[0].project.project_id == "mlj_dspmods"
    assert requests[0].prompt == "qqbot"


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


def test_orchestrator_lets_plain_chat_fall_back_after_codex_session_expires(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "不该收到风格切换。", "exit_code": 0})()

    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)

    asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            context,
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )
    store = orchestrator._codex_session_store()
    active = store.get_active_session(actor_user_id="605738729", group_id="319567534")
    assert active is not None
    stale = active.__class__(
        session_id=active.session_id,
        project_id=active.project_id,
        project_display_name=active.project_display_name,
        status=active.status,
        created_by=active.created_by,
        group_id=active.group_id,
        transcript=active.transcript,
        pending_messages=active.pending_messages,
        created_at=active.created_at - 3600,
        updated_at=active.updated_at - 3600,
    )
    store._replace_session(stale)

    result = asyncio.run(
        orchestrator.handle(
            "切换谜语人风格",
            context,
            NormalizedMessage(text="切换谜语人风格", outline="切换谜语人风格"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "预设" not in result.text
    assert "人格" not in result.text
    assert "4:00" not in result.text
    assert requests == []


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


def test_orchestrator_records_admin_adjustment_while_session_is_running(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    store = orchestrator._codex_session_store()
    project = get_codex_project_by_id("mlj_dspmods")
    assert project is not None
    session = store.create_session(
        project=project,
        actor_user_id="605738729",
        group_id="319567534",
    )
    store.mark_status(session.session_id, "running")

    result = asyncio.run(
        orchestrator.handle(
            "先不要提交，补一个测试",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="先不要提交，补一个测试", outline="先不要提交，补一个测试"),
        )
    )

    updated = store.get_session(session.session_id)
    assert result.handled is True
    assert "已收到 Codex 调整" in result.text
    assert updated is not None
    assert updated.pending_messages == ("先不要提交，补一个测试",)


def test_orchestrator_merges_pending_adjustments_after_codex_turn(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "已经看完。", "exit_code": 0})()

    async def run() -> None:
        orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        store = orchestrator._codex_session_store()
        active = store.get_active_session(actor_user_id="605738729", group_id="319567534")
        assert active is not None
        store.append_pending_message(active.session_id, "优先补测试")

        result = await orchestrator.handle(
            "继续看",
            context,
            NormalizedMessage(text="继续看", outline="继续看"),
        )
        assert result.handled is True
        assert "已合并 1 条运行中调整" in result.text

    asyncio.run(run())

    store = AiOrchestrator(data_root=tmp_path)._codex_session_store()
    active = store.get_active_session(actor_user_id="605738729", group_id="319567534")
    assert active is not None
    assert active.pending_messages == ()
    assert ("user", "[运行中补充] 优先补测试") in active.transcript


def test_orchestrator_reports_codex_session_progress_to_group(tmp_path: Path) -> None:
    bot = FakeBot()

    async def fake_codex_runner(request):
        assert request.progress_callback is not None
        await request.progress_callback(
            CodexProgressEvent(phase="output", message="正在读取计划文件", stream="stdout")
        )
        return type("Result", (), {"ok": True, "message": "讨论完成。", "exit_code": 0})()

    async def run() -> None:
        executor = AiActionExecutor(bot=bot, data_root=tmp_path)
        orchestrator = AiOrchestrator(
            data_root=tmp_path,
            action_executor=executor,
            codex_session_runner=fake_codex_runner,
        )
        context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)
        await orchestrator.handle("codex 分馏", context, NormalizedMessage(text="codex 分馏", outline="codex 分馏"))
        result = await orchestrator.handle(
            "看一下方案",
            context,
            NormalizedMessage(text="看一下方案", outline="看一下方案"),
        )
        assert result.handled is True

    asyncio.run(run())

    assert bot.calls[0][0] == "send_group_msg"
    assert "Codex 还在处理" in bot.calls[0][1]["message"]
    assert "正在读取计划文件" in bot.calls[0][1]["message"]


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
        assert result.handled is False
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
        assert result.handled is False

    asyncio.run(run())

    assert requests == []


def test_orchestrator_enters_codex_session_only_with_explicit_codex_prefix(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "已收到。", "exit_code": 0})()

    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)

    result = asyncio.run(
        orchestrator.handle(
            "codex 异星模组品质飞船的计算公式改成新的倍率",
            context,
            NormalizedMessage(
                text="codex 异星模组品质飞船的计算公式改成新的倍率",
                outline="codex 异星模组品质飞船的计算公式改成新的倍率",
            ),
        )
    )

    assert result.handled is True
    assert "已进入 Codex 模式 CODEX-S0001" in result.text
    assert "MLJ_DSPmods" in result.text
    assert requests[0].prompt == "异星模组品质飞船的计算公式改成新的倍率"


def test_orchestrator_does_not_treat_codex_draft_followup_as_plain_chat_command(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True)

    second = asyncio.run(
        orchestrator.handle(
            "补充一下，公式具体改成 A/B",
            context,
            NormalizedMessage(text="补充一下，公式具体改成 A/B", outline="补充一下，公式具体改成 A/B"),
        )
    )

    assert second.handled is False


def test_orchestrator_enters_codex_session_for_revision_version_request(tmp_path: Path) -> None:
    requests = []

    async def fake_codex_runner(request):
        requests.append(request)
        return type("Result", (), {"ok": True, "message": "收到版本号需求。", "exit_code": 0})()

    orchestrator = AiOrchestrator(data_root=tmp_path, codex_session_runner=fake_codex_runner)

    result = asyncio.run(
        orchestrator.handle(
            "codex 分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(
                text="codex 分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
                outline="codex 分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不",
            ),
        )
    )

    assert result.handled is True
    assert "已进入 Codex 模式 CODEX-S0001" in result.text
    assert "MLJ_DSPmods" in result.text
    assert requests[0].prompt == "分馏现在一直是2.3.0版本，你看看能不能加一个修订版本号，跟R2兼容不"


def test_orchestrator_does_not_treat_revision_version_request_as_codex_without_prefix(tmp_path: Path) -> None:
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

    assert result.handled is False


def test_orchestrator_does_not_treat_plain_chat_as_codex_alias(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花糖也才出生没多久也是个萝莉呢，他在隐晦的对你表白呢",
            AiOrchestratorContext(actor_user_id="10001", group_id="319567534", is_admin=False),
            NormalizedMessage(
                text="棉花糖也才出生没多久也是个萝莉呢，他在隐晦的对你表白呢",
                outline="棉花糖也才出生没多久也是个萝莉呢，他在隐晦的对你表白呢",
            ),
        )
    )

    assert result.handled is False


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


def test_orchestrator_generates_image_with_rightcodes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeDrawClient.requests = []
    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FakeDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(
                text="棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
                outline="棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
                image_urls=("https://example.com/ref.png",),
            ),
        )
    )

    assert result.handled is True
    assert result.image_path == "https://example.com/generated.png"
    assert result.text == "✨ 生成成功！\n📊 耗时: 1.00s\n🖼️ 数量: 1张\n🤖 模型: nano-banana-pro"
    api_key, request = FakeDrawClient.requests[0]
    assert api_key == "rc-secret"
    assert request.model == "nano-banana-pro"
    assert request.prompt == "画一个糖果城堡"
    assert request.image_urls == ("https://example.com/ref.png",)


def test_orchestrator_prioritizes_rightcodes_draw_over_style_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeDrawClient.requests = []
    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FakeDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花生图 把这张图按照nature封面的风格重画",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(
                text="棉花生图 把这张图按照nature封面的风格重画",
                outline="棉花生图 把这张图按照nature封面的风格重画",
                image_urls=("https://example.com/ref.png",),
            ),
        )
    )

    assert result.handled is True
    assert result.image_path == "https://example.com/generated.png"
    assert result.text != STYLE_CONTROL_REPLY_MESSAGE
    assert FakeDrawClient.requests[0][1].prompt == "把这张图按照nature封面的风格重画"


def test_orchestrator_returns_rightcodes_model_help(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "生图模型说明",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="生图模型说明", outline="生图模型说明"),
        )
    )

    assert result.handled is True
    assert "gpt-image-2（默认）：0.04r/张" in result.text
    assert "nano-banana-pro：0.18r/张" in result.text
    assert result.image_path is None


def test_orchestrator_reports_rightcodes_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FailingDrawClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

        async def draw(self, request):
            raise RuntimeError("API 错误 (400)")

    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FailingDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花生图 雌小鬼萝莉",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="棉花生图 雌小鬼萝莉", outline="棉花生图 雌小鬼萝莉"),
        )
    )

    assert result.handled is True
    assert result.image_path is None
    assert result.text == "❌ 生成失败: API 错误 (400)"


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
