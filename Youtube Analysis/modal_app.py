"""
Modal app for the YouTube AI Trend Analysis pipeline.

Run on-demand (local trigger, remote execution):
    modal run modal_app.py
    modal run modal_app.py --days 7

Deploy so it can be triggered remotely at any time:
    modal deploy modal_app.py

Then call it from anywhere:
    modal run modal_app.py  (after deploy, still works)

Secrets setup (one-time):
    Go to modal.com → Secrets → Create secret named "youtube-analysis-secrets"
    Add these keys:
        GMAIL_SENDER         your-email@gmail.com
        GMAIL_APP_PASSWORD   your-16-char-app-password
        REPORT_RECIPIENT     recipient@example.com
"""

import os
import sys

import modal

# ---------------------------------------------------------------------------
# Container image — installs dependencies and bundles project source files
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.abspath(__file__))

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "yt-dlp>=2024.1.0",
        "python-pptx>=1.0.0",
        "matplotlib>=3.8.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
    )
    # Embed tools and config directly into the image at build time
    .add_local_dir(os.path.join(_project_root, "tools"), remote_path="/app/tools")
    .add_local_dir(os.path.join(_project_root, "config"), remote_path="/app/config")
)

app = modal.App("youtube-analysis", image=image)


# ---------------------------------------------------------------------------
# Pipeline function
# ---------------------------------------------------------------------------
@app.function(
    secrets=[modal.Secret.from_dotenv(os.path.join(_project_root, ".env"))],
    timeout=3600,  # up to 1 hour (yt-dlp can be slow across many channels)
)
def run_pipeline(days: int = 14) -> str:
    """
    Full pipeline:
      1. Fetch recent videos via yt-dlp (no API key needed)
      2. Analyze trends (topics, tools, engagement)
      3. Generate a PowerPoint slide deck
      4. Email the report via Gmail SMTP

    Returns the container path of the generated .pptx file.
    """
    sys.path.insert(0, "/app")
    os.makedirs("/app/.tmp", exist_ok=True)

    # Import each tool's main() after adding /app to the path
    from tools.fetch_youtube_data import main as fetch_main  # noqa: E402
    from tools.analyze_trends import main as analyze_main    # noqa: E402
    from tools.create_report import main as report_main      # noqa: E402
    from tools.send_email import main as email_main          # noqa: E402

    print(f"=== Step 1/4: Fetching YouTube data (last {days} days) ===")
    sys.argv = ["fetch_youtube_data.py", "--days", str(days)]
    fetch_main()

    print("\n=== Step 2/4: Analyzing trends ===")
    sys.argv = ["analyze_trends.py"]
    analyze_main()

    print("\n=== Step 3/4: Generating PowerPoint report ===")
    sys.argv = ["create_report.py"]
    report_path = report_main()

    print("\n=== Step 4/4: Sending email ===")
    sys.argv = ["send_email.py"]
    email_main()

    print(f"\nPipeline complete. Report saved to: {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Local entrypoint — `modal run modal_app.py [--days N]`
# ---------------------------------------------------------------------------
@app.local_entrypoint()
def main(days: int = 14):
    print(f"Triggering YouTube trend analysis pipeline on Modal (last {days} days)...")
    result = run_pipeline.remote(days=days)
    print(f"\nDone. Report path in container: {result}")
