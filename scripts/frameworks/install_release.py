from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

import argparse
import json
import os
import shutil
import subprocess
import tempfile

from deploy_plugins import PLUGIN_MANAGEMENT, WORKSPACE, deploy_plugins, framework_kind, load_deployment


STATE = {
    "astrbot": ("data", ".astrbot", ".env"),
    "maibot": ("config", "data", "plugins", "logs", "temp", "custom_prompts", ".env", "eula.confirmed", "privacy.confirmed"),
}
RECORD = ".qqbot-release.json"


def unpack_release(spec, stage):
    archive = stage.parent / "upstream.zip"
    url = f"https://codeload.github.com/{spec['repository']}/zip/{spec['commit']}"
    with urlopen(url, timeout=25) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    with ZipFile(archive) as package:
        for entry in package.infolist():
            parts = PurePosixPath(entry.filename).parts
            if not parts or any(part in {"..", "/"} or ":" in part or "\\" in part for part in parts):
                raise ValueError(f"发布包路径无效：{entry.filename}")
            if not parts[0].endswith("-" + spec["commit"]):
                raise ValueError(f"发布包目录与固定提交不一致：{parts[0]}")
            if entry.is_dir():
                continue
            dest = stage.joinpath(*parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, dest.open("xb") as output:
                shutil.copyfileobj(source, output)


def install_release(account, manifest, local_source=None):
    kind = framework_kind(account)
    spec = manifest[kind]
    root = WORKSPACE / account["framework"]["root"]
    release = {key: spec[key] for key in ("repository", "tag", "commit")}
    record = root / RECORD
    if record.is_file() and json.loads(record.read_text(encoding="utf-8")) == release:
        if not (root / spec["entrypoint"]).is_file():
            raise RuntimeError(f"{root} 的运行包不完整，先恢复框架文件。")
        deploy_plugins(account, manifest, root)
        return
    if (root / ".git").exists() and local_source is None:
        raise RuntimeError(f"{root} 仍是旧 Git 子仓库，需先迁移现有实例。")

    trash = WORKSPACE / ".codex/trash"
    trash.mkdir(parents=True, exist_ok=True)
    transaction = Path(tempfile.mkdtemp(prefix=f"framework-{account['target']}-", dir=trash))
    stage = transaction / "release"
    previous = transaction / "previous"
    if local_source is None:
        unpack_release(spec, stage)
    else:
        shutil.copytree(local_source, stage)
    if not (stage / spec["entrypoint"]).is_file() or not (stage / "pyproject.toml").is_file():
        raise RuntimeError(f"官方包缺少入口或 pyproject.toml：{stage}")
    if kind == "maibot" and not (stage / "uv.lock").is_file():
        raise RuntimeError(f"MaiBot 发布包缺少 uv.lock：{stage}")

    retained = set(STATE[kind])
    if kind == "maibot":
        config = stage / PLUGIN_MANAGEMENT
        if not (config.parent / "plugin.py").is_file():
            raise RuntimeError(f"{spec['tag']} 的 MaiBot 插件管理位置已变化，请核对禁用设置。")
        existing = root / PLUGIN_MANAGEMENT
        if existing.is_file():
            shutil.copy2(existing, config)
        else:
            config.write_text("[plugin]\nenabled = false\n", encoding="utf-8")
    if local_source is not None:
        dependency_file = "pyproject.toml" if kind == "astrbot" else "uv.lock"
        old_dep, new_dep = root / dependency_file, stage / dependency_file
        if old_dep.is_file() and old_dep.read_bytes().replace(b"\r\n", b"\n") == new_dep.read_bytes().replace(b"\r\n", b"\n"):
            retained.add(".venv")
            if kind == "astrbot" and not (stage / "uv.lock").exists():
                retained.add("uv.lock")

    prepared_record = transaction / RECORD
    prepared_record.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    if root.exists() and os.name == "nt" and (root / spec["entrypoint"]).exists():
        launcher = WORKSPACE / account["framework"]["startScript"]
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher), "-ProjectRoot", str(root), "-StopOnly", "-SkipInstall"], check=True)
    root.mkdir(parents=True, exist_ok=True)
    previous.mkdir()
    moves = []
    try:
        for old in sorted(root.iterdir()):
            if old.name not in retained:
                backup = previous / old.name
                old.rename(backup)
                moves.append((old, backup))
        for incoming in sorted(stage.iterdir()):
            dest = root / incoming.name
            if dest.exists():
                if incoming.name == "plugins":
                    for plugin in sorted(incoming.iterdir()):
                        if not (dest / plugin.name).exists():
                            plugin.rename(dest / plugin.name)
                            moves.append((plugin, dest / plugin.name))
                    continue
                raise RuntimeError(f"发布包与实例数据路径重叠：{dest}")
            incoming.rename(dest)
            moves.append((incoming, dest))
        deploy_plugins(account, manifest, root)
        prepared_record.rename(record)
    except BaseException:
        for original, dest in reversed(moves):
            dest.rename(original)
        raise
    print(f"[qqbot] {account['target']} 已安装 {spec['repository']} {spec['tag']}。归档：{transaction}")


def main():
    accounts, manifest = load_deployment()
    targets = [account["target"] for account in accounts]
    parser = argparse.ArgumentParser(description="安装清单固定的官方框架版本")
    parser.add_argument("target", choices=["all", "astrbot", "maibot", *targets])
    parser.add_argument("--from-tag-tree", type=Path, help="使用已经解包的同版本官方 tag 归档迁移单个实例")
    args = parser.parse_args()
    if args.from_tag_tree and args.target not in targets:
        parser.error("本地归档仅支持单个实例 Target")
    for account in accounts:
        if args.target in {"all", account["target"], framework_kind(account)}:
            install_release(account, manifest, args.from_tag_tree)


if __name__ == "__main__":
    main()
