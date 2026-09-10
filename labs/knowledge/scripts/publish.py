"""จัด publication สำหรับทดสอบ ไม่ถือเป็นการอนุมัติความถูกต้องของเนื้อหา"""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("root", nargs="?", default="../../knowledge")
args = parser.parse_args()
root = Path(args.root).resolve()
previous_path = root / "publication.json"
previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
old = {d["id"]: d for d in previous.get("documents", [])}
documents = []
for path in sorted((root / "source").rglob("*.md")):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise SystemExit("ไม่รับ symlink หรือไฟล์นอก root")
    if path.name.lower() == "readme.md":
        continue
    content = path.read_text(encoding="utf-8")
    title = next((line.lstrip("# ") for line in content.splitlines() if line.startswith("# ")), path.stem)
    relative = path.relative_to(root).as_posix()
    documents.append({"id": relative.removeprefix("source/"), "path": relative, "title": title,
        "sha256": hashlib.sha256(content.encode()).hexdigest(), "status": "published",
        "content_review": "unverified_import", "effective_from": None, "effective_until": None})
for document in documents:
    prior = old.get(document["id"], {})
    for field in ("status", "effective_from", "effective_until"):
        if field in prior:
            document[field] = prior[field]
    if prior.get("sha256") == document["sha256"]:
        document["content_review"] = prior.get("content_review", "unverified_import")
manifest = {"schema_version": 1, "purpose": "knowledge_lab_not_production_approval", "documents": documents}
temporary = root / "publication.json.tmp"
temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(root / "publication.json")
print(f"จัด publication สำหรับทดสอบ {len(documents)} เอกสาร")
