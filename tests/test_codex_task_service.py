from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.codex_task_service import (
    build_codex_exec_command,
    build_codex_session_prompt,
    CodexSessionStore,
    CodexSessionRequest,
    CodexTaskResult,
    CodexTaskStore,
    extract_codex_zip_artifacts,
    learn_codex_project_alias,
    get_codex_project_by_id,
    get_codex_project_for_group,
    load_learned_project_aliases,
    parse_codex_alias_learning_request,
    resolve_codex_project_for_text,
    to_wsl_path,
)


def test_codex_project_binding_maps_dsp_group_to_mod_repo() -> None:
    project = get_codex_project_for_group("319567534")

    assert project is not None
    assert project.project_id == "mlj_dspmods"
    assert project.repo_path == "/mnt/d/project/csharp/DSP MOD/MLJ_DSPmods"


def test_codex_project_resolver_matches_factorio_quality_ship_from_index(tmp_path: Path) -> None:
    result = resolve_codex_project_for_text(
        "异星模组品质飞船的计算公式改成新的倍率",
        group_id=None,
        data_root=tmp_path,
    )

    assert result is not None
    assert result.project.project_id == "factorio_mods"
    assert "索引" in result.reason or "别名" in result.reason


def test_codex_project_resolver_uses_learned_alias(tmp_path: Path) -> None:
    learn_codex_project_alias(tmp_path, "品质飞船", "factorio_mods")

    result = resolve_codex_project_for_text(
        "品质飞船公式改一下",
        group_id=None,
        data_root=tmp_path,
    )

    assert result is not None
    assert result.project.project_id == "factorio_mods"
    assert load_learned_project_aliases(tmp_path)["品质飞船"] == "factorio_mods"


def test_parse_codex_alias_learning_request() -> None:
    parsed = parse_codex_alias_learning_request("品质飞船是MLJ_Factorio_Mods的一个内容")

    assert parsed == ("品质飞船", "factorio_mods")


def test_to_wsl_path_converts_windows_drive_path() -> None:
    assert to_wsl_path(r"D:\project\csharp\DSP MOD\MLJ_DSPmods") == (
        "/mnt/d/project/csharp/DSP MOD/MLJ_DSPmods"
    )


def test_extract_codex_zip_artifacts_keeps_only_repo_zip_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo with space"
    package = repo / "AfterBuildEvent" / "bin" / "win" / "Debug" / "ModZips" / "FractionateEverything_2.3.0.zip"
    outside = tmp_path / "outside.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"zip")
    outside.write_bytes(b"zip")

    artifacts = extract_codex_zip_artifacts(
        f"产物：{package}\n不应上传：{outside}",
        repo,
    )

    assert artifacts == (package,)


def test_codex_command_uses_workspace_write_and_model() -> None:
    command = build_codex_exec_command(
        "/mnt/d/project/csharp/DSP MOD/MLJ_DSPmods",
        "gpt-5.5",
    )

    assert command[:4] == ["wsl.exe", "-e", "bash", "-lc"]
    assert '"$codex_bin" -a never exec' in command[4]
    assert "-m gpt-5.5" in command[4]
    assert "-c model_provider=custom" in command[4]
    assert "-s workspace-write" in command[4]


def test_codex_command_can_use_read_only_sandbox() -> None:
    command = build_codex_exec_command(
        "/mnt/d/project/python/qqbot",
        "gpt-5.5",
        sandbox="read-only",
    )

    assert "-s read-only" in command[4]


def test_codex_command_loads_nvm_before_running_codex() -> None:
    command = build_codex_exec_command(
        "/mnt/d/project/python/qqbot",
        "gpt-5.5",
    )

    assert 'NVM_DIR="$HOME/.nvm"' in command[4]
    assert "nvm.sh" in command[4]
    assert "codex_bin" in command[4]


