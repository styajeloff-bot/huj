"""OpenAPI schema filtering by user role.

Builds per-role OpenAPI schemas at application startup by introspecting route
dependencies. The custom ``/api/v1/openapi.json`` handler serves the schema
that matches the authenticated user's role.
"""
from __future__ import annotations

import copy
from collections import deque
from typing import Any

from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from domain.services.scopes import _ROLE_SCOPES
from presentation.dependencies.auth import (
    get_current_user,
    get_current_user_optional,
    get_current_user_optional_strict,
    get_current_user_with_db,
)

_MANDATORY_AUTH_CALLABLES: frozenset[Any] = frozenset(
    {get_current_user, get_current_user_with_db}
)
_OPTIONAL_AUTH_CALLABLES: frozenset[Any] = frozenset(
    {get_current_user_optional, get_current_user_optional_strict}
)
_ALL_AUTH_CALLABLES: frozenset[Any] = _MANDATORY_AUTH_CALLABLES | _OPTIONAL_AUTH_CALLABLES
_COMPONENT_REF_PREFIX = "#/components/"


def _collect_required_scopes(route: APIRoute | RouteContext) -> frozenset[str]:
    """Return all scopes required by ``require_scopes(...)`` on this route."""
    scopes: set[str] = set()

    # Router-level / endpoint-decorator dependencies
    for dep in getattr(route, "dependencies", []):
        dependency = getattr(dep, "dependency", None)
        if dependency is not None and hasattr(dependency, "_required_scopes"):
            scopes.update(dependency._required_scopes)

    # Parameter dependencies (recursive through the dependant tree)
    def _visit(dependant: Any) -> None:
        if dependant is None:
            return
        call = getattr(dependant, "call", None)
        if call is not None and hasattr(call, "_required_scopes"):
            scopes.update(call._required_scopes)
        for sub in getattr(dependant, "dependencies", []):
            _visit(sub)

    _visit(route.dependant)
    return frozenset(scopes)


def _collect_required_any_scopes(
    route: APIRoute | RouteContext,
) -> tuple[frozenset[str], ...]:
    """Return each OR-scope group declared on the route.

    Separate dependencies remain conjunctive: a role must satisfy at least
    one scope from every collected group.
    """

    groups: list[frozenset[str]] = []

    def _append(dependency: Any) -> None:
        raw = getattr(dependency, "_required_any_scopes", None)
        if raw:
            group = frozenset(raw)
            if group not in groups:
                groups.append(group)

    for dep in getattr(route, "dependencies", []):
        dependency = getattr(dep, "dependency", None)
        if dependency is not None:
            _append(dependency)

    def _visit(dependant: Any) -> None:
        if dependant is None:
            return
        call = getattr(dependant, "call", None)
        if call is not None:
            _append(call)
        for sub in getattr(dependant, "dependencies", []):
            _visit(sub)

    _visit(route.dependant)
    return tuple(groups)


def _collect_required_roles(route: APIRoute | RouteContext) -> frozenset[str]:
    """Return all roles required by ``require_roles(...)`` on this route."""
    roles: set[str] = set()

    for dep in getattr(route, "dependencies", []):
        dependency = getattr(dep, "dependency", None)
        if dependency is not None and hasattr(dependency, "_required_roles"):
            roles.update(dependency._required_roles)

    def _visit(dependant: Any) -> None:
        if dependant is None:
            return
        call = getattr(dependant, "call", None)
        if call is not None and hasattr(call, "_required_roles"):
            roles.update(call._required_roles)
        for sub in getattr(dependant, "dependencies", []):
            _visit(sub)

    _visit(route.dependant)
    return frozenset(roles)


