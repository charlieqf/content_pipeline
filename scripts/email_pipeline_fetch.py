#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")
DEFAULT_BASE = Path("/Users/macmini-4/.openclaw/workspace/content_pipeline")
DEFAULT_CONFIG = DEFAULT_BASE / "config" / "pipelines.json"
SUBJECT_RE = re.compile(r"^(?P<task>[a-z0-9_]+)_\[(?P<pipeline>\d+)\]$", re.IGNORECASE)
GOG_BIN = shutil.which("gog") or "/opt/homebrew/bin/gog"


def run_cmd(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}")
    return result.stdout


def gog_json(args):
    out = run_cmd(args + ["--json", "--results-only", "--no-input"])
    return json.loads(out)


def load_config(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_label(account: str, label_name: str) -> None:
    labels = gog_json([GOG_BIN, "gmail", "labels", "list", "--account", account])
    names = {item.get("name") for item in labels if isinstance(item, dict)}
    if label_name not in names:
        run_cmd([GOG_BIN, "gmail", "labels", "create", label_name, "--account", account, "--no-input"])


def search_messages(account: str, query: str, max_results: int):
    rows = gog_json([GOG_BIN, "gmail", "search", query, "--account", account, "--max", str(max_results)])
    if isinstance(rows, dict):
        return [rows]
    return rows


def get_metadata(account: str, message_id: str):
    return gog_json([
        GOG_BIN, "gmail", "get", message_id,
        "--account", account,
        "--format", "metadata",
        "--headers", "Subject,From,Date",
    ])


def get_attachments(account: str, message_id: str):
    rows = gog_json([GOG_BIN, "gmail", "get", message_id, "--account", account])
    return rows if isinstance(rows, list) else []


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return cleaned or "attachment"


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


def build_rule_index(config: dict):
    rules = {}
    for rule in config.get("rules", []):
        subject = rule.get("subject")
        task = str(rule.get("task") or "")
        pipeline = str(rule.get("pipeline") or "")
        if not subject and task and pipeline:
            subject = f"{task}_[{pipeline}]"
            rule["subject"] = subject
        if subject:
            rules[subject] = rule
    return rules


def build_query(rule: dict, processed_label: str):
    subject = rule["subject"]
    filename_query = rule.get("filenameQuery", "")
    parts = [
        "is:unread",
        "has:attachment",
        f'subject:"{subject}"',
        f'-label:"{processed_label}"',
    ]
    if filename_query:
        parts.append(filename_query)
    return " ".join(parts)


def landing_dir(base: Path, task: str, pipeline: str, dt: datetime, message_id: str) -> Path:
    day = dt.astimezone(SYDNEY).strftime("%Y%m%d")
    return base / task / pipeline / day / "incoming" / message_id


def download_attachment(account: str, message_id: str, attachment_id: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        GOG_BIN, "gmail", "attachment", message_id, attachment_id,
        "--account", account,
        "--out", str(out_path),
        "--no-input",
    ])


def mark_processed(account: str, message_id: str, label_name: str):
    run_cmd([
        GOG_BIN, "gmail", "batch", "modify", message_id,
        "--account", account,
        "--add", label_name,
        "--remove", "UNREAD",
        "--no-input",
    ])


def attachment_matches(item: dict, rule: dict):
    filename = (item.get("filename") or "").lower()
    mime = (item.get("mimeType") or "").lower()
    exts = [e.lower() for e in rule.get("attachmentExtensions", [".mp3"])]
    if any(filename.endswith(ext) for ext in exts):
        return True
    mime_allow = set(m.lower() for m in rule.get("mimeTypes", ["audio/mpeg", "audio/mp3", "application/octet-stream"]))
    return mime in mime_allow and bool(filename)


def process_message(account: str, base: Path, label_name: str, rules_by_subject: dict, message_id: str, dry_run: bool = False):
    meta = get_metadata(account, message_id)
    headers = meta.get("headers", {})
    message = meta.get("message", {})
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date_str = headers.get("date", "")

    rule = rules_by_subject.get(subject)
    if not rule:
        task, pipeline = parse_subject(subject)
        if not task or not pipeline:
            return {"messageId": message_id, "status": "skipped", "reason": f"subject_not_supported:{subject}"}
        rule = {
            "subject": subject,
            "task": task,
            "pipeline": pipeline,
            "attachmentExtensions": [".mp3"],
            "mimeTypes": ["audio/mpeg", "audio/mp3", "application/octet-stream"],
        }

    task = str(rule["task"])
    pipeline = str(rule["pipeline"])
    dt = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=ZoneInfo("UTC"))
    target_dir = landing_dir(base, task, pipeline, dt, message_id)
    attachments = get_attachments(account, message_id)
    matched = [item for item in attachments if attachment_matches(item, rule)]

    if not matched:
        return {"messageId": message_id, "status": "skipped", "reason": "no_matching_attachments"}

    saved = []
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
    for item in matched:
        original = item.get("filename") or "attachment"
        out_path = unique_path(target_dir / safe_name(original))
        if not dry_run:
            download_attachment(account, message_id, item["attachmentId"], out_path)
        saved.append({
            "filename": out_path.name,
            "path": str(out_path),
            "size": item.get("size"),
            "mimeType": item.get("mimeType"),
            "attachmentId": item.get("attachmentId"),
        })

    metadata = {
        "messageId": message_id,
        "threadId": message.get("threadId"),
        "historyId": message.get("historyId"),
        "subject": subject,
        "task": task,
        "pipeline": pipeline,
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
        "task": task,
        "pipeline": pipeline,
        "from": sender,
        "targetDir": str(target_dir),
        "files": saved,
    }


def collect_message_ids(account: str, rules: list, processed_label: str, max_results: int):
    ids = []
    seen = set()
    for rule in rules:
        query = build_query(rule, processed_label)
        for row in search_messages(account, query, max_results):
            message_id = row.get("ID")
            if message_id and message_id not in seen:
                seen.add(message_id)
                ids.append(message_id)
    return ids


def main():
    parser = argparse.ArgumentParser(description="Fetch pipeline email attachments into structured folders.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--account")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE))
    parser.add_argument("--label")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--message-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    account = args.account or config["account"]
    label = args.label or config.get("processedLabel", "processed/content_pipeline")
    base = Path(args.base_dir)
    rules_by_subject = build_rule_index(config)
    rules = list(rules_by_subject.values())

    if not args.dry_run:
        ensure_label(account, label)

    if args.message_id:
        ids = [args.message_id]
    else:
        ids = collect_message_ids(account, rules, label, args.max_results)

    results = []
    for message_id in ids:
        try:
            results.append(process_message(account, base, label, rules_by_subject, message_id, dry_run=args.dry_run))
        except Exception as e:
            results.append({"messageId": message_id, "status": "error", "error": str(e)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r.get("status") == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
