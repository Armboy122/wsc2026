#!/usr/bin/env python3
"""ซิงก์คลังความรู้ PEA ที่เป็นแหล่งข้อมูลหลักไปยัง Gemini File Search store

นโยบายแหล่งข้อมูลที่สำคัญต่อความปลอดภัย: ซิงก์ได้เฉพาะไฟล์ภายใต้
``<corpus root>/source/`` เท่านั้น corpus root เริ่มต้นคือ ``<repo>/knowledge``
ดังนั้นการทำงานเริ่มต้นจะอัปโหลดเฉพาะ ``knowledge/source/**`` เท่านั้น ไฟล์ README,
manifest, ไฟล์ซ่อน และไฟล์ที่ไม่ใช่เอกสารจะไม่ถูกอัปโหลดไม่ว่าจะอยู่ลึกระดับใด
repository นี้ตั้งใจไม่รวมเนื้อหา PEA ไว้ใน ``source/`` (มีเพียง placeholder
ที่ไม่มีข้อเท็จจริง) อนุญาตให้วางได้เฉพาะข้อมูลส่งออก PEA ที่เป็นแหล่งข้อมูลหลัก
และได้รับอนุมัติจากหัวหน้าทีมแล้ว หากไม่มีข้อมูลส่งออกที่ได้รับอนุมัติ การซิงก์
จะไม่ดำเนินการใด ๆ และไม่สามารถเติมข้อเท็จจริงที่แต่งขึ้นลงใน store ได้

สคริปต์เก็บ source manifest แบบ SHA256 (ค่าเริ่มต้น: ``knowledge/manifest.json``)
ซึ่งจับคู่ path ที่สัมพันธ์กับ corpus แต่ละรายการกับ hash ของเนื้อหาและชื่อเอกสาร
ระยะไกล แต่ละครั้งจะอัปโหลดเฉพาะแหล่งข้อมูลใหม่หรือที่เปลี่ยนแปลง แหล่งข้อมูลที่
ไม่เปลี่ยนแปลงจะได้รับการแตะ และเอกสารระยะไกลที่แหล่งข้อมูลภายในหายไปจะถูกลบ
เมื่อระบุทั้ง ``--prune`` และ ``--yes`` เท่านั้น

แฟล็ก:
    --root      corpus root (ค่าเริ่มต้น: <repo>/knowledge); ซิงก์ได้เฉพาะ
                <root>/source/** หาก root ไม่มีไดเรกทอรี source/ ถือว่าใช้คำสั่งผิด
    --manifest  path ของ manifest (ค่าเริ่มต้น: <corpus root>/manifest.json หรือ
                knowledge/manifest.json สำหรับ root เริ่มต้น)
    --file      จำกัดการทำงานไว้ที่ path เดียวที่สัมพันธ์กับ corpus (ระบุซ้ำได้) เช่น
                source/<approved-export>.md
    --store     ชื่อทรัพยากร File Search store (ค่าเริ่มต้น: $GEMINI_FILE_SEARCH_STORE)
    --dry-run   แสดงเฉพาะแผน ไม่อัปโหลดและไม่เขียน manifest
    --force     อัปโหลดแหล่งข้อมูลที่ไม่เปลี่ยนแปลงซ้ำด้วย
    --prune     ลบเอกสารระยะไกลที่แหล่งข้อมูลภายในหายไป (ต้องใช้ --yes)
    --yes       ยืนยันการลบแบบ prune ที่ทำลายข้อมูล
    --verbose   แสดงความคืบหน้ารายไฟล์

ค่าเริ่มต้นของผู้ให้บริการ: การแบ่ง chunk ใช้ค่าเริ่มต้นของผู้ให้บริการ
(จะไม่มีการส่งการตั้งค่า chunking) ความปลอดภัยด้าน Unicode: ชื่อแหล่งข้อมูลที่
ไม่ใช่ ASCII (เช่น ภาษาไทย) จะไม่ไปถึง HTTP header หรือฟิลด์คำขอที่ถูกปฏิเสธ
โดยแหล่งข้อมูลจะถูกอัปโหลดผ่านสำเนาชั่วคราวชื่อ ASCII ที่คง suffix และ byte เดิม
เพื่อให้ SDK อนุมาน MIME type สำหรับ upload header จาก path แบบ ASCII ได้
(SDK จะสะท้อน basename ของอาร์กิวเมนต์ path ไปยัง header
``X-Goog-Upload-File-Name`` ที่รับเฉพาะ ASCII) ขณะที่
``UploadToFileSearchStoreConfig`` จะไม่มี ``mime_type`` (SDK คัดลอกฟิลด์นั้น
ไปยัง request body ซึ่ง Gemini ปฏิเสธด้วย 400 INVALID_ARGUMENT สำหรับชนิด
DOCX ของผู้ผลิต) สำเนาชั่วคราวจะถูกลบทั้งเมื่อสำเร็จและในทุกเส้นทางที่ล้มเหลว
ชื่อแสดงผลระยะไกลเป็นรูปแบบ ASCII-safe ที่ให้ผลแน่นอนของ path ที่สัมพันธ์กับ
corpus พร้อม suffix ซึ่งเป็น path hash และจะส่ง path UTF-8 เดิมใน
``custom_metadata`` (JSON request body ไม่ใช่ header) เมื่อขนาดไม่เกินงบประมาณ
แบบเผื่อความปลอดภัย manifest ภายในจะเก็บ path UTF-8 ที่สัมพันธ์กับ corpus
แบบตรงกันทุกประการเป็น key เสมอ ทำให้ path เดิมยังคงใช้ได้แม้ยาวเกินกว่าจะใส่
metadata ส่วน SDK ``google-genai`` จะถูกนำเข้าแบบ lazy เพื่อให้ ``--dry-run``
ทำงานได้โดยไม่ต้องติดตั้ง SDK
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# รากของคลังข้อมูล (ค่าเริ่มต้น): เก็บ source/ (แผนผังย่อยเดียวที่ซิงก์ได้), manifest
# และเอกสาร/การทดสอบ โดยจะไม่มีสิ่งใดถูกอัปโหลดนอกจากไฟล์ภายใต้ source/
DEFAULT_CORPUS_ROOT = REPO_ROOT / "knowledge"
# อัปโหลดเฉพาะไฟล์ภายใต้ <corpus root>/source/** เท่านั้น (ปิดอย่างปลอดภัยเมื่อผิดพลาด)
SOURCE_DIR_NAME = "source"
MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

ENV_STORE = "GEMINI_FILE_SEARCH_STORE"
ENV_API_KEY = "GEMINI_API_KEY"
ENV_FALLBACK_API_KEY = "GOOGLE_API_KEY"

ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx", ".csv", ".html"}
# ไฟล์เอกสาร/ข้อมูลกำกับที่จะไม่ถูกอัปโหลดไม่ว่าจะอยู่ลึกระดับใด
# (เปรียบเทียบโดยไม่สนตัวพิมพ์เล็กหรือใหญ่)
EXCLUDED_FILENAMES = {MANIFEST_NAME, "readme.md"}

LRO_POLL_SECONDS = 0.5
LRO_TIMEOUT_SECONDS = 120.0
SHA256_CHUNK_SIZE = 1024 * 1024

# งบประมาณชื่อแสดงผลระยะไกล ผู้ให้บริการอนุญาต 512 อักขระ ส่วน 200 ช่วยให้ชื่อ
# เป็น ASCII-safe อย่างมั่นใจและเปรียบเทียบกันได้ในรายการ
DISPLAY_NAME_MAX_LENGTH = 200
# จำนวนเลขฐานสิบหกจาก SHA256 ของ path UTF-8 เดิมที่ต่อท้ายชื่อแสดงผลทุกชื่อ
# ที่ไม่ใช่ ASCII เพื่อไม่ให้ path ที่ต่างกันเกิดการชนกัน
DISPLAY_NAME_HASH_LENGTH = 12
# key ของ custom_metadata ที่เก็บ path ซึ่งสัมพันธ์กับ corpus แบบตรงกันทุกประการ (JSON body)
CUSTOM_METADATA_PATH_KEY = "corpus_rel_path"
# งบประมาณ byte UTF-8 แบบเผื่อความปลอดภัยสำหรับค่าสตริง custom-metadata
# ผู้ให้บริการไม่ได้ระบุขีดจำกัดไว้ ดังนั้น path ที่ยาวกว่านี้จึงอาศัย manifest
CUSTOM_METADATA_MAX_VALUE_BYTES = 256


def _is_ascii_printable(char: str) -> bool:
    return 0x20 <= ord(char) <= 0x7E


def ascii_display_name(rel_path: str) -> str:
    """สร้างชื่อแสดงผลระยะไกลแบบ ASCII-safe ที่ให้ผลแน่นอนสำหรับ path ที่สัมพันธ์กับ corpus

    path ที่เป็น ASCII ล้วน พิมพ์ได้ และอยู่ภายในงบประมาณความยาวจะผ่านไปโดย
    ไม่เปลี่ยนแปลง ทำให้ชื่อเอกสารที่ซิงก์แล้วคงที่ระหว่างการทำงานแต่ละครั้ง
    path อื่นทั้งหมด (เช่น ชื่อไฟล์ภาษาไทย ซึ่งทำให้ httpx ล้มเหลวเมื่อรั่วไปยัง
    header ที่รับเฉพาะ ASCII) จะถูกลดรูปเป็นโครง ASCII ที่พิมพ์ได้ โดยชุดอักขระ
    ที่ไม่ใช่ ASCII ต่อเนื่องกันจะยุบเป็น ``_`` ตัวเดียว แล้วนำเลขฐานสิบหก
    ``DISPLAY_NAME_HASH_LENGTH`` หลักแรกจาก SHA256 ของ path UTF-8 เดิมมาต่อก่อน
    extension ค่า hash ของ path รับประกันว่า path ต่างกันสองรายการจะไม่ชนกัน
    แม้โครง ASCII จะเหมือนกัน ขณะเดียวกันจะคง stem แบบ ASCII ที่จดจำได้และ
    extension ไว้เมื่อเป็นไปได้ ผลลัพธ์จะเป็น ASCII เสมอและยาวไม่เกิน
    ``DISPLAY_NAME_MAX_LENGTH`` อักขระ
    """
    if (
        rel_path
        and len(rel_path) <= DISPLAY_NAME_MAX_LENGTH
        and all(_is_ascii_printable(char) for char in rel_path)
    ):
        return rel_path
    digest = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:DISPLAY_NAME_HASH_LENGTH]
    skeleton = re.sub(
        r"_+", "_", "".join(char if _is_ascii_printable(char) else "_" for char in rel_path)
    )
    stem, ext = os.path.splitext(skeleton)
    stem = stem.rstrip(" _") or "file"
    if stem.endswith("/"):
        stem += "file"
    budget = max(DISPLAY_NAME_MAX_LENGTH - len(ext) - len(digest) - 1, len("file"))
    return f"{stem[:budget]}-{digest}{ext}"


def _ascii_temp_dir() -> str:
    """ไดเรกทอรี ASCII-safe สำหรับสำเนาชั่วคราวที่ใช้ในการอัปโหลด

    ``tempfile.gettempdir()`` เคารพค่า ``TMPDIR`` ซึ่งอาจไม่ใช่ ASCII ทำให้ SDK
    สะท้อนไดเรกทอรีของ path ชั่วคราวกลับเข้า header อีกครั้ง จึงย้อนกลับไปใช้
    realpath หรือ ``/tmp`` และปิดอย่างปลอดภัยเมื่อใช้ไม่ได้แม้แต่ตัวเลือกเหล่านั้น
    แทนที่จะปล่อยให้ path ที่ไม่ใช่ ASCII รั่วออกไป
    """
    raw = tempfile.gettempdir()
    for candidate in (raw, os.path.realpath(raw), "/tmp"):
        if candidate and os.path.isdir(candidate):
            try:
                candidate.encode("ascii")
            except UnicodeEncodeError:
                continue
            return candidate
    raise SyncError("ไม่มีไดเรกทอรีชั่วคราวแบบ ASCII-safe สำหรับการอัปโหลด")


def _ascii_temp_copy(local_path: Path) -> Path:
    """คัดลอกแหล่งข้อมูลไปยังไฟล์ชั่วคราวชื่อ ASCII โดยคง suffix ไว้

    SDK อนุมาน MIME type สำหรับการอัปโหลดจาก extension ของ path ไฟล์ และสะท้อน
    basename เข้า header ``X-Goog-Upload-File-Name`` ที่รับเฉพาะ ASCII ดังนั้น
    ชื่อสำเนาจึงเป็น ASCII ทั้งหมด (ชื่อสุ่มจาก ``tempfile`` ตามด้วย suffix เดิม
    ที่เป็น ASCII และพิมพ์ได้) และมี byte เหมือนแหล่งข้อมูล ผู้เรียกเป็นเจ้าของไฟล์
    และต้องลบไฟล์นั้น (บล็อก finally ใน :meth:`GeminiStoreProvider.upload`)
    """
    suffix = local_path.suffix
    if suffix and not all(_is_ascii_printable(char) for char in suffix):
        suffix = ""
    temp_dir = _ascii_temp_dir()
    handle_fd, temp_name = tempfile.mkstemp(prefix="pea-sync-", suffix=suffix, dir=temp_dir)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "wb") as dst, local_path.open("rb") as src:
            shutil.copyfileobj(src, dst, SHA256_CHUNK_SIZE)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise SyncError(f"ไม่สามารถจัดเตรียม {local_path.name} สำหรับการอัปโหลดได้") from exc
    return temp_path


def _custom_metadata(genai, rel_path: str) -> list | None:
    """ใช้ path UTF-8 เดิมเป็น metadata ระยะไกลเมื่อขนาดอยู่ภายในงบประมาณ

    ``custom_metadata`` จะถูก serialize ลงใน JSON request body ไม่ใช่ header
    ที่รับเฉพาะ ASCII จึงคง path ที่สัมพันธ์กับ corpus แบบตรงกันทุกประการไว้ได้
    path ที่เกินงบประมาณค่าแบบเผื่อความปลอดภัยจะไม่ถูกแต่งหรือตัดทอนบนระบบระยะไกล
    โดย manifest ภายในยังคงเป็นระเบียนหลักสำหรับทุก path
    """
    if len(rel_path.encode("utf-8")) > CUSTOM_METADATA_MAX_VALUE_BYTES:
        return None
    return [genai.types.CustomMetadata(key=CUSTOM_METADATA_PATH_KEY, string_value=rel_path)]


class SyncError(Exception):
    """ความล้มเหลวของผู้ให้บริการหรือ I/O พร้อมข้อความที่ปลอดภัยสำหรับผู้ใช้"""


class UsageError(SyncError):
    """การใช้บรรทัดคำสั่งไม่ถูกต้อง"""


@dataclass(frozen=True)
class LocalSource:
    """ไฟล์แหล่งข้อมูลหนึ่งไฟล์ที่ซิงก์ได้ ซึ่งระบุด้วย path แบบ POSIX ที่สัมพันธ์กับ corpus"""

    rel_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class UploadItem:
    """แหล่งข้อมูลที่ต้องอัปโหลดหรืออัปโหลดซ้ำในการทำงานครั้งนี้"""

    rel_path: str
    sha256: str
    size_bytes: int
    kind: str  # "new" | "changed" | "forced"


@dataclass(frozen=True)
class PruneItem:
    """รายการใน manifest ที่ไม่มีแหล่งข้อมูลภายในอยู่แล้ว"""

    rel_path: str
    document_name: str | None


@dataclass(frozen=True)
class SyncPlan:
    """ผลต่างล้วนระหว่าง corpus ภายในกับ manifest"""

    uploads: tuple[UploadItem, ...]
    unchanged: tuple[str, ...]
    prune: tuple[PruneItem, ...]


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(SHA256_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_sources(corpus_root: Path, only: tuple[str, ...] = ()) -> list[LocalSource]:
    """แสดงรายการแหล่งข้อมูลที่ซิงก์ได้ภายใต้ ``corpus_root`` (เรียงลำดับคงที่)

    นโยบายแหล่งข้อมูลแบบปิดอย่างปลอดภัยเมื่อผิดพลาด: ซิงก์ได้เฉพาะไฟล์ภายใน
    ``corpus_root/source/`` เท่านั้น ส่วนสิ่งอื่นทั้งหมดใน corpus (README,
    เอกสาร, การทดสอบ, metadata) จะอัปโหลดไม่ได้ ภายใน ``source/`` จะข้ามไฟล์
    หรือไดเรกทอรีที่ซ่อนอยู่ ไฟล์ README และ manifest (ทุกแบบตัวพิมพ์และทุกระดับ)
    รวมถึงไฟล์ที่ไม่มี suffix เอกสารที่อนุญาต corpus root ที่ไม่มีไดเรกทอรี
    ``source/`` ถือเป็น :class:`UsageError` ไม่ใช่การไม่ดำเนินการอย่างเงียบ ๆ
    path สัมพัทธ์จะสัมพันธ์กับ corpus root (``source/...``) เมื่อระบุ ``only``
    ทุก path ที่ระบุต้องชี้ไปยังแหล่งข้อมูลที่ซิงก์ได้ มิฉะนั้นจะยก
    :class:`UsageError`
    """
    source_dir = corpus_root / SOURCE_DIR_NAME
    if not source_dir.is_dir():
        raise UsageError(
            f"รากของคลังข้อมูล {corpus_root} ไม่มีไดเรกทอรี {SOURCE_DIR_NAME}/; "
            f"ซิงก์ได้เฉพาะ {SOURCE_DIR_NAME}/** เท่านั้น"
        )
    found: list[LocalSource] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(corpus_root).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts):
            continue
        if path.name.lower() in EXCLUDED_FILENAMES:
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        found.append(
            LocalSource(
                rel_path=rel,
                sha256=compute_sha256(path),
                size_bytes=path.stat().st_size,
            )
        )
    if only:
        wanted = set(only)
        found = [source for source in found if source.rel_path in wanted]
        missing = sorted(
            path for path in wanted
            if path not in {source.rel_path for source in found}
        )
        if missing:
            raise UsageError(f"ไม่ใช่แหล่งข้อมูลในคลังที่ซิงก์ได้: {', '.join(missing)}")
        found.sort(key=lambda source: source.rel_path)
    return found


def load_manifest(manifest_path: Path) -> dict:
    """โหลด manifest โดยไฟล์ที่ไม่มีจะให้โครงเปล่า"""
    if not manifest_path.exists():
        return {"schemaVersion": MANIFEST_SCHEMA_VERSION, "storeName": None, "files": {}}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"ไม่สามารถอ่าน manifest {manifest_path.name}: JSON อ่านไม่ได้") from exc
    files = raw.get("files")
    if not isinstance(files, dict):
        raise SyncError(f"ไม่สามารถอ่าน manifest {manifest_path.name}: แผนผังไฟล์มีรูปแบบไม่ถูกต้อง")
    return {
        "schemaVersion": raw.get("schemaVersion", MANIFEST_SCHEMA_VERSION),
        "storeName": raw.get("storeName"),
        "files": files,
    }


def build_plan(
    local: list[LocalSource],
    manifest_files: dict,
    *,
    force: bool = False,
    scope: tuple[str, ...] | None = None,
) -> SyncPlan:
    """หาผลต่างของแหล่งข้อมูลภายในเทียบกับ manifest (ฟังก์ชันบริสุทธิ์ ไม่เข้าถึงผู้ให้บริการ)

    เมื่อกำหนด ``scope`` (``--file``) จะสร้างรายการอัปโหลดเฉพาะแหล่งข้อมูล
    ในขอบเขตและไม่สร้างรายการที่อาจ prune เนื่องจาก pruning เป็นการทำงานกับ
    corpus ทั้งหมด
    """
    uploads: list[UploadItem] = []
    unchanged: list[str] = []
    local_paths = {source.rel_path for source in local}
    for source in local:
        entry = manifest_files.get(source.rel_path)
        if entry is None:
            kind = "new"
        elif force:
            kind = "forced"
        elif not isinstance(entry, dict) or entry.get("sha256") != source.sha256:
            kind = "changed"
        else:
            unchanged.append(source.rel_path)
            continue
        uploads.append(
            UploadItem(
                rel_path=source.rel_path,
                sha256=source.sha256,
                size_bytes=source.size_bytes,
                kind=kind,
            )
        )
    prune: list[PruneItem] = []
    if scope is None:
        for rel_path, entry in sorted(manifest_files.items()):
            if rel_path in local_paths:
                continue
            document_name = entry.get("documentName") if isinstance(entry, dict) else None
            prune.append(PruneItem(rel_path=rel_path, document_name=document_name))
    return SyncPlan(tuple(uploads), tuple(unchanged), tuple(prune))


def write_manifest(manifest_path: Path, store_name: str | None, files: dict) -> None:
    """แทนที่ manifest แบบ atomic (ไฟล์ tmp + เปลี่ยนชื่อ)"""
    payload = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "storeName": store_name,
        "files": files,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, manifest_path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _import_genai():
    """นำเข้าผู้ให้บริการแบบ lazy โดยไม่บังคับว่าต้องมี SDK ขณะนำเข้าโมดูล"""
    try:
        from google import genai
    except ImportError as exc:
        raise SyncError(
            "ยังไม่ได้ติดตั้ง google-genai SDK; ให้เรียกใช้: pip install google-genai"
        ) from exc
    return genai


def _describe_error(error: object) -> str:
    """คำอธิบาย dict ข้อผิดพลาดของผู้ให้บริการแบบหนึ่งบรรทัดที่ปลอดภัยสำหรับผู้ใช้"""
    if isinstance(error, dict):
        status = error.get("status") or "ERROR"
        code = error.get("code", "?")
        return f"{status} (รหัส {code})"
    return "ข้อผิดพลาดจากผู้ให้บริการ"


class GeminiStoreProvider:
    """SDK adapter แบบบางสำหรับอัปโหลดแหล่งข้อมูลและลบเอกสารระยะไกล"""

    def __init__(self, store_name: str, api_key: str) -> None:
        self._store_name = store_name
        self._api_key = api_key

    def upload(self, local_path: Path, rel_path: str) -> str:
        """อัปโหลดแหล่งข้อมูลหนึ่งรายการและคืนชื่อเอกสารระยะไกล

        ความปลอดภัยด้าน Unicode + MIME (จากการทำซ้ำกับระบบจริง): ชื่อภาษาไทย
        ทำให้ httpx ล้มเหลวขณะ encode header เป็น ASCII และ ``config.mime_type``
        ที่ระบุชัดเจนจะถูก SDK คัดลอกไปยัง request body ซึ่ง Gemini ปฏิเสธชนิด
        DOCX ของผู้ผลิตด้วย 400 INVALID_ARGUMENT
        (``UploadToFileSearchStoreRequest.mime_type`` ไม่ถูกต้อง) ดังนั้นจึง
        จัดเตรียมแหล่งข้อมูลเป็นสำเนาชั่วคราวชื่อ ASCII ที่คง suffix และ byte เดิม
        (:func:`_ascii_temp_copy`) แล้วส่ง path นั้นให้ SDK โดยไม่ส่ง raw handle
        หรือ path ของ corpus และไม่มี ``mime_type`` ใน config เพื่อให้ SDK อนุมาน
        MIME type จาก extension แบบ ASCII สำหรับ upload header เท่านั้น สำเนาชั่วคราว
        จะถูกลบเมื่อสำเร็จและในทุกเส้นทางที่ล้มเหลว รวมถึงข้อผิดพลาดจากผู้ให้บริการ
        ชื่อแสดงผลเป็นรูปแบบ ASCII-safe ที่ให้ผลแน่นอนของ path ที่สัมพันธ์กับ corpus
        (:func:`ascii_display_name`) และ path UTF-8 เดิมจะส่งไปใน
        ``custom_metadata`` ซึ่งเป็น JSON request body ไม่ใช่ header เมื่อขนาดอยู่
        ภายในงบประมาณค่า โดย manifest ภายในจะคง path แบบตรงกันทุกประการเป็น key เสมอ
        จะไม่มีการส่งการตั้งค่า chunking และใช้การแบ่ง chunk เริ่มต้นของผู้ให้บริการ
        """
        genai = _import_genai()
        client = genai.Client(api_key=self._api_key)
        config_kwargs: dict = {
            "display_name": ascii_display_name(rel_path),
        }
        metadata = _custom_metadata(genai, rel_path)
        if metadata is not None:
            config_kwargs["custom_metadata"] = metadata
        temp_path = _ascii_temp_copy(local_path)
        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=self._store_name,
                file=str(temp_path),
                config=genai.types.UploadToFileSearchStoreConfig(**config_kwargs),
            )
            operation = self._wait_for_operation(client, operation)
            if operation.error:
                raise SyncError(
                    f"เกิดข้อผิดพลาดจากผู้ให้บริการขณะอัปโหลด {rel_path}: {_describe_error(operation.error)}"
                )
            response = operation.response
            document_name = (
                getattr(response, "document_name", None) if response is not None else None
            )
            if not document_name:
                raise SyncError(f"ผู้ให้บริการไม่ส่งคืนชื่อเอกสารสำหรับ {rel_path}")
            return document_name
        finally:
            temp_path.unlink(missing_ok=True)

    def delete_document(self, document_name: str) -> None:
        genai = _import_genai()
        client = genai.Client(api_key=self._api_key)
        client.file_search_stores.documents.delete(name=document_name)

    def _wait_for_operation(self, client, operation) -> object:
        if operation.done:
            return operation
        deadline = time.monotonic() + LRO_TIMEOUT_SECONDS
        while not operation.done:
            if time.monotonic() > deadline:
                raise SyncError("หมดเวลารอให้ผู้ให้บริการอัปโหลดเสร็จ")
            time.sleep(LRO_POLL_SECONDS)
            operation = client.operations.get(operation=operation.name)
        return operation


def _resolve_store_name(args: argparse.Namespace, manifest: dict) -> str | None:
    return args.store or os.environ.get(ENV_STORE) or manifest.get("storeName")


def run_sync(args: argparse.Namespace, provider: object | None = None) -> int:
    """ดำเนินการซิงก์และคืน exit code ของ process

    สามารถ inject ``provider`` สำหรับการทดสอบได้ เมื่อไม่ระบุจะสร้างแบบ lazy
    (และสร้างเมื่อกำลังจะอัปโหลดจริงหรือ prune เท่านั้น)
    """
    corpus_root = Path(args.root).expanduser().resolve() if args.root else DEFAULT_CORPUS_ROOT
    if not corpus_root.is_dir():
        raise UsageError(f"ไม่พบรากของคลังข้อมูล: {corpus_root}")
    manifest_path = (
        Path(args.manifest).expanduser().resolve() if args.manifest
        else corpus_root / MANIFEST_NAME
    )
    only = tuple(Path(path).as_posix() for path in (args.file or ()))

    local = discover_sources(corpus_root, only)
    manifest = load_manifest(manifest_path)
    plan = build_plan(local, manifest["files"], force=args.force, scope=only or None)
    store_name = _resolve_store_name(args, manifest)

    def log(message: str) -> None:
        if args.verbose:
            print(message)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}คลังข้อมูล: {corpus_root}")
    for item in plan.uploads:
        print(f"{prefix}upload {item.kind}: {item.rel_path}")
    print(f"{prefix}ไม่เปลี่ยนแปลง: {len(plan.unchanged)} ไฟล์")
    if plan.prune:
        for item in plan.prune:
            print(f"{prefix}รายการที่อาจตัดออก: {item.rel_path}")
    if args.dry_run:
        print(f"{prefix}ทดลองทำเสร็จแล้ว ไม่มีการอัปโหลดและไม่ได้แก้ไข manifest")
        return 0

    will_prune = bool(plan.prune) and args.prune and args.yes
    if plan.prune and args.prune and not args.yes:
        print(
            f"คำเตือน: ขอให้ตัดออกโดยไม่ระบุ --yes; "
            f"จึงข้ามการลบระยะไกล {len(plan.prune)} รายการ"
        )
    if not plan.uploads and not will_prune:
        print("up to date; nothing to do")
        return 0

    if provider is None:
        if not store_name:
            raise UsageError(
                "ยังไม่ได้กำหนดค่า File Search store (ตั้งค่า GEMINI_FILE_SEARCH_STORE หรือระบุ --store)"
            )
        api_key = os.environ.get(ENV_API_KEY) or os.environ.get(ENV_FALLBACK_API_KEY)
        if not api_key:
            raise UsageError("ยังไม่ได้กำหนด API key ของผู้ให้บริการ (ตั้งค่า GEMINI_API_KEY)")
        provider = GeminiStoreProvider(store_name, api_key)

    files = dict(manifest["files"])
    for item in plan.uploads:
        log(f"uploading {item.rel_path} ({item.size_bytes} bytes)")
        document_name = provider.upload(corpus_root / item.rel_path, item.rel_path)
        files[item.rel_path] = {
            "sha256": item.sha256,
            "sizeBytes": item.size_bytes,
            "documentName": document_name,
            "uploadedAt": utc_now_iso(),
        }
        write_manifest(manifest_path, store_name, files)
        log(f"uploaded {item.rel_path} -> {document_name}")

    pruned: list[str] = []
    if will_prune:
        for item in plan.prune:
            if item.document_name:
                log(f"กำลังลบเอกสารระยะไกลของ {item.rel_path}")
                provider.delete_document(item.document_name)
            files.pop(item.rel_path, None)
            pruned.append(item.rel_path)
        write_manifest(manifest_path, store_name, files)
    elif plan.prune:
        log(f"หมายเหตุ: ไม่ได้ตัดรายการ manifest ที่ล้าสมัย {len(plan.prune)} รายการออก (ไม่ได้ระบุ --prune)")

    print(
        f"เสร็จสิ้น: อัปโหลด {len(plan.uploads)}, ไม่เปลี่ยนแปลง {len(plan.unchanged)}, "
        f"ตัดออก {len(pruned)}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync_knowledge.py",
        description=(
            "ซิงก์คลังความรู้ PEA ที่เป็นแหล่งข้อมูลหลักไปยัง Gemini File Search "
            "store โดยจะอัปโหลดเฉพาะ <root>/source/** เท่านั้น repository ไม่มี "
            "เนื้อหา PEA ให้มา (ใช้เฉพาะข้อมูลส่งออกที่หัวหน้าทีมอนุมัติแล้ว)"
        ),
    )
    parser.add_argument(
        "--root",
        help="รากของคลังข้อมูล (ค่าเริ่มต้น: <repo>/knowledge); ซิงก์ได้เฉพาะ <root>/source/**",
    )
    parser.add_argument(
        "--manifest",
        help="path ของ manifest (ค่าเริ่มต้น: <corpus root>/manifest.json หรือ knowledge/manifest.json)",
    )
    parser.add_argument(
        "--file",
        action="append",
        metavar="PATH",
        help="จำกัดการทำงานไว้ที่ path นี้ซึ่งสัมพันธ์กับคลังข้อมูล เช่น source/<export>.md (ระบุซ้ำได้)",
    )
    parser.add_argument(
        "--store",
        help="ชื่อทรัพยากร File Search store (ค่าเริ่มต้น: $GEMINI_FILE_SEARCH_STORE)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="แสดงเฉพาะแผน ไม่มีการอัปโหลดหรือเขียน manifest"
    )
    parser.add_argument("--force", action="store_true", help="อัปโหลดแหล่งข้อมูลที่ไม่เปลี่ยนแปลงซ้ำด้วย")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="ลบเอกสารระยะไกลเมื่อแหล่งข้อมูลภายในหายไป (ต้องใช้ --yes)",
    )
    parser.add_argument("--yes", action="store_true", help="ยืนยันการลบแบบ prune ที่ทำลายข้อมูล")
    parser.add_argument("--verbose", action="store_true", help="แสดงความคืบหน้ารายไฟล์")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_sync(args)
    except UsageError as exc:
        print(f"ข้อผิดพลาด: {exc}", file=sys.stderr)
        return 2
    except SyncError as exc:
        print(f"ข้อผิดพลาด: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
