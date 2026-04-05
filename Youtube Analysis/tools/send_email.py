"""
Send the AI Trend Report .pptx as a Gmail attachment via SMTP + App Password.
No OAuth required — just a Gmail App Password in .env.

Usage:
    python tools/send_email.py
    python tools/send_email.py .tmp/ai_trend_report_2026-04-05.pptx
    python tools/send_email.py .tmp/ai_trend_report_2026-04-05.pptx --to recipient@example.com
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from glob import glob

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def find_latest_report() -> str | None:
    # Prefer PDF, fall back to pptx
    for ext in ("pdf", "pptx"):
        pattern = os.path.join(PROJECT_ROOT, ".tmp", f"ai_trend_report_*.{ext}")
        files = sorted(glob(pattern), reverse=True)
        if files:
            return files[0]
    return None


def find_latest_trends() -> dict:
    pattern = os.path.join(PROJECT_ROOT, ".tmp", "trends_*.json")
    files = sorted(glob(pattern), reverse=True)
    if not files:
        return {}
    with open(files[0]) as f:
        return json.load(f)


def build_email_html(trends: dict, date_str: str) -> str:
    top_topics = trends.get("summary", {}).get("top_topics", [])
    total_videos = trends.get("summary", {}).get("total_videos", 0)
    channels = trends.get("summary", {}).get("channels_active", 0)
    tools = trends.get("tools_in_spotlight", [])[:3]
    date_range = trends.get("date_range", {})

    topics_html = "".join(
        f'<li style="margin-bottom:6px;"><strong style="color:#6366F1;">{t}</strong></li>'
        for t in top_topics
    )
    tools_html = "".join(
        f'<li style="margin-bottom:6px;">{t["tool"]} — {t["mention_count"]} mentions '
        f'across {t["channels_mentioning"]} channels</li>'
        for t in tools
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0F172A;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0F172A;">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="620" cellpadding="0" cellspacing="0" style="background:#1E293B;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#6366F1;padding:6px 0;"></td></tr>
        <tr>
          <td style="padding:36px 40px 20px 40px;">
            <p style="margin:0;font-size:11px;color:#94A3B8;letter-spacing:2px;text-transform:uppercase;">Weekly Intelligence</p>
            <h1 style="margin:8px 0 4px 0;font-size:28px;color:#FFFFFF;font-weight:700;">AI Trend Report</h1>
            <p style="margin:0;font-size:14px;color:#06B6D4;">{date_range.get('from', '')} → {date_range.get('to', '')}</p>
          </td>
        </tr>
        <tr><td style="padding:0 40px;"><hr style="border:none;border-top:1px solid #334155;margin:0;"></td></tr>
        <tr>
          <td style="padding:24px 40px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center" style="background:#0F172A;border-radius:8px;padding:16px;">
                  <p style="margin:0;font-size:28px;font-weight:700;color:#6366F1;">{total_videos}</p>
                  <p style="margin:4px 0 0 0;font-size:11px;color:#94A3B8;text-transform:uppercase;">Videos Analyzed</p>
                </td>
                <td width="16"></td>
                <td align="center" style="background:#0F172A;border-radius:8px;padding:16px;">
                  <p style="margin:0;font-size:28px;font-weight:700;color:#06B6D4;">{channels}</p>
                  <p style="margin:4px 0 0 0;font-size:11px;color:#94A3B8;text-transform:uppercase;">Channels Tracked</p>
                </td>
                <td width="16"></td>
                <td align="center" style="background:#0F172A;border-radius:8px;padding:16px;">
                  <p style="margin:0;font-size:28px;font-weight:700;color:#F59E0B;">{len(top_topics)}</p>
                  <p style="margin:4px 0 0 0;font-size:11px;color:#94A3B8;text-transform:uppercase;">Trending Topics</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:0 40px 24px 40px;">
            <h2 style="margin:0 0 12px 0;font-size:16px;color:#FFFFFF;">🔥 Top Trending Topics</h2>
            <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.6;">{topics_html}</ul>
          </td>
        </tr>
        {"" if not tools else f"""
        <tr>
          <td style="padding:0 40px 24px 40px;">
            <h2 style="margin:0 0 12px 0;font-size:16px;color:#FFFFFF;">🛠 Tools in Spotlight</h2>
            <ul style="margin:0;padding-left:20px;color:#CBD5E1;font-size:14px;line-height:1.6;">{tools_html}</ul>
          </td>
        </tr>
        """}
        <tr><td style="padding:0 40px;"><hr style="border:none;border-top:1px solid #334155;margin:0;"></td></tr>
        <tr>
          <td style="padding:24px 40px;">
            <p style="margin:0;font-size:14px;color:#94A3B8;line-height:1.6;">
              📎 <strong style="color:#FFFFFF;">Full report attached</strong> — open the PDF for charts, top videos, channel activity, and key takeaways.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 40px;background:#0F172A;border-radius:0 0 12px 12px;">
            <p style="margin:0;font-size:11px;color:#475569;text-align:center;">
              Generated by YouTube AI Trend Automation · {date_str}
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_via_smtp(sender: str, app_password: str, recipient: str,
                  subject: str, html_body: str, attachment_path: str):
    filename = os.path.basename(attachment_path)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    ext = os.path.splitext(filename)[1].lower()
    subtype = "pdf" if ext == ".pdf" else "vnd.openxmlformats-officedocument.presentationml.presentation"
    with open(attachment_path, "rb") as f:
        part = MIMEApplication(f.read(), Name=filename, _subtype=subtype)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.sendmail(sender, recipient, msg.as_bytes())


def main():
    parser = argparse.ArgumentParser(description="Send AI Trend Report via Gmail SMTP")
    parser.add_argument("attachment", nargs="?", default=None)
    parser.add_argument("--to", default=None)
    args = parser.parse_args()

    sender = os.getenv("GMAIL_SENDER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = args.to or os.getenv("REPORT_RECIPIENT")

    if not sender:
        print("ERROR: GMAIL_SENDER not set in .env")
        sys.exit(1)
    if not app_password:
        print("ERROR: GMAIL_APP_PASSWORD not set in .env")
        print()
        print("To generate one (30 seconds):")
        print("1. Go to myaccount.google.com → Security")
        print("2. Under 'How you sign in' → 2-Step Verification (enable if not on)")
        print("3. Search 'App passwords' → create one named 'YouTube Report'")
        print("4. Paste the 16-char password into .env as GMAIL_APP_PASSWORD=...")
        sys.exit(1)
    if not recipient:
        print("ERROR: REPORT_RECIPIENT not set in .env (or use --to flag)")
        sys.exit(1)

    attachment_path = args.attachment
    if not attachment_path:
        attachment_path = find_latest_report()
        if not attachment_path:
            print("ERROR: No ai_trend_report_*.pdf or *.pptx found in .tmp/.")
            sys.exit(1)
        print(f"Using latest report: {attachment_path}")

    trends = find_latest_trends()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_range = trends.get("date_range", {})
    subject = f"AI Trend Report — {date_range.get('from', date_str)} to {date_range.get('to', date_str)}"

    print(f"Sending to {recipient} via SMTP...")
    html_body = build_email_html(trends, date_str)
    send_via_smtp(sender, app_password, recipient, subject, html_body, attachment_path)

    print(f"Email sent.")
    print(f"Subject: {subject}")
    print(f"Attachment: {os.path.basename(attachment_path)}")


if __name__ == "__main__":
    main()