def test_codex_prompt_only_describes_qqbot_source_context() -> None:
    project = get_codex_project_by_id("mlj_dspmods")
    assert project is not None

    prompt = build_codex_session_prompt(
        CodexSessionRequest(
            project=project,
            actor_user_id="605738729",
            group_id="319567534",
            session_id="CODEX-S0001",
            prompt="执行",
            transcript=(),
            mode="execute",
        )
    )

    assert "QQ bot 转发" in prompt
    assert "本轮模式：execute" in prompt
    assert "不附加项目执行规则" in prompt
    assert "不要 push" not in prompt
    assert "验证通过后必须原子提交" not in prompt
    assert "不要提交或推送 git" not in prompt
    assert "不要使用 Markdown" not in prompt
    assert "AGENTS.md" not in prompt


def test_codex_task_store_creates_draft_and_persists_messages(tmp_path: Path) -> None:
    project = get_codex_project_by_id("factorio_mods")
    assert project is not None
    store = CodexTaskStore(tmp_path)

    task = store.create_draft(
        project=project,
        actor_user_id="605738729",
        group_id="319567534",
        message="异星模组品质飞船公式改成新倍率",
        evidence="用户在群里提出公式修改",
    )

    reread = CodexTaskStore(tmp_path).get_task(task.task_id)
    assert reread is not None
    assert reread.task_id == "CODEX-0001"
    assert reread.project_id == "factorio_mods"
    assert reread.status == "draft"
    assert reread.raw_messages == ("异星模组品质飞船公式改成新倍率",)
    assert reread.evidence == ("用户在群里提出公式修改",)


def test_codex_task_store_appends_to_recent_draft(tmp_path: Path) -> None:
    project = get_codex_project_by_id("mlj_dspmods")
    assert project is not None
    store = CodexTaskStore(tmp_path)
    task = store.create_draft(
        project=project,
        actor_user_id="605738729",
        group_id="319567534",
        message="改一下分馏，先讨论公式",
        evidence="",
    )

    latest = store.find_latest_draft(
        actor_user_id="605738729",
        group_id="319567534",
        project_id="mlj_dspmods",
    )
    assert latest is not None
    updated = store.append_message(latest.task_id, "公式具体改成 A/B", evidence="补充说明")

    assert updated.task_id == task.task_id
    assert updated.raw_messages == ("改一下分馏，先讨论公式", "公式具体改成 A/B")
    assert updated.evidence == ("补充说明",)


def test_codex_task_store_records_codex_result(tmp_path: Path) -> None:
    project = get_codex_project_by_id("qqbot")
    assert project is not None
    store = CodexTaskStore(tmp_path)
    task = store.create_draft(
        project=project,
        actor_user_id="605738729",
        group_id=None,
        message="调整机器人 Codex 流程",
        evidence="",
    )

    done = store.record_result(
        task.task_id,
        CodexTaskResult(ok=False, message="测试失败：1 failed", exit_code=1),
    )

    assert done.status == "failed"
    assert done.last_codex_result == "测试失败：1 failed"


def test_codex_session_store_creates_active_session_and_records_turns(tmp_path: Path) -> None:
    project = get_codex_project_by_id("mlj_dspmods")
    assert project is not None
    store = CodexSessionStore(tmp_path)

    session = store.create_session(
        project=project,
        actor_user_id="605738729",
        group_id="319567534",
    )
    updated = store.append_turn(session.session_id, user_message="先看看版本号", codex_message="需要确认 R2 兼容边界")

    active = CodexSessionStore(tmp_path).get_active_session(
        actor_user_id="605738729",
        group_id="319567534",
    )
    assert active is not None
    assert active.session_id == "CODEX-S0001"
    assert active.project_id == "mlj_dspmods"
    assert updated.transcript[-2:] == (
        ("user", "先看看版本号"),
        ("codex", "需要确认 R2 兼容边界"),
    )


def test_codex_session_store_closes_session(tmp_path: Path) -> None:
    project = get_codex_project_by_id("qqbot")
    assert project is not None
    store = CodexSessionStore(tmp_path)
    session = store.create_session(project=project, actor_user_id="605738729", group_id=None)

    store.close_session(session.session_id)

    assert store.get_active_session(actor_user_id="605738729", group_id=None) is None
