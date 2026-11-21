from pathlib import Path

import argparse
import filecmp
import json
import os
import shutil
import stat
import tempfile


WORKSPACE = Path(__file__).resolve().parents[2]
ACCOUNTS = WORKSPACE / "napcat/accounts.json"
FRAMEWORKS = WORKSPACE / "deployment/frameworks.json"
PLUGIN_MANAGEMENT = Path("src/plugins/built_in/plugin_management/config.toml")


def load_deployment():
    accounts = json.loads(ACCOUNTS.read_text(encoding="utf-8"))["accounts"]
    frameworks = json.loads(FRAMEWORKS.read_text(encoding="utf-8"))
    return accounts, frameworks


def framework_kind(account):
    return account["framework"]["name"].split("-", 1)[0]


def plugin_sources(account, manifest):
    kind = framework_kind(account)
    sets = manifest["pluginSets"]
    names = set(sets[kind])
    layers = [(kind, set())]
    if account["target"] in {"fengling", "yelin"}:
        names.difference_update(sets["chatOnly"]["excludePlugins"])
        layers.append(("overrides/chat-only", sets["chatOnly"]["excludeFiles"]))
    if account["target"] == "yelin":
        layers.append(("overrides/yelin", sets["yelin"]["excludeFiles"]))

    files = {}
    for layer, excluded in layers:
        for path in excluded:
            files.pop(Path(path), None)
        root = WORKSPACE / "plugins" / layer
        for name in sorted(names):
            for source in (root / name).rglob("*"):
                relative = source.relative_to(root)
                if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in relative.parts):
                    continue
                if source.name.lower() in {"config.toml", ".env"} or source.suffix.lower() in {".pyc", ".db", ".sqlite", ".sqlite3", ".log"}:
                    continue
                if source.is_file():
                    if source.resolve() != source.absolute():
                        raise ValueError(f"插件源码包含链接：{source}")
                    files[relative] = source
    missing = names.difference(path.parts[0] for path in files)
    if missing:
        raise ValueError(f"插件清单缺少源码：{', '.join(sorted(missing))}")
    return files


def deploy_plugins(account, manifest, runtime):
    kind = framework_kind(account)
    root = runtime / manifest[kind]["pluginDirectory"]
    files = plugin_sources(account, manifest)
    pending = []
    for relative, source in sorted(files.items()):
        dest = root / relative
        for path in (dest, *dest.parents):
            if path == runtime.parent:
                break
            if path.is_symlink() or (os.name == "nt" and path.exists() and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError(f"插件目录包含链接：{path}")
        # 图床默认值随插件交付，已有本机配置优先。
        if dest.exists() and relative.as_posix().endswith("/image_host/config.json"):
            continue
        if not dest.is_file() or not filecmp.cmp(source, dest, shallow=False):
            pending.append((source, dest))
    for source, dest in pending:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".tmp", delete=False) as file:
            temp = Path(file.name)
        try:
            shutil.copyfile(source, temp)
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
    print(f"[qqbot] {account['target']} 同步 {len(pending)} 个插件文件")


def main():
    accounts, manifest = load_deployment()
    parser = argparse.ArgumentParser(description="部署 qqbot 自研插件")
    parser.add_argument("target", choices=["all", *(account["target"] for account in accounts)])
    args = parser.parse_args()
    for account in accounts:
        if args.target not in {"all", account["target"]}:
            continue
        runtime = WORKSPACE / account["framework"]["root"]
        spec = manifest[framework_kind(account)]
        if not (runtime / spec["entrypoint"]).is_file():
            raise SystemExit(f"{runtime} 缺少框架。先运行 scripts/update-all.bat。")
        deploy_plugins(account, manifest, runtime)


if __name__ == "__main__":
    main()
