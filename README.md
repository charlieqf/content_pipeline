# content_pipeline

Local automation for Charles's content pipeline.

## Email landing workflow

This repo includes a Gmail attachment fetcher for pipeline-style emails such as:

- `voice_to_video_[1]`
- future rules like `voice_to_video_[2]`, `image_to_video_[1]`, etc.

Matching attachments are saved into the runtime landing directory, not the repo working tree:

```text
/Users/macmini-4/.openclaw/runtime/content_pipeline/landing/<task>/<pipeline>/YYYYMMDD/incoming/<gmail_message_id>/
```

Example:

```text
/Users/macmini-4/.openclaw/runtime/content_pipeline/landing/voice_to_video/1/20260409/incoming/19d70f665582db0a/
```

Each landed email directory contains only raw input files plus `metadata.json`.

## Config

Rules live in:

```text
config/pipelines.json
```

Example:

```json
{
  "account": "content.pipeline.1@gmail.com",
  "processedLabel": "processed/content_pipeline",
  "rules": [
    {
      "subject": "voice_to_video_[1]",
      "task": "voice_to_video",
      "pipeline": "1",
      "attachmentExtensions": [".mp3"],
      "filenameQuery": "filename:mp3"
    }
  ]
}
```

Add more rules by appending to `rules`.

## Environment variables

These override defaults when present:

- `CONTENT_PIPELINE_BASE`
- `CONTENT_PIPELINE_CONFIG`
- `CONTENT_PIPELINE_ACCOUNT`

Defaults:

- code repo: `/Users/macmini-4/.openclaw/repos/content_pipeline`
- runtime landing: `/Users/macmini-4/.openclaw/runtime/content_pipeline/landing`
- runtime logs: `/Users/macmini-4/.openclaw/runtime/content_pipeline/logs`

## Scripts

Run one pass manually:

```bash
python3 scripts/email_pipeline_fetch.py
```

Process one known message id:

```bash
python3 scripts/email_pipeline_fetch.py --message-id <gmail_message_id>
```

Dry run:

```bash
python3 scripts/email_pipeline_fetch.py --dry-run
```

Wrapper for scheduled execution:

```bash
scripts/run_email_pipeline.sh
```

Default behavior:
- account comes from `config/pipelines.json`
- processed messages get Gmail label `processed/content_pipeline`
- processed messages are also marked read

## launchd auto-run on macOS

A sample launchd job is included:

```text
launchd/com.charles.content-pipeline.email.plist
```

Install it:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.charles.content-pipeline.email.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.charles.content-pipeline.email.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.charles.content-pipeline.email.plist
```

Check status:

```bash
launchctl list | grep content-pipeline
```

Logs:

```text
/Users/macmini-4/.openclaw/runtime/content_pipeline/logs/email_pipeline.log
/Users/macmini-4/.openclaw/runtime/content_pipeline/logs/launchd.stdout.log
/Users/macmini-4/.openclaw/runtime/content_pipeline/logs/launchd.stderr.log
```

## Boundaries

- This project only handles `email -> raw attachments + metadata.json`.
- It does not create derived outputs.
- It does not touch downstream directories.
- Runtime landing data is intentionally kept out of the git repo.

## Notes

- MP4 files are git-ignored.
- Scripts, config, and docs are committed by default.
