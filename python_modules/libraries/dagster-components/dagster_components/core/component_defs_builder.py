from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from dagster._utils.warnings import suppress_dagster_warnings

from dagster_components.core.component import (
    Component,
    ComponentLoadContext,
    ComponentTypeRegistry,
    TemplatedValueResolver,
)
from dagster_components.core.component_decl_builder import (
    ComponentDeclNode,
    ComponentFolder,
    YamlComponentDecl,
    path_to_decl_node,
)
from dagster_components.core.deployment import CodeLocationProjectContext

if TYPE_CHECKING:
    from dagster._core.definitions.definitions_class import Definitions


def resolve_decl_node_to_yaml_decls(decl: ComponentDeclNode) -> list[YamlComponentDecl]:
    if isinstance(decl, YamlComponentDecl):
        return [decl]
    elif isinstance(decl, ComponentFolder):
        leaf_decls = []
        for sub_decl in decl.sub_decls:
            leaf_decls.extend(resolve_decl_node_to_yaml_decls(sub_decl))
        return leaf_decls

    raise NotImplementedError(f"Unknown component type {decl}")


def build_components_from_component_folder(
    context: ComponentLoadContext, path: Path
) -> Sequence[Component]:
    component_folder = path_to_decl_node(path)
    assert isinstance(component_folder, ComponentFolder)
    return component_folder.load(context.for_decl_node(component_folder))


def build_defs_from_component_path(
    path: Path,
    registry: ComponentTypeRegistry,
    resources: Mapping[str, object],
) -> "Definitions":
    """Build a definitions object from a folder within the components hierarchy."""
    decl_node = path_to_decl_node(path=path)
    if not decl_node:
        raise Exception(f"No component found at path {path}")

    context = ComponentLoadContext(
        resources=resources,
        registry=registry,
        decl_node=decl_node,
        templated_value_resolver=TemplatedValueResolver.default(),
    )
    components = decl_node.load(context)
    return defs_from_components(resources=resources, context=context, components=components)


@suppress_dagster_warnings
def defs_from_components(
    *,
    context: ComponentLoadContext,
    components: Sequence[Component],
    resources: Mapping[str, object],
) -> "Definitions":
    from dagster._core.definitions.definitions_class import Definitions

    return Definitions.merge(
        *[
            *[
                c.build_defs(context.with_rendering_scope(c.get_additional_scope()))
                for c in components
            ],
            Definitions(resources=resources),
        ]
    )


# Public method so optional Nones are fine
@suppress_dagster_warnings
def build_component_defs(
    code_location_root: Path,
    resources: Optional[Mapping[str, object]] = None,
    registry: Optional["ComponentTypeRegistry"] = None,
    components_path: Optional[Path] = None,
) -> "Definitions":
    """Build a Definitions object for all the component instances in a given code location.

    Args:
        code_location_root (Path): The path to the code location root.
            The path must be a code location directory that has a pyproject.toml with a [dagster] section.
    """
    from dagster._core.definitions.definitions_class import Definitions

    context = CodeLocationProjectContext.from_code_location_path(
        code_location_root,
        registry or ComponentTypeRegistry.from_entry_point_discovery(),
        components_path=components_path,
    )

    all_defs: list[Definitions] = []
    for component in context.component_instances:
        component_path = Path(context.get_component_instance_path(component))
        defs = build_defs_from_component_path(
            path=component_path,
            registry=context.component_registry,
            resources=resources or {},
        )
        all_defs.append(defs)
    return Definitions.merge(*all_defs)
