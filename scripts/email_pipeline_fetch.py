#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")
DEFAULT_ACCOUNT = "content.pipeline.1@gmail.com"
DEFAULT_BASE = Path("/Users/macmini-4/.openclaw/workspace/content_pipeline")
DEFAULT_LABEL = "processed/content_pipeline"
SUBJECT_RE = re.compile(r"^(?P<task>[a-z0-9_]+)_\[(?P<pipeline>\d+)\]$", re.IGNORECASE)


def run_cmd(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}")
    return result.stdout


def gog_json(args):
    out = run_cmd(args + ["--json", "--results-only", "--no-input"])
    return json.loads(out)


def ensure_label(account: str, label_name: str) -> None:
    labels = gog_json(["gog", "gmail", "labels", "list", "--account", account])
    names = {item.get("name") for item in labels if isinstance(item, dict)}
    if label_name not in names:
        run_cmd(["gog", "gmail", "labels", "create", label_name, "--account", account, "--no-input"])


def search_messages(account: str, query: str, max_results: int):
    rows = gog_json(["gog", "gmail", "search", query, "--account", account, "--max", str(max_results)])
    if isinstance(rows, dict):
        return [rows]
    return rows


def get_metadata(account: str, message_id: str):
    return gog_json([
        "gog", "gmail", "get", message_id,
        "--account", account,
        "--format", "metadata",
        "--headers", "Subject,From,Date",
    ])


def get_attachments(account: str, message_id: str):
    rows = gog_json(["gog", "gmail", "get", message_id, "--account", account])
    return rows if isinstance(rows, list) else []


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return cleaned or "attachment.mp3"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 2
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def parse_subject(subject: str):
    m = SUBJECT_RE.match(subject.strip())
    if not m:
        return None, None
    return m.group("task"), m.group("pipeline")


def landing_dir(base: Path, task: str, pipeline: str, dt: datetime, message_id: str) -> Path:
    day = dt.astimezone(SYDNEY).strftime("%Y%m%d")
    return base / task / pipeline / day / "incoming" / message_id


def download_attachment(account: str, message_id: str, attachment_id: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        "gog", "gmail", "attachment", message_id, attachment_id,
        "--account", account,
        "--out", str(out_path),
        "--no-input",
    ])


def mark_processed(account: str, message_id: str, label_name: str):
    run_cmd([
        "gog", "gmail", "batch", "modify", message_id,
        "--account", account,
        "--add", label_name,
        "--remove", "UNREAD",
        "--no-input",
    ])


def process_message(account: str, base: Path, label_name: str, message_id: str, dry_run: bool = False):
    meta = get_metadata(account, message_id)
    headers = meta.get("headers", {})
    message = meta.get("message", {})
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date_str = headers.get("date", "")
    task, pipeline = parse_subject(subject)
    if not task or not pipeline:
        return {"messageId": message_id, "status": "skipped", "reason": f"subject_not_supported:{subject}"}

    dt = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=ZoneInfo("UTC"))
    target_dir = landing_dir(base, task, pipeline, dt, message_id)
    attachments = get_attachments(account, message_id)
    mp3s = []
    for item in attachments:
        filename = item.get("filename") or "attachment.mp3"
        mime = item.get("mimeType", "")
        if not filename.lower().endswith(".mp3") and mime not in {"audio/mpeg", "audio/mp3", "application/octet-stream"}:
            continue
        mp3s.append(item)

    if not mp3s:
        return {"messageId": message_id, "status": "skipped", "reason": "no_mp3_attachments"}

    saved = []
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
    for item in mp3s:
        filename = safe_name(item.get("filename") or "attachment.mp3")
        out_path = unique_path(target_dir / filename)
        if not dry_run:
            download_attachment(account, message_id, item["attachmentId"], out_path)
        saved.append({
            "filename": out_path.name,
            "path": str(out_path),
            "size": item.get("size"),
            "attachmentId": item.get("attachmentId"),
        })

    metadata = {
        "messageId": message_id,
        "threadId": message.get("threadId"),
        "historyId": message.get("historyId"),
        "subject": subject,
        "from": sender,
        "date": date_str,
        "internalDate": message.get("internalDate"),
        "labels": message.get("labelIds", []),
        "savedAt": datetime.now(tz=SYDNEY).isoformat(),
        "savedFiles": saved,
    }
    if not dry_run:
        (target_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        mark_processed(account, message_id, label_name)

    return {
        "messageId": message_id,
        "status": "processed",
        "subject": subject,
        "from": sender,
        "targetDir": str(target_dir),
        "files": saved,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch pipeline email MP3 attachments into structured folders.")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE))
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--query", default='is:unread has:attachment subject:"voice_to_video_[1]" filename:mp3 -label:"processed/content_pipeline"')
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--message-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = Path(args.base_dir)
    if not args.dry_run:
        ensure_label(args.account, args.label)

    ids = [args.message_id] if args.message_id else [row["ID"] for row in search_messages(args.account, args.query, args.max_results)]
    results = []
    for message_id in ids:
        try:
            results.append(process_message(args.account, base, args.label, message_id, dry_run=args.dry_run))
        except Exception as e:
            results.append({"messageId": message_id, "status": "error", "error": str(e)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r.get("status") == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