def _has_auth_dependency(
    route: APIRoute | RouteContext, *, optional: bool = False
) -> bool:
    """Return True if the route depends on any auth callable.

    When ``optional=False`` only ``get_current_user`` / ``get_current_user_with_db``
    count. When ``optional=True`` ``get_current_user_optional`` counts as well.
    """
    targets = _ALL_AUTH_CALLABLES if optional else _MANDATORY_AUTH_CALLABLES

    for dep in getattr(route, "dependencies", []):
        dependency = getattr(dep, "dependency", None)
        if dependency in targets:
            return True

    def _visit(dependant: Any) -> bool:
        if dependant is None:
            return False
        call = getattr(dependant, "call", None)
        if call in targets:
            return True
        return any(_visit(sub) for sub in getattr(dependant, "dependencies", []))

    return _visit(route.dependant)


def _get_route_roles(route: APIRoute | RouteContext) -> frozenset[str | None]:
    """Determine which roles may see this route in OpenAPI documentation.

    * ``None`` in the result means the route is public (visible without auth).
    * If explicit scopes/roles are declared, only matching roles are returned.
    * If mandatory auth is present but no explicit scopes/roles, all
      authenticated roles are returned.
    * If only optional auth is present, the route is treated as public.
    """
    required_scopes = _collect_required_scopes(route)
    required_any_scopes = _collect_required_any_scopes(route)
    required_roles = _collect_required_roles(route)
    has_mandatory_auth = _has_auth_dependency(route, optional=False)

    all_role_names = frozenset(_ROLE_SCOPES.keys())
    roles: frozenset[str | None]

    if required_scopes or required_any_scopes:
        roles = frozenset(
            role
            for role, scopes in _ROLE_SCOPES.items()
            if required_scopes.issubset(scopes)
            and all(not scopes.isdisjoint(group) for group in required_any_scopes)
        )
    elif required_roles:
        roles = required_roles
    elif has_mandatory_auth:
        roles = all_role_names
    else:
        # Optional auth or no auth → public
        roles = frozenset([None, *all_role_names])

    return roles


def _apply_prefix_override(
    route_roles: frozenset[str | None],
    route_path: str,
    prefix_overrides: dict[str, frozenset[str]] | None,
) -> frozenset[str | None]:
    if not prefix_overrides:
        return route_roles
    for prefix, override_roles in prefix_overrides.items():
        if route_path.startswith(prefix):
            return (route_roles - {None}) & override_roles
    return route_roles


def _filter_schema_paths(
    schema: dict[str, Any], allowed: set[tuple[str, str]]
) -> set[str]:
    paths = schema.get("paths", {})
    used_tags: set[str] = set()

    for path, methods in list(paths.items()):
        filtered_methods: dict[str, Any] = {}
        for method, operation in methods.items():
            if method.lower() == "parameters":
                filtered_methods[method] = operation
                continue
            if (path, method.upper()) in allowed:
                filtered_methods[method] = operation
                used_tags.update(operation.get("tags", []))
        if filtered_methods and set(filtered_methods.keys()) != {"parameters"}:
            paths[path] = filtered_methods
        else:
            del paths[path]

    return used_tags


