#!/usr/bin/env python3
"""启动前校验本机插件配置，保留独立实例的启用选择。"""

from pathlib import Path

import re
import sys
import tomllib


PROJECT_ROOT = Path.cwd()


def main() -> int:
    """校验 TOML、启用字段和 MaiBot 要求的插件配置版本。"""
    targets = sorted((PROJECT_ROOT / "plugins").glob("*/config.toml"))
    management = PROJECT_ROOT / "src/plugins/built_in/plugin_management/config.toml"
    targets.append(management)
    for path in targets:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            # 不输出解析器原文，配置可能包含本机凭据。
            raise RuntimeError(f"无法解析插件配置 {path}: {type(exc).__name__}") from None
        plugin = data.get("plugin")
        if not isinstance(plugin, dict) or type(plugin.get("enabled")) is not bool:
            raise RuntimeError(f"插件配置 {path} 必须明确设置布尔值 plugin.enabled")
        version = plugin.get("config_version")
        if (path == management or plugin["enabled"]) and (
            not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        ):
            raise RuntimeError(f"插件配置 {path} 必须填写插件声明的 plugin.config_version")
        if path == management and plugin["enabled"] is not False:
            raise RuntimeError(f"{path} 必须设置 plugin.enabled = false")
    print(f"独立插件配置校验通过，共 {len(targets)} 份。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"插件配置校验失败：{exc}", file=sys.stderr)
        sys.exit(1)
