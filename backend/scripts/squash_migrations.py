#!/usr/bin/env python3
r"""Squash all Alembic migrations into a single file.

Usage:
    uv run python scripts/squash_migrations.py

What it does:
    1. Reads every file in alembic/versions/ matching \d+_*.py
    2. Parses the AST and extracts:
       - top-level imports
       - top-level helper functions / constants
       - the body of each upgrade() function
    3. Writes one new migration: alembic/versions/001_squashed.py
    4. Deletes old migrations (they are in git history if you need them).

After running, the new migration is the only head and starts from base.
You can then `alembic stamp head` on an already-migrated database.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS_DIR = Path("alembic/versions")



def _get_source_segment(source: str, node: ast.AST) -> str:
    """Best-effort source extraction; falls back to ast.unparse on 3.9+."""
    try:
        return ast.unparse(node)
    except AttributeError:  # pragma: no cover
        # Python < 3.9 – not supported in this project (3.12)
        raise


def extract_migration_parts(source: str, path: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (imports, helpers, upgrade_body_lines)."""
    tree = ast.parse(source)

    imports: list[str] = []
    helpers: list[str] = []
    upgrade_body: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            seg = _get_source_segment(source, node)
            # Filter out the alembic migration boiler-plate revision vars
            if seg.strip().startswith(("revision ", "down_revision", "branch_labels", "depends_on")):
                continue
            imports.append(seg)
        elif isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            for stmt in node.body:
                # Drop docstrings inside upgrade
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    continue
                upgrade_body.append(_get_source_segment(source, stmt))
        elif isinstance(node, ast.Assign):
            # Keep assignments that look like module-level constants (UPPER_CASE or _private)
            # but skip revision metadata
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in ("revision", "down_revision", "branch_labels", "depends_on"):
                    continue
            helpers.append(_get_source_segment(source, node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # helper functions except upgrade/downgrade
            if node.name in ("upgrade", "downgrade"):
                continue
            helpers.append(_get_source_segment(source, node))
        elif isinstance(node, ast.ClassDef):
            helpers.append(_get_source_segment(source, node))

    return imports, helpers, upgrade_body


def main() -> int:
    version_files = sorted(
        VERSIONS_DIR.glob("[0-9][0-9][0-9]_*.py"),
        key=lambda p: int(p.stem.split("_", 1)[0]),
    )

    if not version_files:
        return 1

    all_imports: list[str] = []
    all_helpers: list[str] = []
    all_upgrade_stmts: list[str] = []

    seen_imports: set[str] = set()

    for vf in version_files:
        source = vf.read_text(encoding="utf-8")
        imports, helpers, body = extract_migration_parts(source, vf)

        for imp in imports:
            key = imp.strip()
            if key not in seen_imports:
                seen_imports.add(key)
                all_imports.append(imp)

        if helpers:
            all_helpers.append(f"# ── helpers from {vf.name} ──")
            all_helpers.extend(helpers)

        if body:
            all_upgrade_stmts.append(f"    # ── {vf.name} ──")
            for stmt in body:
                # indent to sit inside def upgrade():
                indented = "    " + stmt.replace("\n", "\n    ")
                all_upgrade_stmts.append(indented)

    # Build the squashed migration
    lines: list[str] = [
        '"""Squashed migration.',
        "",
        "Revision ID: 001",
        "Revises:",
        f"Create Date: {__import__('datetime').datetime.now().isoformat()}",
        '"""',
        "",
    ]
    lines.extend(all_imports)
    lines.append("")
    lines.append('revision = "001"')
    lines.append('down_revision = None')
    lines.append('branch_labels = None')
    lines.append('depends_on = None')
    lines.append("")

    if all_helpers:
        lines.extend(all_helpers)
        lines.append("")

    lines.append("")
    lines.append("def upgrade() -> None:")
    lines.extend(all_upgrade_stmts)
    lines.append("")
    lines.append("")
    lines.append("def downgrade() -> None:")
    lines.append('    raise NotImplementedError("Squashed migration downgrade is not supported.")')
    lines.append("")

    content = "\n".join(lines)

    # Remove old migrations
    for vf in version_files:
        vf.unlink()

    # Write new squashed migration
    new_path = VERSIONS_DIR / "001_squashed.py"
    new_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
