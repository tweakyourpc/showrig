"""Declarative creative packs; no scripts or network resources are executed."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .jobs import write_json


def validate_pack(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Choose a Showrig pack with schema 1.")
    if set(value) - {"schema", "id", "name", "author", "license", "templates", "themes"}:
        raise ValueError("Packs support templates and themes, not executable plug-ins.")
    result = copy.deepcopy(value)
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,47}", str(value.get("id", ""))):
        raise ValueError("Pack ID must be 2–48 lowercase letters, numbers or hyphens.")
    for key in ("name", "author", "license"):
        if not isinstance(value.get(key), str) or not 1 <= len(value[key].strip()) <= 160:
            raise ValueError(f"Include a {key} of 1–160 characters.")
    for kind in ("templates", "themes"):
        items = result.setdefault(kind, [])
        if not isinstance(items, list) or len(items) > 24:
            raise ValueError(f"Use at most 24 {kind} per pack.")
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Pack entries must be objects.")
            if not re.fullmatch(r"[a-z][a-z0-9-]{1,47}", str(item.get("id", ""))) or item["id"] in seen:
                raise ValueError("Entries need unique lowercase IDs.")
            seen.add(item["id"])
            if not isinstance(item.get("name"), str) or not 1 <= len(item["name"]) <= 80:
                raise ValueError("Entries need names of 1–80 characters.")
            if kind == "templates":
                if set(item) - {"id", "name", "description", "prompts", "format", "category"}:
                    raise ValueError("Unknown template field.")
                if not isinstance(item.get("description", ""), str) or len(item.get("description", "")) > 400:
                    raise ValueError("Description must be text of up to 400 characters.")
                prompts = item.get("prompts")
                if not isinstance(prompts, list) or not 1 <= len(prompts) <= 40 or any(not isinstance(p, str) or not 1 <= len(p.strip()) <= 300 for p in prompts):
                    raise ValueError("Templates need 1–40 prompts of up to 300 characters.")
                if item.get("format", "landscape") not in ("landscape", "vertical", "square"):
                    raise ValueError("Choose landscape, vertical or square.")
                if item.get("category", "Personal") not in ("Show", "Teach", "Announce", "Personal"):
                    raise ValueError("Choose a supported category.")
            else:
                if set(item) - {"id", "name", "accent", "background", "titles", "transitions", "pushIn"}:
                    raise ValueError("Unknown theme field.")
                for color in ("accent", "background"):
                    if not isinstance(item.get(color), str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item[color]):
                        raise ValueError("Theme colors must be six-digit hex colors.")
                if item.setdefault("titles", "rise") not in ("rise", "typewriter", "none") or item.setdefault("transitions", "simple") not in ("cinematic", "simple", "cuts"):
                    raise ValueError("Unsupported title or transition style.")
                push = item.setdefault("pushIn", 0)
                if isinstance(push, bool) or not isinstance(push, (int, float)) or not 0 <= push <= 20:
                    raise ValueError("Theme push-in must be between 0 and 20.")
    if not result["templates"] and not result["themes"]:
        raise ValueError("Add at least one template or theme.")
    return result


def catalog(root: Path) -> dict:
    packs, warnings = [], []
    folder = root / ".extensions"
    if folder.is_symlink():
        return {"packs": [], "warnings": ["Pack folder must be inside this library."]}
    for file in sorted(folder.glob("*.json")):
        try:
            if file.is_symlink() or file.stat().st_size > 256_000:
                raise ValueError("Pack is linked or too large")
            packs.append(validate_pack(json.loads(file.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as error:
            warnings.append(f"{file.name}: {error}")
    return {"packs": packs, "warnings": warnings}


def install(root: Path, value: dict) -> dict:
    pack = validate_pack(value)
    directory = root / ".extensions"
    if directory.is_symlink():
        raise ValueError("Pack folder must be inside this library.")
    directory.mkdir(exist_ok=True)
    path = directory / (pack["id"] + ".json")
    if path.exists() or path.is_symlink():
        raise ValueError("Pack already installed. Use a new ID for a new revision.")
    write_json(path, pack)
    return pack


def entries(root: Path, kind: str) -> list[dict]:
    return [{**item, "id": f"pack.{pack['id']}.{item['id']}", "pack": pack["name"]}
            for pack in catalog(root)["packs"] for item in pack[kind]]
