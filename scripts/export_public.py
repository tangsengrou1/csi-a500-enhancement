"""Export a conservative source-only release, without copying Git history or datasets."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "CONTRIBUTING.md", ".gitignore", "LICENSE", "LICENSE.md"}
DATA_DOCS = {"Data/Wind导出清单.md", "Data/data_dictionary.csv"}
CODE_SUFFIXES = {".py", ".json", ".md", ".txt", ".mjs"}


def allowed(name):
    p = Path(name)
    if any(part.startswith(".") for part in p.parts) and p.parts[0] != ".github" and name != ".gitignore":
        return False
    if name in ROOT_FILES or name in DATA_DOCS:
        return True
    if p.parts[0] == "Code":
        return p.suffix in CODE_SUFFIXES and not {"node_modules", "__pycache__"}.intersection(p.parts)
    if p.parts[0] in {"docs", "scripts"}:
        return p.suffix in {".md", ".py"}
    if p.parts[0] == ".github":
        return p.suffix in {".md", ".yml", ".yaml"}
    if p.parts[0] in {"Data", "Result"}:
        return p.name == "README.md" and len(p.parts) == 3
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must be a new directory; existing files are never overwritten.")
    if output == ROOT or ROOT.is_relative_to(output):
        parser.error("Output cannot contain the source repository.")
    # Include tracked and new source files, but respect local ignore rules.
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    candidates = []
    for name in sorted(set(filter(None, names))):
        source = ROOT / name
        if allowed(name) and source.is_file() and not source.is_symlink():
            if not source.resolve().is_relative_to(ROOT):
                raise ValueError("Source outside repository: " + name)
            candidates.append((name, source))
    output.mkdir(parents=True)
    manifest = {}
    for name, source in candidates:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "EXPORT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported {len(manifest)} files to {output}")
    print("No Git history included. Review source text and choose a license before publication.")


if __name__ == "__main__":
    main()
