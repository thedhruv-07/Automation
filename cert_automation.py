"""
Certification Renewal Automation Engine
========================================
Reads client certification data from Excel, identifies expiring certs, and
sends Email notifications with professional banners. Real WhatsApp sending
is handled separately by whatsapp_renewal_alerts.py / the dashboard app,
using Meta's WhatsApp Cloud API — not this script.

MODES:
  - test_mode=True  → Simulates everything, saves preview files, no real messages sent
  - test_mode=False → Actually sends via configured providers

SETUP (for real sending):
  Email: Set EMAIL_SENDER (verified in Brevo) and BREVO_API_KEY in .env
"""

import sys
import base64
import pandas as pd
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, which crashes on emoji output

# ── Local modules ────────────────────────────────────────────────────────────
from banner_generator import generate_banner
from email_template import build_email_html

load_dotenv(Path(__file__).parent / ".env")

LOGO_PATH = Path(__file__).parent / "dashboard-app" / "frontend" / "public" / "company-logo.png"
LOGO_CID = "company-logo.png"

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — org details below; credentials come from .env (see .env.example)
# ═════════════════════════════════════════════════════════════════════════════
CONFIG = {
    # Reminder thresholds (days before expiry)
    "alert_days": [60],   # 0 = expiry day; negative = already expired (still alert)
    "include_expired": True,         # Also send alerts for recently expired certs

    # Your organization
    "org_name": "Absolute Veritas",
    "org_website": "",
    "org_contact": "",
    "org_email": "cs@absoluteveritas.com",

    # Email config (sent via Brevo's transactional email API) — from .env, never hardcode real credentials here
    "EMAIL_SENDER": os.environ.get("EMAIL_SENDER", ""),   # must be a verified sender in your Brevo account
    "BREVO_API_KEY": os.environ.get("BREVO_API_KEY", ""),
}

ALERT_THRESHOLDS = CONFIG["alert_days"]


# ═════════════════════════════════════════════════════════════════════════════
# EXCEL READER
# ═════════════════════════════════════════════════════════════════════════════
def read_certifications(excel_path: str) -> list[dict]:
    df = pd.read_excel(excel_path)
    df.columns = [c.strip() for c in df.columns]

    # Map to standard keys (flexible column name matching)
    col_map = {
        "Client ID": "client_id",
        "Full Name": "name",
        "Company": "company",
        "Email": "email",
        "Phone (WhatsApp)": "phone",
        "Certification Name": "cert_name",
        "Certification ID": "cert_id",
        "Issue Date": "issue_date",
        "Expiry Date": "expiry_date",
        "Renewal Link": "renewal_link",
        "Status": "status"
    }

    records = []
    for _, row in df.iterrows():
        rec = {}
        for col, key in col_map.items():
            if col in df.columns:
                rec[key] = row[col]
        records.append(rec)

    return records


# ═════════════════════════════════════════════════════════════════════════════
# EXPIRY CHECKER
# ═════════════════════════════════════════════════════════════════════════════
def check_expiry(records: list[dict], today=None) -> list[dict]:
    if today is None:
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    to_notify = []
    for rec in records:
        try:
            exp_raw = rec.get("expiry_date", "")
            if isinstance(exp_raw, datetime):
                exp = exp_raw
            elif isinstance(exp_raw, str):
                for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        exp = datetime.strptime(exp_raw.strip(), fmt)
                        break
                    except ValueError:
                        continue
                else:
                    print(f"  ⚠ Could not parse date for {rec.get('name')}: {exp_raw}")
                    continue
            else:
                exp = pd.Timestamp(exp_raw).to_pydatetime()

            days_left = (exp - today).days

            # Check if falls in any alert bucket
            should_alert = False
            if days_left < 0 and CONFIG["include_expired"] and days_left >= -30:
                should_alert = True   # Alert for up to 30 days past expiry
            else:
                for threshold in ALERT_THRESHOLDS:
                    if threshold > 0 and days_left <= threshold:
                        should_alert = True
                        break
                    elif threshold == 0 and days_left == 0:
                        should_alert = True
                        break

            if should_alert:
                rec["days_left"] = days_left
                rec["expiry_formatted"] = exp.strftime("%d %B %Y")
                to_notify.append(rec)

        except Exception as e:
            print(f"  ⚠ Error processing {rec.get('name', 'Unknown')}: {e}")

    return to_notify


# ═════════════════════════════════════════════════════════════════════════════
# WHATSAPP MESSAGE TEXT
# ═════════════════════════════════════════════════════════════════════════════
def build_whatsapp_text(rec: dict) -> str:
    days_left = rec["days_left"]
    if days_left < 0:
        urgency_line = f"⚠️ *EXPIRED* — {abs(days_left)} days ago!"
    elif days_left == 0:
        urgency_line = "🔴 *EXPIRES TODAY!*"
    elif days_left <= 7:
        urgency_line = f"🔴 *Expires in {days_left} day{'s' if days_left != 1 else ''}* — CRITICAL"
    elif days_left <= 30:
        urgency_line = f"🟠 *Expires in {days_left} days* — Act now"
    else:
        urgency_line = f"🟡 *Expires in {days_left} days* — Plan ahead"

    return f"""🏅 *{CONFIG['org_name']}*
━━━━━━━━━━━━━━━━━━━━━━

📢 *CERTIFICATION RENEWAL ALERT*

Dear *{rec['name']}*,
(*{rec['company']}*)

{urgency_line}

📋 *Certification Details:*
• Name: {rec['cert_name']}
• ID: `{rec['cert_id']}`
• Expiry: *{rec['expiry_formatted']}*

━━━━━━━━━━━━━━━━━━━━━━
🔄 *Renew Online:*
{rec['renewal_link']}

📞 *Call us for assistance:*
{CONFIG['org_contact']}

📧 {CONFIG['org_email']}
🌐 {CONFIG['org_website']}
━━━━━━━━━━━━━━━━━━━━━━
_Avoid compliance issues — renew on time!_"""


