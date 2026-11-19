"""Project templates the loop starts from (DOSSIER.md §7.7: templates
carry the boilerplate, so the model writes less and gets less wrong).

A template is a folder of plain files in the §5.4 project layout —
``src/reblend/addon.py``, ``src/blender/__init__.py``,
``src/shared/`` modules, README — copied into a new project. A
template carries no manifest: the emitters build the manifests from
the project.

This module finds templates (``template_dir``, ``list_templates``)
and starts projects from them (``create_project_from_template``).
The copy lives here, not in the project model, because this module
is the one that knows what a template holds; the project model only
knows what a project holds.
"""

import shutil
from pathlib import Path

from devsuite.projects.project import (
    DEFAULT_AUTHOR,
    DEFAULT_VERSION,
    create_project,
)


def template_dir(name: str) -> Path:
    """The folder holding the template called ``name``.

    Returns the path whether or not the folder exists — callers check
    ``.is_dir()`` and say so in plain words when a template is missing.
    """
    return Path(__file__).resolve().parent / name


def list_templates() -> list[dict]:
    """Every template, found by scanning the templates folder.

    A template is a folder with a README.md in it, so a new template
    appears here without code changes. Returns a list of dicts —
    ``name`` (the folder name), ``path``, ``description`` (the first
    content line of the README, or an empty string) — sorted by
    name. Never raises: a README that cannot be read gives an empty
    description.
    """
    base = Path(__file__).resolve().parent
    templates = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "README.md").is_file():
            continue
        templates.append(
            {
                "name": child.name,
                "path": child,
                "description": _template_summary(child),
            }
        )
    return templates


def _template_summary(template_path: Path) -> str:
    """The template's one-line description: the first line of its
    README that is not blank and not a heading. Empty when the
    README has no such line, or cannot be read."""
    try:
        text = (template_path / "README.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def create_project_from_template(
    template,
    path,
    *,
    name: str,
    targets: list | None = None,
    description: str | None = None,
    version: str = DEFAULT_VERSION,
    author: str = DEFAULT_AUTHOR,
) -> tuple[object | None, str | None]:
    """Create a project at ``path`` from the template called ``template``.

    Creates the project (``create_project``) and copies the template
    tree — ``src/`` and ``README.md`` — into it. ``description``
    defaults to the template's own one-line description. Returns
    ``(project, error)`` in the usual plain-words shape: a missing
    template, a folder that already holds files, or template files
    that cannot be copied all come back as sentences, never as a
    crash.
    """
    source = template_dir(template)
    if not source.is_dir():
        return None, (
            f"There is no template called '{template}', so I could "
            "not start a project from it. Check the name and try again."
        )
    if description is None:
        description = _template_summary(source)
    project, error = create_project(
        path,
        name=name,
        targets=targets,
        description=description,
        version=version,
        author=author,
    )
    if error is not None:
        return None, error
    try:
        if (source / "src").is_dir():
            shutil.copytree(
                source / "src", project.root / "src", dirs_exist_ok=True
            )
        if (source / "README.md").is_file():
            shutil.copy2(source / "README.md", project.root / "README.md")
    except OSError:
        return None, (
            "The project was made, but I could not copy the template "
            "files into it. Check the project folder can be written "
            "to, and copy the template files by hand if needed."
        )
    return project, None
