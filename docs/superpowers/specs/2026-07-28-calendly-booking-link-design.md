# "Book an Appointment" Calendly Link

## Problem

Clients reading a renewal alert or the Transition Facilitation notice have
no direct way to schedule a call with Absolute Veritas from the message
itself — the only actions today are "Renew Now" (renewal emails) or "Read
the Full Breakdown" (the notice email), both taking the reader away without
an easy path to actually talk to someone.

## Scope

Add a secondary "Book an Appointment" call-to-action, linking to
`https://calendly.com/cs-absoluteveritas/30min`, to both email templates
(the renewal/expiry email and the Transition Facilitation notice email).
WhatsApp needs no code change — the same link becomes a static URL button
configured directly on each WhatsApp template in Meta Business Manager, a
manual step outside this codebase (covered in the "WhatsApp" section
below, not implemented here).

## 1. Shared constant — `email_template.py`

```python
CALENDLY_URL = "https://calendly.com/cs-absoluteveritas/30min"
```

Lives here rather than in a config/env var, matching how `DEFAULT_INTRO_TEXT`
already lives here as email_template.py's canonical shared constant — a
plain Python constant, not deployment-specific or secret, so there's no
reason for it to be an env var (unlike WhatsApp template names, which
genuinely vary by scheme/deployment). `notice_transition_facilitation_2026.py`
imports it from here instead of duplicating the URL, the same DRY pattern
already used for `DEFAULT_INTRO_TEXT`.

## 2. Renewal/expiry email — `email_template.py`'s `build_email_html`

Below the existing "Renew Now" button (the primary CTA, styled solid blue,
unchanged), add a second button: "Book an Appointment" → `CALENDLY_URL`,
`target="_blank" rel="noopener noreferrer"`, styled as a **secondary**
button (outlined, not solid) so it doesn't visually compete with "Renew
Now" — renewing stays the primary action, booking a call is a secondary
option underneath it. Applies to every renewal/expiry email sent, across
every scheme (ISI/CRS/FMCS), since this button lives in the shared
template function every scheme's content flows through.

## 3. Notice email — `notice_transition_facilitation_2026.py`'s `build_email_html`

Same pattern, below the existing "Read the Full Breakdown" button: a
secondary "Book an Appointment" button → the same shared `CALENDLY_URL`,
same `target="_blank" rel="noopener noreferrer"` treatment (this module
already learned that lesson from the X-Frame-Options bug on its first
button).

## 4. WhatsApp — no code change, template-configuration step only

Because the Calendly link is identical for every client (not personalized
per recipient), it qualifies as a **static URL button** in Meta's WhatsApp
template format — baked into the template definition itself when created
or edited in Meta Business Manager, requiring no button-related data in the
send payload (`build_payload`/`build_whatsapp_payload` need zero changes;
that's only necessary for *dynamic* URL buttons with a templated
`{{1}}`-style suffix). This applies to every WhatsApp template still
pending approval — the per-scheme renewal templates and the transition
notice's own template — as a step to take when creating/editing them in
Meta Business Manager, not something this codebase can automate.

## Testing

- `test_email_template.py`: `build_email_html` includes a "Book an
  Appointment" link pointing to `CALENDLY_URL`, with `target="_blank"` and
  `rel="noopener noreferrer"`, alongside the existing "Renew Now" button
  (both present, not one replacing the other).
- `test_notice_transition_facilitation_2026.py`: same assertions for the
  notice's `build_email_html`, confirming the "Read the Full Breakdown"
  button is still present *and* the new Calendly button is added, not
  substituted.
