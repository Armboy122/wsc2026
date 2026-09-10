from __future__ import annotations

import argparse
import asyncio
import json

from .bootstrap import Settings, authenticate, build


async def run(args):
    settings = Settings.from_env()
    service = build(settings)
    # CLI ท้องถิ่นใช้ตัวตนแรกจาก config; API ต้องส่ง bearer token เสมอ
    principal = authenticate(settings, next(iter(settings.tokens), None))
    await service.sessions.initialize()
    session_id = None
    try:
        if args.command == "search":
            result = await service.registry.invoke(settings.plugin_id, {"query": args.question}, principal)
            print(json.dumps({"sources": [{"id": d.source_id, "title": d.title} for d in result.evidence],
                "publication": result.publication, "omitted": result.omitted}, ensure_ascii=False, indent=2))
            return
        print(f"โหมด {settings.provider} — พิมพ์ /new เริ่มใหม่, /quit ออก")
        if settings.provider == "extractive":
            print("โหมดนี้แสดงข้อความที่ค้นพบ ยังไม่ใช่คำตอบจาก AI")
        while True:
            question = args.question if args.question else await asyncio.to_thread(input, "คุณ: ")
            if question.strip() == "/quit":
                break
            if question.strip() == "/new":
                session_id = None
                continue
            answer = await service.ask(principal, question, session_id)
            session_id = answer.session_id
            print(f"\n[{answer.status}] {answer.message}\n")
            for i, citation in enumerate(answer.citations, 1):
                print(f"[{i}] {citation.title} — {citation.source_id}")
            if args.question:
                break
    finally:
        await service.provider.close()


def main():
    parser = argparse.ArgumentParser(description="ทดลอง Knowledge จาก Markdown")
    parser.add_argument("command", choices=["chat", "search"])
    parser.add_argument("question", nargs="?")
    args = parser.parse_args()
    if args.command == "search" and not args.question:
        parser.error("search ต้องระบุคำถาม")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
