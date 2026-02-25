#!/usr/bin/env python3
#####################################################################################################################################################################################################
# Project:       Juniper
# Sub-Project:   juniper-cascor-worker
# Application:   juniper_cascor_worker
# File Name:     check_doc_links.py
# Author:        Paul Calnon
# Version:       0.4.2
#
# Date Created:  2026-02-25
# Last Modified: 2026-02-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Validates internal links in markdown documentation files.
#    Checks that relative file links point to existing files and
#    that same-file anchor links reference existing headings.
#    External URLs (http/https/mailto) are skipped.
#
# Usage:
#    python scripts/check_doc_links.py              # Scan all .md files
#    python scripts/check_doc_links.py --verbose    # Show all links checked
#    python scripts/check_doc_links.py docs/ notes/ # Scan specific directories
#
# Exit Codes:
#    0 - All links valid
#    1 - Broken links found
#
# References:
#    - RD-014: Add Documentation Build Step to CI
#####################################################################################################################################################################################################

"""Validate internal links in markdown documentation files.

Scans markdown files for relative links and anchor references,
verifying that target files exist and heading anchors are valid.
"""

import re
import sys
import unicodedata
from pathlib import Path

# Regex to find markdown links: [text](target)
# Captures the target (group 1) and the full match for line reporting
_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Prefixes that indicate external URLs (skip these)
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "ftp://")

# File extensions to treat as documentation
_DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}

# Directories to skip during scanning
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".egg-info",
    "htmlcov",
    ".trunk",
    ".vscode",
    ".idea",
}

# Directories to exclude from link validation (contain expected broken links)
# - templates/: placeholder links (LINK_TO_PHASE0_README, [VERIFICATION_REPORT_FILE], etc.)
# - history/: archived PR descriptions and plans referencing old monorepo paths
_EXCLUDE_DIRS: set[str] = set()


