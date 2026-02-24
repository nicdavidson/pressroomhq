"""Email Composer — formats content into email drafts with clean HTML templates."""

import html


def compose_email_draft(content: dict, org_settings: dict) -> dict:
    """Take a content item and org settings, return a formatted email draft.

    Args:
        content: dict with headline, body, channel, etc.
        org_settings: dict with company name, domain, etc.

    Returns:
        dict with subject, html_body, text_body, from_name, preview_text
    """
    company_name = org_settings.get("onboard_company_name") or org_settings.get("name", "Company")
    domain = org_settings.get("domain", "")
    headline = content.get("headline", "Update")
    body = content.get("body", "")
    channel = content.get("channel", "release_email")

    subject = headline
    from_name = company_name

    # Build preview text — first ~120 chars of body, stripped of any markup
    preview_text = body[:120].replace("\n", " ").strip()
    if len(body) > 120:
        preview_text += "..."

    # Plain-text fallback
    text_body = f"{headline}\n\n{body}\n\n---\n{company_name}"
    if domain:
        text_body += f" | {domain}"

    # Determine label based on channel
    type_label = "Newsletter" if channel == "newsletter" else "Release"

    # HTML email template — inline CSS for email client compatibility
    html_body = _build_html_template(
        company_name=html.escape(company_name),
        domain=html.escape(domain),
        headline=html.escape(headline),
        body_html=_body_to_html(body),
        preview_text=html.escape(preview_text),
        type_label=type_label,
    )

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
        "from_name": from_name,
        "preview_text": preview_text,
    }


def _body_to_html(body: str) -> str:
    """Convert plain text body to HTML paragraphs."""
    if not body:
        return ""
    paragraphs = body.split("\n\n")
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # Handle single newlines as <br>
        escaped = html.escape(p).replace("\n", "<br>")
        html_parts.append(f'<p style="margin: 0 0 16px 0; line-height: 1.6;">{escaped}</p>')
    return "\n".join(html_parts)


def _build_html_template(
    company_name: str,
    domain: str,
    headline: str,
    body_html: str,
    preview_text: str,
    type_label: str,
) -> str:
    """Build a clean, responsive HTML email template with inline CSS."""
    footer_domain = f' | <a href="https://{domain}" style="color: #999999; text-decoration: underline;">{domain}</a>' if domain else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline}</title>
<!--[if mso]>
<style>table,td {{font-family: Arial, sans-serif;}}</style>
<![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
<!-- Preview text -->
<div style="display: none; max-height: 0; overflow: hidden;">{preview_text}</div>

<!-- Wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4;">
<tr><td align="center" style="padding: 24px 16px;">

<!-- Email container -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 4px;">

<!-- Header -->
<tr>
<td style="padding: 32px 40px 24px 40px; border-bottom: 2px solid #222222;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td style="font-size: 20px; font-weight: 700; color: #222222; letter-spacing: 0.5px;">
      {company_name}
    </td>
    <td align="right" style="font-size: 11px; color: #999999; text-transform: uppercase; letter-spacing: 1px;">
      {type_label}
    </td>
  </tr>
  </table>
</td>
</tr>

<!-- Content -->
<tr>
<td style="padding: 32px 40px;">
  <h1 style="margin: 0 0 24px 0; font-size: 24px; font-weight: 700; color: #222222; line-height: 1.3;">
    {headline}
  </h1>
  {body_html}
</td>
</tr>

<!-- Footer -->
<tr>
<td style="padding: 24px 40px; border-top: 1px solid #e5e5e5;">
  <p style="margin: 0; font-size: 12px; color: #999999; line-height: 1.5;">
    {company_name}{footer_domain}
  </p>
</td>
</tr>

</table>
<!-- /Email container -->

</td></tr>
</table>
<!-- /Wrapper -->

</body>
</html>"""