# ═════════════════════════════════════════════════════════════════════════════
# SENDERS (REAL)
# ═════════════════════════════════════════════════════════════════════════════
def send_email_real(rec: dict, html_body: str):
    """Sends via Brevo's transactional email API. The banner PNG is generated
    for WhatsApp and local previews but intentionally not attached here — only
    the logo goes along, inline via its cid: reference in html_body."""
    attachments = []
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("ascii")
        attachments.append({"name": LOGO_CID, "content": logo_b64})

    payload = {
        "sender": {"name": CONFIG["org_name"], "email": CONFIG["EMAIL_SENDER"]},
        "to": [{"email": rec["email"], "name": rec["name"]}],
        "subject": f"[Action Required] Renew {rec['cert_name']} — {rec['company']}",
        "htmlContent": html_body,
        "attachment": attachments,
    }
    headers = {
        "api-key": CONFIG["BREVO_API_KEY"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=15
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Brevo send failed ({response.status_code}): {response.text}")

    print(f"  ✅ Email sent to {rec['email']} via Brevo")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═════════════════════════════════════════════════════════════════════════════
def run_automation(excel_path: str, test_mode: bool = True, output_dir: str = "output"):
    print("\n" + "="*60)
    print("  CERTIFICATION RENEWAL AUTOMATION ENGINE")
    print("  Mode:", "🧪 TEST (no real messages)" if test_mode else "🚀 LIVE (sending real messages)")
    print("="*60)

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(f"{output_dir}/banners", exist_ok=True)
    os.makedirs(f"{output_dir}/emails", exist_ok=True)

    # 1. Read Excel
    print("\n📂 Reading Excel file...")
    records = read_certifications(excel_path)
    print(f"   Found {len(records)} clients in database")

    # 2. Check expiry
    print("\n📅 Checking expiry dates...")
    to_notify = check_expiry(records)
    print(f"   {len(to_notify)} clients require notification")

    if not to_notify:
        print("\n✅ No certifications require alerts at this time.")
        return

    # 3. Process each
    print("\n📨 Processing notifications...\n")
    summary = []

    for rec in to_notify:
        days_left = rec["days_left"]
        status = (
            "EXPIRED" if days_left < 0
            else "EXPIRES TODAY" if days_left == 0
            else f"Expires in {days_left} days"
        )
        print(f"  👤 {rec['name']} | {rec['company']}")
        print(f"     {rec['cert_name']} — {status}")

        # Generate banner
        banner_path = f"{output_dir}/banners/{rec['client_id']}_banner.png"
        banner_data = {
            "name": rec["name"],
            "company": rec["company"],
            "cert_name": rec["cert_name"],
            "cert_id": rec["cert_id"],
            "expiry_date": rec["expiry_formatted"],
            "days_left": days_left,
            "renewal_link": str(rec.get("renewal_link", CONFIG["org_website"])),
            "contact_number": CONFIG["org_contact"],
        }
        generate_banner(banner_data, banner_path)

        # Generate email HTML
        html = build_email_html(
            rec,
            org_name=CONFIG["org_name"],
            org_website=CONFIG["org_website"],
            org_contact=CONFIG["org_contact"],
            org_email=CONFIG["org_email"],
            logo_src=f"cid:{LOGO_CID}" if LOGO_PATH.exists() else "",
        )
        email_path = f"{output_dir}/emails/{rec['client_id']}_email.html"
        with open(email_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Generate WhatsApp text
        wa_text = build_whatsapp_text(rec)
        wa_path = f"{output_dir}/{rec['client_id']}_whatsapp_text.txt"
        with open(wa_path, "w", encoding="utf-8") as f:
            f.write(wa_text)

        if test_mode:
            print(f"     💌 [TEST] Email preview → {email_path}")
            print(f"     📱 [TEST] WhatsApp text → {wa_path}")
            print(f"     🖼  [TEST] Banner → {banner_path}")
        else:
            # Real sending (email only — WhatsApp is sent separately via
            # whatsapp_renewal_alerts.py / the dashboard app's Meta Cloud API integration)
            try:
                send_email_real(rec, html)
            except Exception as e:
                print(f"     ❌ Email failed: {e}")

        summary.append({
            "client": rec["name"],
            "company": rec["company"],
            "cert": rec["cert_name"],
            "expiry": rec["expiry_formatted"],
            "days_left": days_left,
            "email": rec["email"],
            "phone": rec["phone"],
            "banner": banner_path,
            "email_preview": email_path,
        })
        print()

    # 4. Summary report
    report_path = f"{output_dir}/automation_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "run_date": datetime.now().isoformat(),
            "mode": "test" if test_mode else "live",
            "total_clients_in_db": len(records),
            "clients_notified": len(to_notify),
            "details": summary
        }, f, indent=2)

    print("="*60)
    print(f"  ✅ Done! {len(to_notify)} notifications processed.")
    print(f"  📊 Report saved: {report_path}")
    print(f"  📁 All outputs: {output_dir}/")
    print("="*60 + "\n")

    return summary


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_automation(
        excel_path="clients_certifications.xlsx",
        test_mode=True  # Change to False (after setting real credentials in .env) to send real messages
    )
