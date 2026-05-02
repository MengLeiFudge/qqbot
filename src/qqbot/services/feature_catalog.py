from __future__ import annotations

from dataclasses import dataclass

from qqbot.services.plugin_registry import (
    PluginSpec,
    get_plugin_spec_by_feature_index,
    get_plugin_spec_by_menu_key,
    list_visible_plugin_specs,
)


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    index: int
    name: str
    legacy_names: tuple[str, ...] = ()
    menu_lines: tuple[str, ...] = ()
    menu_keys: tuple[str, ...] = ()


def _feature_from_plugin(spec: PluginSpec) -> FeatureDefinition:
    if spec.feature_index is None:
        raise ValueError(f"插件 {spec.id} 没有可见功能序号")
    return FeatureDefinition(
        index=spec.feature_index,
        name=spec.name,
        legacy_names=spec.legacy_names,
        menu_lines=spec.menu_lines,
        menu_keys=spec.menu_keys,
    )


def list_visible_features() -> list[FeatureDefinition]:
    return [_feature_from_plugin(spec) for spec in list_visible_plugin_specs()]


def get_feature_by_index(index: int) -> FeatureDefinition | None:
    spec = get_plugin_spec_by_feature_index(index)
    if spec is None:
        return None
    return _feature_from_plugin(spec)


def get_feature_by_menu_key(key: str) -> FeatureDefinition | None:
    spec = get_plugin_spec_by_menu_key(key)
    if spec is None:
        return None
    return _feature_from_plugin(spec)


def build_group_menu_text(feature_states: dict[int, bool]) -> str:
    # 菜单文案沿用旧 mirai 结构，先保证迁移后的命令与原行为一致。
    lines = ["本群功能开启情况如下："]
    for feature in list_visible_features():
        status = "开启" if feature_states.get(feature.index, False) else "关闭"
        lines.append(f"{feature.index}.{feature.name}：{status}")
    lines.append("tips：【菜单+功能序号】获得对应功能菜单，如【菜单21】")
    return "\n".join(lines)


def build_feature_menu_text(index_or_key: int | str) -> str | None:
    feature = (
        get_feature_by_index(index_or_key)
        if isinstance(index_or_key, int)
        else get_feature_by_menu_key(index_or_key)
    )
    if feature is None:
        return None

    if not feature.menu_lines:
        return f"{feature.name} 暂无单独功能菜单。"

    lines = [f"{feature.name} 功能菜单："]
    lines.extend(feature.menu_lines)
    return "\n".join(lines)
