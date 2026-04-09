# content_pipeline

Local automation and landed assets for Charles's content pipeline.

## Email landing workflow

This repo includes a Gmail attachment fetcher that looks for pipeline-style emails such as:

- `voice_to_video_[1]`

Matching MP3 attachments are saved into:

```text
voice_to_video/<pipeline>/YYYYMMDD/incoming/<gmail_message_id>/
```

Example:

```text
voice_to_video/1/20260409/incoming/19d70f665582db0a/
```

Each landed email also gets a `metadata.json` file with message details and saved file info.

## Script

```bash
python3 scripts/email_pipeline_fetch.py
```

Common options:

```bash
python3 scripts/email_pipeline_fetch.py --message-id <gmail_message_id>
python3 scripts/email_pipeline_fetch.py --dry-run
```

Default behavior:
- account: `content.pipeline.1@gmail.com`
- query: unread `voice_to_video_[1]` emails with MP3 attachments
- after success: add Gmail label `processed/content_pipeline` and remove `UNREAD`

## Notes

- MP4 files are git-ignored.
- MP3s, metadata, scripts, and docs are committed by default.
