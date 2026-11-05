#!/usr/bin/env python3
"""Read-only inspection of Open Knowledge Format v0.2 bundles.

This is an optional adapter, not a new memory store. It never indexes content,
executes computations, repairs documents or writes to the knowledge bundle.
Requires optional PyYAML for correct YAML frontmatter parsing.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MAX_DOCUMENTS = 2500
MAX_BYTES = 2_000_000
RESERVED = {"index.md", "log.md"}


class OKFError(ValueError):
    pass


def _yaml_parser():
    try:
        import yaml
    except ImportError as exc:
        raise OKFError("OKF support requires optional PyYAML: pip install -r requirements-okf.txt") from exc
    return yaml


def frontmatter(raw, filename):
    """Safely decode bounded YAML frontmatter and report its byte digest."""
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise OKFError("OKF document too large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OKFError("OKF requires UTF-8") from exc
    if not text.startswith("---\n"):
        return None
    pos = text.find("\n---\n", 4)
    if pos == -1:
        raise OKFError("unclosed YAML frontmatter")
    fm = text[4:pos]
    if len(fm.encode("utf-8")) > 64_000:
        raise OKFError("OKF metadata exceeds limit")
    yaml = _yaml_parser()
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError as exc:
        raise OKFError("invalid YAML frontmatter") from exc
    if not isinstance(data, dict) or any(not isinstance(k, str) for k in data):
        raise OKFError("frontmatter must be an object with string keys")
    return data


def inspect(bundle):
    """Return bounded file records with content hashes and conservative findings.

    Does not reject unrecognized OKF types or optional fields. This is a useful
    structural validation, not full external certification of all OKF v0.2 rules.
    """
    if not isinstance(bundle, Path) or bundle.is_symlink() or not bundle.is_dir():
        raise OKFError("bundle must be an existing nonsymlink directory")
    root = bundle.resolve(strict=True)
    records = []
    findings = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(d for d in directories
                                if not (current_path / d).is_symlink() and d != ".git")
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                findings.append({"file": str(path.relative_to(root)), "code": "unsafe-file"})
                continue
            if len(records) >= MAX_DOCUMENTS:
                raise OKFError("too many knowledge documents")
            raw = path.read_bytes()
            if len(raw) > MAX_BYTES:
                raise OKFError("knowledge document exceeds size limit")
            relative = path.relative_to(root).as_posix()
            metadata = frontmatter(raw, relative)
            if name == "index.md":
                if metadata is not None and relative != "index.md":
                    findings.append({"file": relative, "code": "reserved-index-frontmatter"})
                if relative == "index.md" and metadata is not None:
                    v = metadata.get("okf_version")
                    if v is not None and str(v) != "0.2":
                        findings.append({"file": relative, "code": "unknown-okf-version"})
            elif name == "log.md":
                if metadata is not None:
                    findings.append({"file": relative, "code": "reserved-log-frontmatter"})
            elif metadata is None or not isinstance(metadata.get("type"), str) or not metadata["type"].strip():
                findings.append({"file": relative, "code": "missing-type-frontmatter"})
            if name in ("Index.md", "Log.md"):
                findings.append({"file": relative, "code": "reserved-case"})
            rows = {
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "type": "index" if name == "index.md" else "log" if name == "log.md"
                         else metadata.get("type") if metadata else None,
                "title": metadata.get("title") if metadata else None,
            }
            # Delegation context works on project-relative paths only; do not
            # manufacture one for an external bundle.
            try:
                project_relative = path.relative_to(Path(__file__).resolve().parents[1]).as_posix()
                rows["project_context_path"] = project_relative
            except ValueError:
                pass
            if metadata:
                for key in ("status", "stale_after", "sources", "generated", "verified"):
                    if key in metadata:
                        # Preserve native metadata for consumers; do not infer
                        # human review or freshness when fields are absent.
                        rows[key] = metadata[key]
            records.append(rows)
    return {
        "format": "okf", "target_version": "0.2", "bundle": str(root),
        "documents": records, "count": len(records), "findings": findings,
        "conformant_structure": not findings,
        "note": "Structural subset only; unknown types and optional metadata are preserved. No independent provenance, trust or attestation has been verified."
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("inspect",))
    p.add_argument("bundle", type=Path)
    args = p.parse_args(argv)
    try:
        print(json.dumps(inspect(args.bundle), ensure_ascii=False, indent=2, default=str))
        return 0
    except (OKFError, OSError) as exc:
        print("okf: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