def _heading_to_anchor(heading_text: str) -> str:
    """Convert a markdown heading to its GitHub-style anchor ID.

    GitHub anchor generation rules:
    - Convert to lowercase
    - Remove punctuation (except hyphens and spaces)
    - Replace spaces with hyphens
    - Strip leading/trailing hyphens

    Args:
        heading_text: The heading text (without the # prefix).

    Returns:
        The anchor string (without the leading #).
    """
    text = heading_text.strip().lower()
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    # Remove characters that aren't alphanumeric, spaces, or hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    # Replace each whitespace character with a hyphen (preserves double-space → --)
    text = re.sub(r"\s", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    return text


def _extract_headings(content: str) -> set[str]:
    """Extract all heading anchors from markdown content.

    Args:
        content: The markdown file content.

    Returns:
        Set of anchor strings (without leading #).
    """
    anchors = set()
    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            heading_text = match.group(2).strip()
            anchors.add(_heading_to_anchor(heading_text))
    return anchors


def _find_markdown_files(search_paths: list[Path], repo_root: Path, exclude_dirs: set[str] | None = None) -> list[Path]:
    """Find all markdown files in the given paths.

    Args:
        search_paths: Directories or files to scan.
        repo_root: Repository root for default scanning.
        exclude_dirs: Additional directory names to exclude.

    Returns:
        Sorted list of markdown file paths.
    """
    skip = _SKIP_DIRS | (exclude_dirs or set()) | _EXCLUDE_DIRS
    md_files = set()

    for path in search_paths:
        if path.is_file() and path.suffix in _DOC_EXTENSIONS:
            # Skip broken symlinks
            if path.is_symlink() and not path.exists():
                continue
            # Check if file is under an excluded directory
            try:
                rel = path.relative_to(repo_root)
                if not any(part in skip for part in rel.parts):
                    md_files.add(path)
            except ValueError:
                md_files.add(path)
        elif path.is_dir():
            for ext in _DOC_EXTENSIONS:
                for f in path.rglob(f"*{ext}"):
                    # Skip broken symlinks
                    if f.is_symlink() and not f.exists():
                        continue
                    try:
                        rel = f.relative_to(repo_root)
                        if not any(part in skip for part in rel.parts):
                            md_files.add(f)
                    except ValueError:
                        if not any(part in skip for part in f.parts):
                            md_files.add(f)

    return sorted(md_files)


def _validate_file(md_file: Path, repo_root: Path, verbose: bool = False) -> list[str]:
    """Validate all internal links in a single markdown file.

    Args:
        md_file: Path to the markdown file.
        repo_root: Repository root for resolving relative paths.
        verbose: If True, print each link checked.

    Returns:
        List of error messages for broken links.
    """
    errors = []
    content = md_file.read_text(encoding="utf-8", errors="replace")
    headings = _extract_headings(content)
    file_dir = md_file.parent

    for line_num, line in enumerate(content.splitlines(), start=1):
        for match in _LINK_PATTERN.finditer(line):
            link_text = match.group(1)
            target = match.group(2).strip()

            # Skip external URLs
            if any(target.startswith(prefix) for prefix in _EXTERNAL_PREFIXES):
                if verbose:
                    print(f"  SKIP (external): {md_file}:{line_num} -> {target}")
                continue

            # Skip image badges and data URIs
            if target.startswith("data:") or target.startswith("//"):
                continue

            # Parse target into file path and optional anchor
            if "#" in target:
                file_part, anchor = target.split("#", 1)
            else:
                file_part = target
                anchor = None

            # Same-file anchor link
            if not file_part:
                if anchor and anchor not in headings:
                    errors.append(f"  {md_file}:{line_num}: broken anchor #{anchor} (heading not found)")
                elif verbose:
                    print(f"  OK (anchor): {md_file}:{line_num} -> #{anchor}")
                continue

            # Resolve relative file path
            target_path = (file_dir / file_part).resolve()

            # Also try resolving from repo root (some links use repo-relative paths)
            target_path_from_root = (repo_root / file_part).resolve()

            if target_path.exists() or target_path_from_root.exists():
                if verbose:
                    print(f"  OK (file): {md_file}:{line_num} -> {file_part}")
            else:
                rel_source = md_file.relative_to(repo_root)
                errors.append(f"  {rel_source}:{line_num}: broken link [{link_text}]({target}) -> file not found")

    return errors


def main() -> int:
    """Run documentation link validation.

    Returns:
        0 if all links are valid, 1 if broken links found.
    """
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    exclude_dirs: set[str] = set()

    # Parse --exclude flags
    argv = sys.argv[1:]
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--exclude" and i + 1 < len(argv):
            exclude_dirs.add(argv[i + 1])
            i += 2
        elif argv[i].startswith("--exclude="):
            exclude_dirs.add(argv[i].split("=", 1)[1])
            i += 1
        elif not argv[i].startswith("-"):
            positional.append(argv[i])
            i += 1
        else:
            i += 1

    # Determine repo root (script is in scripts/ subdir)
    repo_root = Path(__file__).resolve().parent.parent

    # Determine search paths
    if positional:
        search_paths = [repo_root / a for a in positional]
    else:
        # Default: scan all markdown files in the repo
        search_paths = [repo_root]

    print("=" * 60)
    print("Documentation Link Validation")
    print("=" * 60)
    if exclude_dirs:
        print(f"Excluding directories: {', '.join(sorted(exclude_dirs))}")

    md_files = _find_markdown_files(search_paths, repo_root, exclude_dirs)
    print(f"\nScanning {len(md_files)} markdown files...\n")

    all_errors = []
    files_with_errors = 0

    for md_file in md_files:
        errors = _validate_file(md_file, repo_root, verbose=verbose)
        if errors:
            files_with_errors += 1
            all_errors.extend(errors)

    # Report results
    print("-" * 60)
    if all_errors:
        print(f"\nFOUND {len(all_errors)} broken link(s) in {files_with_errors} file(s):\n")
        for error in all_errors:
            print(error)
        print(f"\n{'=' * 60}")
        print("FAILED: Documentation link validation")
        print(f"{'=' * 60}")
        return 1
    else:
        print(f"\nAll links valid across {len(md_files)} files.")
        print(f"\n{'=' * 60}")
        print("PASSED: Documentation link validation")
        print(f"{'=' * 60}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
