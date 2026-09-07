"""Send the card. SMTP (Gmail app password works) or Resend. Chosen by env vars, nothing else."""
import os, smtplib, json, urllib.request
from email.message import EmailMessage
from email.utils import formataddr

def html_card(card):
    rows = "".join(f'<p style="margin:0 0 10px"><b>{l.split(":",1)[0]}:</b>{l.split(":",1)[1]}</p>' for l in card["lines"])
    return (f'<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:520px;margin:0 auto;padding:20px;'
            f'color:#1a1a1a;line-height:1.5;background:#faf9f6"><h2 style="margin:0 0 14px;font-weight:600">{card["subject"]}</h2>'
            f'{rows}<p style="font-size:11px;color:#777;margin:18px 0 0">{card["footer"]}</p></div>')

def send(card, to, prefix=""):
    subject = prefix + card["subject"]
    text = "\n".join(card["lines"]) + "\n\n" + card["footer"]
    html = html_card(card)
    if os.environ.get("RESEND_API_KEY"):
        body = json.dumps({"from": os.environ.get("MAIL_FROM", "Klädkollen <onboarding@resend.dev>"), "to": to, "subject": subject, "text": text, "html": html}).encode()
        req = urllib.request.Request("https://api.resend.com/emails", data=body, method="POST",
                                     headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"], "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    host, user, pw = os.environ.get("SMTP_HOST", "smtp.gmail.com"), os.environ["SMTP_USER"], os.environ["SMTP_PASS"]
    msg = EmailMessage()
    msg["From"] = formataddr(("Klädkollen", user)); msg["To"] = ", ".join(to); msg["Subject"] = subject
    msg.set_content(text); msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT", 465))) as s:
        s.login(user, pw); s.send_message(msg)
    return {"sent": True}