def _component_target(ref: str) -> tuple[str, str] | None:
    """Decode a local OpenAPI component JSON pointer."""

    if not ref.startswith(_COMPONENT_REF_PREFIX):
        return None
    pointer = ref[len(_COMPONENT_REF_PREFIX) :]
    parts = pointer.split("/", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None

    def _unescape(value: str) -> str:
        return value.replace("~1", "/").replace("~0", "~")

    return _unescape(parts[0]), _unescape(parts[1])


def _security_scheme_names(value: dict[str, Any]) -> set[str]:
    security = value.get("security")
    if not isinstance(security, list):
        return set()
    return {
        scheme_name
        for requirement in security
        if isinstance(requirement, dict)
        for scheme_name in requirement
    }


def _discriminator_targets(value: dict[str, Any]) -> list[tuple[str, str]]:
    discriminator = value.get("discriminator")
    if not isinstance(discriminator, dict):
        return []
    mapping = discriminator.get("mapping")
    if not isinstance(mapping, dict):
        return []

    targets: list[tuple[str, str]] = []
    for mapped_ref in mapping.values():
        if not isinstance(mapped_ref, str):
            continue
        target = _component_target(mapped_ref)
        targets.append(target if target is not None else ("schemas", mapped_ref))
    return targets


class _ComponentReachability:
    def __init__(self, components: dict[str, Any]) -> None:
        self.components = components
        self.reachable: dict[str, set[str]] = {}
        self.pending: deque[tuple[str, str]] = deque()

    def enqueue(self, section: str, name: str) -> None:
        section_items = self.components.get(section)
        if not isinstance(section_items, dict) or name not in section_items:
            return
        names = self.reachable.setdefault(section, set())
        if name in names:
            return
        names.add(name)
        self.pending.append((section, name))

    def scan(self, value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                self.scan(item)
            return
        if not isinstance(value, dict):
            return

        ref = value.get("$ref")
        target = _component_target(ref) if isinstance(ref, str) else None
        if target is not None:
            self.enqueue(*target)
        for scheme_name in _security_scheme_names(value):
            self.enqueue("securitySchemes", scheme_name)
        for discriminator_target in _discriminator_targets(value):
            self.enqueue(*discriminator_target)
        for item in value.values():
            self.scan(item)

    def walk(self, root: dict[str, Any]) -> None:
        self.scan(root)
        while self.pending:
            section, name = self.pending.popleft()
            section_items = self.components.get(section)
            if isinstance(section_items, dict):
                self.scan(section_items[name])

    def prune(self) -> None:
        for section, section_items in list(self.components.items()):
            if not isinstance(section_items, dict):
                continue
            kept_names = self.reachable.get(section, set())
            self.components[section] = {
                name: item
                for name, item in section_items.items()
                if name in kept_names
            }
            if not self.components[section]:
                del self.components[section]


def _prune_unreachable_components(schema: dict[str, Any]) -> None:
    """Keep only components reachable from the role-filtered document.

    Path filtering alone leaves private request/response schemas in a public
    OpenAPI document.  This graph walk starts outside ``components``, follows
    local component ``$ref`` pointers recursively, and then removes every
    unreachable node.  ``seen``/``reachable`` make cyclic schemas safe.

    Security schemes are named directly by Security Requirement Objects rather
    than through ``$ref``.  Discriminator mappings may likewise use a bare
    schema name, so both forms are added explicitly to the graph roots.
    """

    components = schema.get("components")
    if not isinstance(components, dict):
        return

    graph = _ComponentReachability(components)
    graph.walk({key: value for key, value in schema.items() if key != "components"})
    graph.prune()
    if not components:
        schema.pop("components", None)


def build_role_openapi_schemas(
    app: Any,
    base_schema: dict[str, Any],
    prefix_overrides: dict[str, frozenset[str]] | None = None,
) -> dict[str | None, dict[str, Any]]:
    """Return a mapping ``role -> filtered openapi schema``.

    ``None`` key holds the public (unauthenticated) schema.
    """
    all_roles = [*list(_ROLE_SCOPES.keys()), None]
    role_operations: dict[str | None, set[tuple[str, str]]] = {
        role: set() for role in all_roles
    }

    for route in iter_route_contexts(app.routes):
        if not isinstance(route.original_route, APIRoute):
            continue
        route_path = route.path
        if route_path is None:
            continue
        route_roles = _apply_prefix_override(
            _get_route_roles(route), route_path, prefix_overrides
        )
        for role in route_roles:
            for method in route.methods or ():
                if method.upper() == "HEAD":
                    continue
                role_operations[role].add((route_path, method.upper()))

    result: dict[str | None, dict[str, Any]] = {}
    for role in all_roles:
        schema = copy.deepcopy(base_schema)
        used_tags = _filter_schema_paths(schema, role_operations.get(role, set()))

        if "tags" in schema:
            schema["tags"] = [
                tag for tag in schema["tags"] if tag.get("name") in used_tags
            ]

        _prune_unreachable_components(schema)
        result[role] = schema

    return result
