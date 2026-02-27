# NexoBI — Integration Scenarios & Architecture
### Dentrix · Google Ads · Meta Ads · HubSpot · CallRail · GA4 · and more

> **Purpose:** Full reference for all NexoBI integration scenarios — data flows, patient journey examples, platform-by-platform architecture, and ETL pipeline design. Use this for sales demos, technical discovery, and product roadmap planning.

---

## Table of Contents

1. [Why Integrations Matter](#1-why-integrations-matter)
2. [Core Attribution Architecture](#2-core-attribution-architecture)
3. [Patient Journey Scenarios](#3-patient-journey-scenarios)
   - 3.1 Simple — Maria Rodriguez (Google Ads → Dentrix)
   - 3.2 Multi-Patient — Campaign Comparison
   - 3.3 Complex — David Chen (HubSpot Nurture + LTV)
4. [Integration Ecosystem Map](#4-integration-ecosystem-map)
5. [Platform-by-Platform Reference](#5-platform-by-platform-reference)
   - 5.1 Dentrix (G-Series & Ascend)
   - 5.2 Google Ads + CallRail
   - 5.3 Meta Ads
   - 5.4 GA4
   - 5.5 HubSpot CRM
   - 5.6 Weave / NexHealth
   - 5.7 Podium / Birdeye (Reviews)
   - 5.8 LinkedIn Ads
6. [Data Pipeline Architecture](#6-data-pipeline-architecture)
7. [Databricks Schema & Table](#7-databricks-schema--table)
8. [NexoBI Data Schema Mapping](#8-nexobi-data-schema-mapping)
9. [Sales Talking Points](#9-sales-talking-points)
10. [Roadmap & Open Questions](#10-roadmap--open-questions)
11. [Case Study — EHR + Paid Marketing with HIPAA Guardrails](#11-case-study--ehr--paid-marketing-with-hipaa-guardrails)
12. [Case Study — CRM + SEO / Organic Search](#12-case-study--crm--seo--organic-search)

---

## 1. Why Integrations Matter

Every dental/healthcare practice operates across **disconnected silos**:

| Platform | What it knows | What it doesn't know |
|---|---|---|
| **Google Ads** | Clicks, impressions, spend, conversions (form fills) | Whether the patient booked, attended, or paid |
| **Meta Ads** | Reach, link clicks, lead form submissions | Clinical outcomes, revenue |
| **GA4** | Sessions, page views, form events, traffic source | Appointment data, treatment revenue |
| **HubSpot** | Lead contact info, email opens, nurture stage | Dentrix appointments, clinical production |
| **Dentrix** | Booked, attended, treatment plans, production $ | Which ad, campaign, or keyword drove the patient |
| **CallRail** | Which ad drove a phone call, call recordings | Whether that caller became a patient |

**NexoBI's job:** Stitch all of these together into a single Delta table so the AI Agent and dashboard can answer questions like:
- *"Which campaign produced the highest patient LTV?"*
- *"What's the revenue impact of our no-shows by traffic source?"*
- *"Which keyword drove the most attended appointments last 90 days?"*

---

## 2. Core Attribution Architecture

### The Attribution Thread

The critical challenge: **connect an ad click to a paid treatment.**

```
┌─────────────────────────────────────────────────────────────┐
│                     PATIENT JOURNEY                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Google Ad Click                                            │
│      │  gclid=ABC123 auto-tagged in URL                     │
│      ↓                                                      │
│  Landing Page                                               │
│      │  gclid captured in cookie / JS                       │
│      ↓                                                      │
│  Contact Form (or Phone Call via CallRail)                  │
│      │  gclid stored as hidden field → submitted with lead  │
│      ↓                                                      │
│  Lead Created (CRM / HubSpot / spreadsheet)                 │
│      │  source + campaign + keyword tagged                   │
│      ↓                                                      │
│  Front Desk Books Appointment in Dentrix                    │
│      │  Referral Source field = "Google Ads – Implants"     │
│      ↓                                                      │
│  Patient Attends                                            │
│      │  Appointment status → "Complete" in Dentrix          │
│      ↓                                                      │
│  Treatment Plan Accepted → Payment                          │
│      │  Production $ recorded in Dentrix                    │
│      ↓                                                      │
│  Nightly Dentrix Export (CSV or ODBC)                       │
│      │  Referral source, production, appt status            │
│      ↓                                                      │
│  Python ETL Script                                          │
│      │  Map → NexoBI schema → MERGE INTO Delta table        │
│      ↓                                                      │
│  Databricks Unity Catalog                                   │
│      │  workspace.silver.DemoData-marketing-crm             │
│      ↓                                                      │
│  NexoBI Dashboard + AI Agent                                │
│      │  Full journey visible: click → revenue → LTV         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Two Critical Connection Points

**Point 1 — Click to Lead:**
Google Auto-Tagging appends `gclid` to the landing page URL. The website captures this and stores it as a hidden field on the contact form. When the patient submits, the gclid travels with the lead record.

**Point 2 — Lead to Dentrix:**
Three options (ranked by reliability):
1. **Middleware (Zapier / Make)** — form submission triggers Zap → creates Dentrix appointment with source tag auto-populated
2. **Manual Tagging** — front desk selects "Referral Source" in Dentrix at booking time (human-dependent, ~80% accurate)
3. **CSV + Python match** — match lead email/phone from CRM to Dentrix patient record by name + DOB (best-effort, ~70% match rate)

---

## 3. Patient Journey Scenarios

### 3.1 Simple — Maria Rodriguez
**Integration: Google Ads → Dentrix (direct, no CRM)**

**The story:**
1. Maria searches "dental implants near me" on Google
2. Clicks ad from campaign `implants-search`, keyword `dental implants cost`
3. `gclid=XYZ789` captured on landing page
4. Maria calls the practice — **CallRail** captures gclid, routes to front desk
5. Front desk books appointment → selects Referral Source: **Google Ads** in Dentrix
6. Maria attends Feb 1 → treatment plan accepted → pays **$4,200**
7. Dentrix Production Summary exported nightly → Python ETL → Delta table
8. NexoBI AI answers: *"implants-search generated $4,200 from 1 attended patient. ROAS: 14x on $300 spend."*

**Row in NexoBI data table:**
```
date         = 2026-02-01
data_source  = Google Ads
channel_group= Paid Search
campaign     = implants-search
total_cost   = 300.00
total_revenue= 4200.00
sessions     = 1
leads        = 1
booked       = 1
attended     = 1
```

---

### 3.2 Multi-Patient — Campaign Comparison
**Integration: Google Ads → Dentrix (3 patients, 2 campaigns)**

**The patients:**

| Patient | Campaign | Status | Revenue |
|---|---|---|---|
| Maria | implants-search | Attended, paid | $4,200 |
| James | implants-display | Booked, no-show | $0 |
| Linda | implants-search | Booked, rescheduled → attended | $6,800 |

**What NexoBI surfaces:**
- **Health Score drops** when James no-shows (show rate falls below 78% benchmark)
- **AI comparison**: "implants-search ROAS = 3.14x vs implants-display ROAS = 0.19x — display is burning budget"
- **Linda's attribution**: The referral source tag survives the reschedule in Dentrix → $6,800 correctly attributed to `implants-search`
- **AI recommendation**: "Shift budget from implants-display to implants-search — display is 16x less efficient per attended patient"

**Aggregated rows:**
```
implants-search:  cost=$3,500  revenue=$11,000  booked=2  attended=2  ROAS=3.14x
implants-display: cost=$1,200  revenue=$0        booked=1  attended=0  ROAS=0.00x
```

---

### 3.3 Complex — David Chen (HubSpot Nurture + LTV)
**Integration: Google Ads → HubSpot → Dentrix → NexoBI**

**The full journey:**

| Date | Event | Platform |
|---|---|---|
| Jan 15 | David clicks Google Ads retargeting ad, `gclid=DEF456` | Google Ads |
| Jan 15 | Lands on implant cost page (3 min dwell time) | GA4 |
| Jan 15 | Doesn't convert — exits | — |
| Jan 16 | Sees retargeting Facebook ad | Meta Ads |
| Jan 16 | Fills contact form — gclid + UTM captured | Website |
| Jan 16 | HubSpot lead created: source=Google Ads, campaign=implants-search | HubSpot |
| Jan 17–27 | 5-email nurture sequence (HubSpot workflow, 11 days) | HubSpot |
| Jan 27 | David clicks email → books consultation | HubSpot / Dentrix |
| Jan 27 | Front desk creates Dentrix appt, syncs source tag | Dentrix |
| Feb 3 | David attends, pays **$3,800** for crown | Dentrix |
| Mar 15 | Returns for implant consult | Dentrix |
| Mar 15 | Upsells to full implant: pays **$10,400** | Dentrix |

**Total LTV from one $87.50 click: $14,200 (ROAS: 162x)**

**What NexoBI surfaces:**
- Google Ads implants-search delivers **4.7x higher patient LTV** than organic referrals
- The 11-day HubSpot nurture sequence is a **revenue multiplier** — patients who complete it spend 3.1x more on first visit
- February AI answer: *"David Chen: $3,800 from attended appointment — source: Google Ads implants-search"*
- March AI answer: *"Returning patient revenue +$10,400 — same source attribution carried forward"*

**Data rows:**
```
Feb 3:
  data_source=Google Ads, campaign=implants-search
  total_cost=87.50, total_revenue=3800, booked=1, attended=1

Mar 15 (return visit):
  data_source=Google Ads, campaign=implants-search
  total_cost=0, total_revenue=10400, booked=1, attended=1
```

> **Product insight:** NexoBI is the only place where $87.50 click → $14,200 LTV is visible as a single story. Google Ads sees a $87.50 click with a form fill. HubSpot sees a nurtured lead. Dentrix sees two separate appointments. NexoBI connects them all.

---

## 4. Integration Ecosystem Map

Six key integration pairs, ranked by revenue impact:

### 🥇 Rank 1 — CallRail + Google Ads + Dentrix
**The attribution gap closer**

- **Problem:** 60–70% of dental leads call the practice rather than submit a form. Google Ads conversion tracking only sees form fills → most conversions are invisible.
- **Solution:** CallRail creates tracking phone numbers for each ad campaign. When a patient calls, CallRail captures the `gclid`, records the call, and can push the lead (with source) into Dentrix or CRM.
- **NexoBI impact:** Closes the largest single attribution gap. Practices discover their real ROAS is often 2–3x higher than reported in Google Ads.
- **Data flow:** CallRail API → Python ETL → `data_source = "Google Ads (Call)"`, `channel_group = "Paid Search"` → Delta table

---

### 🥈 Rank 2 — GA4 + Google Ads + Dentrix
**The content-to-patient pipeline**

- **Problem:** Patients who research cost and financing pages are 2.4x more likely to accept a treatment plan — but this behavior is invisible to Dentrix.
- **Solution:** GA4 event tracking on key pages (pricing, financing, before/after gallery) → linked to Google Ads via Linked Accounts → imported as conversion signals.
- **NexoBI impact:** Show which content pages correlate with highest-revenue patients. Budget optimization: invest in content that attracts high-LTV patients, not just any click.
- **Key GA4 events:** `page_view` (implant cost page), `scroll_depth` (>75%), `form_start`, `phone_click`, `financing_calculator_use`

---

### 🥉 Rank 3 — Podium / Birdeye (Reviews) + Dentrix
**The brand trust signal**

- **Problem:** A Google rating drop from 4.8 → 4.3 caused an 18% CTR drop on Google Ads, costing $12,000 in lost revenue over 6 weeks — with no alert.
- **Solution:** Podium/Birdeye monitors review score changes and can trigger automated patient review requests from Dentrix (post-appointment).
- **NexoBI impact:** Correlate review score trend with CTR trend and revenue trend in the AI Agent. Surface: *"Rating dropped to 4.2 two weeks ago — CTR down 14%, 6 fewer leads this week."*
- **Data flow:** Podium API → `data_source = "Google Reviews"` → daily rating score as a signal column

---

### 4️⃣ Rank 4 — Weave / NexHealth + Dentrix
**The show rate optimizer**

- **Problem:** Industry average show rate is 78%. Practices using SMS reminders average 91% vs 71% for email-only.
- **Solution:** Weave/NexHealth integrates directly with Dentrix to send automated SMS appointment reminders and two-way confirmations.
- **NexoBI impact:** Show rate improvement from 71% → 91% = 28% more attended appointments from the same booking volume = direct revenue lift. Quantifiable in the dashboard.
- **AI demo question:** *"What would our revenue be if show rate improved from 74% to 90%?"*

---

### 5️⃣ Rank 5 — Mailchimp + Dentrix
**The reactivation revenue channel**

- **The scenario:** 847 patients haven't visited in 18+ months. Mailchimp reactivation campaign (3 emails, $180 total spend) → 23 patients rebook → $31,200 revenue (ROAS: 173x).
- **Solution:** Dentrix patient export → Mailchimp audience → automated reactivation sequence → booking link (with UTM) → Dentrix.
- **NexoBI impact:** `data_source = "Email – Reactivation"` rows show the highest ROAS of any channel. Proves the value of the patient database as a marketing asset.
- **Data flow:** Dentrix patient export (lapsed patients) → Mailchimp → UTM-tracked booking link → Dentrix new appointments → NexoBI

---

### 6️⃣ Rank 6 — LinkedIn + HubSpot + Dentrix
**The DSO B2B attribution pipeline**

- **Use case:** Dental Service Organizations (DSOs) marketing to practice owners, not patients. LinkedIn for awareness → HubSpot for CRM/nurture → Dentrix for clinical outcomes.
- **NexoBI impact:** For DSO clients, LinkedIn ROAS is measured differently — revenue is multi-location production uplift, not per-patient. NexoBI can aggregate across all practice locations.
- **Data flow:** LinkedIn Ads → HubSpot (lead stage tracking) → `data_source = "LinkedIn"`, `channel_group = "B2B Social"` → Delta table

---

## 5. Platform-by-Platform Reference

### 5.1 Dentrix

**Two versions in the market:**

| Feature | Dentrix G-Series | Dentrix Ascend |
|---|---|---|
| Deployment | On-premise desktop | Cloud (SaaS) |
| Market share | ~70% of practices | ~30%, growing |
| REST API | ❌ None | ✅ Yes (Henry Schein One Developer Program) |
| ODBC access | ✅ Read-only SQL | ❌ Not applicable |
| CSV export | ✅ Production Summary nightly | ✅ Downloadable reports |
| API approval | N/A | Requires partnership approval (2–6 weeks) |

**Dentrix G-Series — Recommended Pipeline:**
```
Dentrix nightly Production Summary export (CSV)
    → Python script (scheduled, e.g. cron 2am)
    → Map columns to NexoBI schema
    → MERGE INTO workspace.silver.DemoData-marketing-crm
    → NexoBI reads fresh data each morning
```

**Dentrix Ascend — REST API endpoints (once approved):**
- `GET /patients` — patient demographics, referral source
- `GET /appointments` — date, status (Scheduled/Complete/Broken), provider
- `GET /production` — treatment production amounts per patient
- `GET /referrals` — referral source by patient/appointment

**Dentrix fields → NexoBI schema mapping:**

| Dentrix Field | NexoBI Column | Notes |
|---|---|---|
| Appointment Date | `date` | Daily row granularity |
| Referral Source | `data_source` | Maps to platform name |
| Appointment Status | — | "Complete" → contributes to `attended` |
| Production Amount | `total_revenue` | Sum of production by source/date |
| # Appointments Scheduled | `booked` | Count of booked appts |
| # Appointments Completed | `attended` | Count of "Complete" appts |

---

### 5.2 Google Ads + CallRail

**Google Ads native data (via API or CSV export):**
- Campaign, Ad Group, Keyword
- Impressions, Clicks, Cost, Conversions (form only)
- `gclid` for auto-tagging

**CallRail additions:**
- Tracking numbers per campaign (or per keyword)
- `gclid` captured from caller's session
- Call duration, recording, answered/missed
- Lead score (CallRail AI)

**Combined NexoBI row:**
```
data_source  = "Google Ads"
channel_group= "Paid Search"
campaign     = "implants-search"
clicks       = 47
total_cost   = 1,840.00
leads        = 12        ← form fills (6) + tracked calls (6)
booked       = 8         ← from Dentrix referral source match
attended     = 7         ← from Dentrix appointment status
total_revenue= 24,600.00 ← from Dentrix production
```

---

### 5.3 Meta Ads

**Data available:**
- Campaign, Ad Set, Ad
- Reach, Impressions, Link Clicks, Cost
- Lead Form submissions (native Meta leads)
- `fbclid` for browser tracking (less reliable than gclid)

**Integration challenge:** Meta's 7-day click / 1-day view attribution window often double-counts with Google. Use **Databricks as the single source of truth** — if a patient has both a `gclid` and `fbclid`, attribute to whichever platform the front desk selected in Dentrix.

**NexoBI column:** `data_source = "Facebook"` or `"Meta – Instagram"`

---

### 5.4 GA4

**Key events to track:**

| Event | What it signals | NexoBI use |
|---|---|---|
| `page_view` on /implants | Research intent | High-intent session flag |
| `scroll` (75%+) on cost page | Serious consideration | LTV predictor |
| `click` on phone number | High-intent contact | Feeds CallRail |
| `form_start` | Top-funnel conversion | `sessions` → `leads` |
| `form_submit` | Lead created | `conversions` |
| `financing_calc_use` | High-value patient signal | Treatment plan predictor |

**GA4 → NexoBI:**
```
data_source  = "Organic Search" / "Direct" / "Referral"
channel_group= "Organic" / "Direct"
sessions     = GA4 session count by source/date
new_users    = GA4 new users by source/date
conversions  = GA4 form_submit events
```

---

### 5.5 HubSpot CRM

**Data available:**
- Contact record: name, email, phone, lifecycle stage
- Deal record: stage, amount, close date
- Email activity: opens, clicks, unsubscribes
- UTM / gclid on first touch (captured by HubSpot tracking pixel)
- Workflow enrollment and completion

**HubSpot → Dentrix handoff options:**
1. **Zapier/Make automation:** Deal moves to "Booked" stage → creates Dentrix appointment with referral source from HubSpot UTM
2. **Manual sync:** Front desk checks HubSpot for source before entering Dentrix
3. **API push:** HubSpot webhook → Python function → Dentrix API (Ascend only)

**NexoBI use:** HubSpot is the bridge between ad click and Dentrix booking for practices with a multi-touch nurture sequence. Tracks the 11-day gap between lead and appointment that would otherwise be invisible.

---

### 5.6 Weave / NexHealth

**What they do:** Patient communication platforms that integrate natively with Dentrix — SMS/email reminders, two-way texting, online booking, review requests.

**NexoBI integration:**
- Pull reminder send/open/confirm rates as a signal column
- Correlate confirmation rate with actual show rate
- Surface: *"Patients who confirmed via SMS showed at 91% vs 71% for email-only"*

**Data flow:** Weave API → `source_medium = "sms_reminder"` signal → Delta table

---

### 5.7 Podium / Birdeye (Reviews)

**What they do:** Aggregate Google, Facebook, Yelp reviews. Automate post-appointment review requests triggered from Dentrix.

**NexoBI integration:**
- Daily review score as a separate Delta table joined to main table
- Correlate score drops with CTR drops and revenue impact
- AI question: *"How much revenue did we lose when our rating dropped to 4.2?"*

---

### 5.8 LinkedIn Ads

**Use case:** DSO / enterprise dental groups marketing to practice owners or referral dentists.

**Data available:**
- Sponsored Content, InMail, Lead Gen Forms
- Company targeting: practice size, specialty
- Lead form submissions with contact info

**NexoBI column:** `data_source = "LinkedIn"`, `channel_group = "B2B Social"`

---

## 6. Data Pipeline Architecture

### Full Pipeline (Production)

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (raw)                        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Google Ads  │  Meta Ads    │  GA4         │  CallRail      │
│  (API/CSV)   │  (API/CSV)   │  (API/CSV)   │  (API)         │
│              │              │              │                │
│  HubSpot     │  Dentrix     │  Weave       │  Podium        │
│  (API)       │  (CSV/ODBC)  │  (API)       │  (API)         │
└──────┬───────┴──────┬───────┴──────┬───────┴───────┬────────┘
       │              │              │               │
       └──────────────┴──────────────┴───────────────┘
                              │
                     Python ETL scripts
                     (scheduled nightly, 2am)
                              │
                    ┌─────────▼──────────┐
                    │   Normalization    │
                    │  • date coerce     │
                    │  • source mapping  │
                    │  • column aliasing │
                    │  • deduplication  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Databricks Delta  │
                    │  Unity Catalog     │
                    │                    │
                    │  workspace.silver  │
                    │  .DemoData-        │
                    │   marketing-crm    │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │     NexoBI         │
                    │  Dashboard + AI    │
                    └────────────────────┘
```

### Recommended ETL Schedule

| Job | Schedule | Source | Target |
|---|---|---|---|
| Dentrix Production Summary | 2:00 AM daily | CSV export from Dentrix | Delta table (MERGE) |
| Google Ads stats | 3:00 AM daily | Google Ads API | Delta table (MERGE) |
| Meta Ads stats | 3:15 AM daily | Meta Marketing API | Delta table (MERGE) |
| CallRail calls | 3:30 AM daily | CallRail API | Delta table (MERGE) |
| GA4 sessions | 4:00 AM daily | GA4 Data API | Delta table (MERGE) |
| HubSpot leads | 4:30 AM daily | HubSpot API | Delta table (MERGE) |

**Use `MERGE INTO` (not INSERT) to avoid duplicates on re-runs:**
```sql
MERGE INTO workspace.silver.`DemoData-marketing-crm` AS target
USING staging_table AS source
ON target.date = source.date
   AND target.data_source = source.data_source
   AND target.campaign = source.campaign
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

---

## 7. Databricks Schema & Table

**Full table reference:**
```
catalog : workspace
schema  : silver
table   : DemoData-marketing-crm
full    : workspace.silver.`DemoData-marketing-crm`
```

**Genie Space (AI Agent live mode):**
```
Space ID: 01f111cb463a1c1e8c2a03deb976f2a8
Connected to: DemoData-marketing-crm
Model: Llama 3.3 70B Instruct (via Databricks Model Serving)
```

**Genie REST API flow:**
```
1. POST /api/2.0/genie/spaces/{space_id}/start-conversation
   Body: { "content": "user question" }
   Returns: { "conversation_id": "...", "message_id": "..." }

2. GET /api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}
   Poll until status = "COMPLETED"
   Returns: { "attachments": [{ "text": { "content": "..." }, "query": { "query": "SELECT..." } }] }

3. GET /api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}/query-result/{statement_id}
   Returns: Arrow/JSON result table
```

---

## 8. NexoBI Data Schema Mapping

### Source → NexoBI column mapping by platform

| NexoBI Column | Google Ads | Meta Ads | GA4 | Dentrix | CallRail | HubSpot |
|---|---|---|---|---|---|---|
| `date` | stat date | date_start | date | appt date | call date | activity date |
| `data_source` | "Google Ads" | "Facebook" | "Organic Search" | Referral Source | "Google Ads (Call)" | UTM source |
| `channel_group` | campaign type | placement | default channel | — | "Paid Search" | UTM medium |
| `campaign` | campaign name | campaign name | — | — | tracking number name | campaign name |
| `total_cost` | cost | spend | — | — | subscription/mo ÷ days | — |
| `total_revenue` | — | — | — | production amount | — | deal amount |
| `sessions` | — | — | sessions | — | — | — |
| `clicks` | clicks | link_clicks | — | — | — | — |
| `impressions` | impressions | impressions | — | — | — | — |
| `leads` | conversions | leads | form_submit | — | answered calls | contacts created |
| `booked` | — | — | — | appointments booked | — | deals "Booked" |
| `attended` | — | — | — | appointments "Complete" | — | — |
| `new_users` | — | — | new_users | new patients | — | — |
| `source_medium` | google / cpc | facebook / paid | source / medium | direct / offline | google / call | source / medium |

---

## 9. Sales Talking Points

### The Core NexoBI Value Prop (integration angle)

> *"Every practice has the same problem — your data is in four different places, and none of them talk to each other. Google Ads knows you spent $3,000 last month. Meta knows you got 47 form fills. Dentrix knows 12 patients attended and paid $28,400. But nobody knows which ads drove which patients, or what each click is actually worth. NexoBI is the connective tissue. We pull everything into one place and put an AI analyst on top of it."*

### Objection: "We already have reporting in Google Ads / Meta"
> *"Google Ads will show you a conversion when someone fills out a form. But what happened after that form fill? Did they book? Did they show up? Did they pay $400 or $4,000? Google doesn't know — only Dentrix knows. NexoBI closes that loop. You'll discover your real ROAS is often 2–3x higher than Google reports, because 60% of your leads call instead of filling out a form."*

### Objection: "Dentrix doesn't have an API"
> *"For G-Series — the most common version — we use the nightly Production Summary export. Dentrix already generates this report every night. We add a Python script that picks it up, maps it to your data structure, and loads it into Databricks by 4am. No API needed, no changes to your Dentrix setup."*

### The David Chen moment (best demo scenario)
> *"Here's an example that shows what's possible. One patient, David Chen — he clicked a Google retargeting ad, didn't convert, came back 11 days later after a nurture email sequence, booked a consultation, paid $3,800 for a crown, then returned 6 weeks later for a full implant at $10,400. Total lifetime value: $14,200. From a $87.50 click. ROAS of 162x. Google Ads showed: one click, no conversion. HubSpot showed: one nurtured lead. Dentrix showed: two separate appointments. NexoBI is the only place where that $14,200 story is visible as one thread."*

### The Show Rate angle
> *"Your show rate is a hidden ROAS lever. If you have 100 bookings per month and your show rate goes from 74% to 90%, that's 16 more attended appointments — without spending a single dollar more on ads. NexoBI tracks show rate by source, so you know which channels bring patients who actually show up, and which ones book and ghost."*

---

## 10. Roadmap & Open Questions

### Immediate (next session)
- [ ] Build the simple Maria Rodriguez scenario into the demo script as a live walkthrough
- [ ] Add CallRail as a named integration in the sidebar (currently only 5 platforms shown)
- [ ] Add a "Connected Platforms" detail panel (click a platform → see data flow diagram)

### Short term
- [ ] Python ETL script template for Dentrix G-Series CSV → Delta table
- [ ] HubSpot → Dentrix handoff automation (Zapier template)
- [ ] No-show reason pull from Dentrix (if referral source + appointment notes are accessible)
- [ ] Patient LTV estimate column in NexoBI schema (`total_revenue / attended` per patient)

### Open Questions
- **Dentrix Ascend API:** Does the practice use G-Series or Ascend? (Determines connection method)
- **CallRail:** Is it already in use? (If yes, integration is fast — they already track gclid)
- **HubSpot:** Is there an existing CRM? Or do they use a spreadsheet / Dentrix alone?
- **Data latency:** Is a nightly refresh acceptable, or does the practice need same-day data?
- **Multi-location:** Single practice or DSO with multiple locations? (Determines whether a `location` column is needed)

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: reconstructed from archived session — February 27, 2026*

---

---

## 11. Case Study — EHR + Paid Marketing with HIPAA Guardrails

### Overview

**Platforms:** athenahealth (EHR) · Google Ads · Meta Ads · NexoBI
**Use case:** A multi-specialty healthcare or dental practice that uses a full Electronic Health Record system (EHR) wants to connect paid marketing performance with clinical outcomes — without ever exposing Protected Health Information (PHI) to ad platforms or analytics tools.

> ⚠️ **This is the highest-stakes integration.** EHR data contains PHI (diagnoses, treatment notes, insurance, DOB). Sending any of this to Google Ads or Meta — even accidentally — is a HIPAA violation. The architecture below is designed from the ground up to be HIPAA-safe.

---

### The Core Problem

Standard marketing pixels (Google Ads Tag, Meta Pixel) are **not HIPAA-compliant**. They sit in the browser and can inadvertently capture:
- URL parameters containing patient IDs
- Page names revealing diagnoses (e.g. `/treatment/dental-implants/thank-you`)
- Form field data if autofill is active
- IP addresses combined with health-related page visits

**Most practices violate HIPAA every day without knowing it** — because their marketing agency installed a pixel on the patient portal, the booking confirmation page, or the treatment detail page.

NexoBI's role: replace browser-side tracking with a **server-side, de-identified pipeline** that gives marketing teams the attribution data they need without putting PHI at risk.

---

### HIPAA Guardrails — The Non-Negotiables

| Guardrail | What it means | How it's enforced |
|---|---|---|
| **No PHI in marketing platforms** | Patient name, DOB, diagnosis, insurance, SSN never sent to Google or Meta | Server-side only; PII stripped before transmission |
| **No pixel on clinical pages** | Google/Meta tags removed from patient portal, booking confirmation, treatment pages | Tag Manager rule: fire on `/contact`, `/thank-you` only — never `/patient-portal/*` |
| **Hashed identifiers only** | Email and phone SHA-256 hashed before sending to Enhanced Conversions or Meta CAPI | Python hashing layer in ETL script |
| **De-identified aggregates to NexoBI** | NexoBI receives row counts and dollar totals — never individual patient records | ETL groups by date + source + campaign before load |
| **BAA with all vendors** | Business Associate Agreements signed with Google (via Google Workspace), Meta (via CAPI partner), Databricks | Legal prerequisite before go-live |
| **Audit logging** | Every EHR data access logged (who, when, what query) | Databricks Unity Catalog audit logs + EHR access logs |
| **Data retention limits** | Marketing data purged after 24 months; PHI never stored in Delta tables | Databricks table properties + scheduled DELETE jobs |
| **Consent management** | Patient consent captured for marketing communications (not treatment) | Consent flag stored in EHR; only consented patients used for audience building |

---

### Architecture: Two-Layer Separation

The key design principle: **PHI layer and marketing layer never touch directly.**

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHI LAYER (secured)                      │
│                                                                 │
│   athenahealth EHR                                              │
│   ├── Patient records (name, DOB, diagnoses, insurance)        │
│   ├── Appointment records (date, provider, status, CPT codes)  │
│   ├── Production / billing records                             │
│   └── Referral source (self-pay, insurance, "Google Ads")      │
│                                                                 │
│   ⬇  Secure export (SFTP + TLS 1.3, no PHI columns selected)  │
│                                                                 │
│   De-identification Script (Python — runs inside secure VPC)   │
│   ├── DROP: name, DOB, SSN, diagnosis codes, notes, insurance  │
│   ├── HASH: email (SHA-256), phone (SHA-256)                   │
│   ├── AGGREGATE: group by date + referral_source + appt_status │
│   └── OUTPUT: de-identified aggregate rows only                │
│                                                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │  De-identified aggregates only
                          │  (no PHI crosses this line)
┌─────────────────────────▼───────────────────────────────────────┐
│                     MARKETING LAYER (NexoBI)                    │
│                                                                 │
│   Databricks Delta Table (workspace.silver.DemoData-mkt-crm)   │
│   ├── date, data_source, campaign, channel_group               │
│   ├── total_cost, total_revenue, sessions, leads               │
│   ├── booked (count), attended (count)                         │
│   └── NO patient names, NO diagnoses, NO PHI                   │
│                                                                 │
│   NexoBI Dashboard + AI Agent                                   │
│   ├── "Which campaign produced the most attended appointments?" │
│   ├── "What is ROAS by channel this month?"                    │
│   └── "Show me show rate trend by referral source"             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### Server-Side Conversion Tracking (HIPAA-Safe Pixels)

Instead of browser pixels, use **server-side APIs** to report conversions to Google and Meta.

#### Google Ads — Enhanced Conversions (Server-Side)

```
Patient books appointment on website
    ↓
Website sends form data to YOUR server (not Google directly)
    ↓
Python function:
    email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    phone_hash = hashlib.sha256(phone.strip().encode()).hexdigest()
    ↓
POST to Google Ads API — Conversions endpoint:
    {
      "conversions": [{
        "gclid": "ABC123",
        "conversion_action": "booking_form_submit",
        "conversion_date_time": "2026-02-01 10:30:00",
        "user_identifiers": [
          { "hashed_email": "<sha256_hash>" },
          { "hashed_phone_number": "<sha256_hash>" }
        ]
      }]
    }
    ↓
Google matches hashed email/phone to signed-in Google account
→ Attribution credited to correct campaign/keyword
→ NO PHI transmitted — only a hash Google can match
```

#### Meta Ads — Conversions API (CAPI)

```
Same form submission event
    ↓
Python function hashes email + phone (SHA-256)
    ↓
POST to Meta CAPI:
    {
      "data": [{
        "event_name": "Lead",
        "event_time": 1706784600,
        "user_data": {
          "em": ["<sha256_email_hash>"],
          "ph": ["<sha256_phone_hash>"]
        },
        "custom_data": {
          "value": 0,
          "currency": "USD",
          "content_category": "dental_consultation"
        }
      }]
    }
    ↓
Meta matches hash to Facebook/Instagram account
→ Lead attributed to correct ad/campaign
→ Browser pixel can be REMOVED from the site entirely
```

**Result:** Google and Meta receive only hashed identifiers. They can match to their own user database for attribution — but no PHI ever leaves your server.

---

### Patient Journey Scenario — Sofia Ramirez

**Integration: athenahealth EHR → Google Ads + Meta Ads → NexoBI (HIPAA-Safe)**

| Date | Event | Platform | PHI involved? |
|---|---|---|---|
| Feb 1 | Sofia searches "orthodontist near me" | Google | No |
| Feb 1 | Clicks Google Ad, `gclid=GHI789` | Google Ads | No |
| Feb 1 | Lands on `/services/orthodontics` page | Website | No |
| Feb 1 | Submits contact form | Website | Email + phone (hashed immediately) |
| Feb 1 | Server hashes email + phone → sends to Google Enhanced Conversions | Server-side | Hashed only — no PHI |
| Feb 1 | Lead record created in EHR (athenahealth) | EHR | Yes — PHI stays in EHR |
| Feb 3 | Front desk calls Sofia, books appointment | Phone / EHR | Yes — PHI stays in EHR |
| Feb 3 | Referral Source = "Google Ads – Ortho" entered in athenahealth | EHR | Yes — PHI stays in EHR |
| Feb 15 | Sofia attends consultation | EHR | Yes — PHI stays in EHR |
| Feb 15 | Treatment plan accepted: $5,400 braces | EHR | Yes — PHI stays in EHR |
| Feb 16 | Nightly EHR export — de-identification script runs | ETL | PHI stripped; only aggregate row exported |
| Feb 16 | Delta table updated | Databricks | No PHI — aggregate only |

**NexoBI Delta row (no PHI):**
```
date          = 2026-02-15
data_source   = "Google Ads"
channel_group = "Paid Search"
campaign      = "ortho-search"
total_cost    = 420.00      ← campaign daily spend
total_revenue = 5400.00     ← from EHR production (de-identified aggregate)
booked        = 1
attended      = 1
leads         = 1
```

**NexoBI AI answers:**
- *"ortho-search: $5,400 revenue, ROAS 12.9x on $420 spend — 1 attended consultation."*
- *"Show rate for Google Ads referrals: 94% this month vs 71% industry average."*

**What never appears in NexoBI:** Sofia's name, DOB, diagnosis, insurance plan, treatment notes, or any other PHI.

---

### EHR → NexoBI Field Mapping (De-Identified)

| athenahealth Field | Action | NexoBI Column |
|---|---|---|
| `appointment_date` | Pass through | `date` |
| `referral_source` | Map to platform name | `data_source` |
| `appointment_status` | "Checked Out" → attended | `attended` (count) |
| `appointment_status` | "Scheduled" → booked | `booked` (count) |
| `net_production_amount` | Sum by source/date | `total_revenue` |
| `patient_name` | **DROP — never exported** | — |
| `date_of_birth` | **DROP** | — |
| `diagnosis_codes` | **DROP** | — |
| `insurance_carrier` | **DROP** | — |
| `patient_email` | **HASH only** (for CAPI/Enhanced Conv.) | Not stored in Delta |
| `patient_phone` | **HASH only** (for CAPI/Enhanced Conv.) | Not stored in Delta |

---

### Supported EHR Platforms

| EHR | Deployment | API / Export method | BAA available? |
|---|---|---|---|
| **athenahealth** | Cloud (SaaS) | REST API (athenaPractice API) | ✅ Yes |
| **Epic** | On-premise / Cloud | FHIR R4 API (MyChart integration) | ✅ Yes |
| **eClinicalWorks** | Cloud / On-prem | REST API + CSV export | ✅ Yes |
| **Curve Dental** | Cloud (dental-specific) | REST API + CSV | ✅ Yes |
| **Open Dental** | On-premise (dental) | MySQL direct access / CSV export | ✅ (self-hosted) |
| **Eaglesoft** | On-premise (dental) | ODBC + CSV export (Patterson) | ✅ Yes |

> **Note:** For on-premise EHRs (Epic, Open Dental, Eaglesoft), the de-identification ETL script must run inside the practice's own network — never pulling PHI to an external server. The de-identified aggregate output is the only data that leaves the network.

---

### Sales Talking Points — EHR Case

> *"If you're running Google Ads and you have an EHR, there's a 90% chance you have a compliance problem right now. The Google Ads pixel on your thank-you page is recording health-intent page visits next to identifiable information — and that's a HIPAA violation. NexoBI replaces that pixel with a server-side integration that sends only hashed identifiers. Your marketing team gets the attribution data they need. Your compliance team can sleep at night."*

> *"And here's the business case: most EHR-connected practices have 20–30% of their revenue completely invisible to their marketing team. That production is in the EHR — but it's never connected to which ad, campaign, or keyword drove the patient. NexoBI closes that gap without touching a single line of PHI."*

---

---

## 12. Case Study — CRM + SEO / Organic Search

### Overview

**Platforms:** GoHighLevel (CRM) · SEMrush · Google Search Console · BrightLocal · NexoBI
**Use case:** A dental or healthcare practice wants to understand whether their SEO investment is generating real revenue — not just rankings and traffic, but actual patients and production dollars. This case connects organic search performance data with CRM lead tracking and EHR/practice revenue to produce a true **organic channel ROAS**.

> Most SEO agencies report on rankings and traffic. NexoBI reports on **revenue per keyword**.

---

### Why Organic Search Is Hard to Attribute

| What the SEO tool shows | What's missing |
|---|---|
| Keyword rankings | Whether ranking traffic converts to leads |
| Organic clicks (Google Search Console) | Whether those visitors called, booked, or became patients |
| Page-level traffic | Which content actually drives revenue vs just impressions |
| Domain authority trends | No connection to production dollars |
| Local pack appearances | No visibility into which Google Maps clicks became appointments |

**The attribution chain for organic search:**

```
Google Search (organic)
    ↓ Patient clicks result
Landing Page / Blog Post / Service Page
    ↓ UTM: source=google, medium=organic (or direct, if not tagged)
Form Submission / Phone Call
    ↓ Captured in CRM (GoHighLevel) with source=organic
Lead Record Created in CRM
    ↓ Source, keyword (from Search Console), page path stored
Appointment Booked (CRM → Dentrix / EHR sync)
    ↓ Source tag carried into practice management system
Patient Attends + Pays
    ↓ Revenue recorded in Dentrix / EHR
Nightly ETL
    ↓ CRM + GSC + SEMrush data → merged → Delta table
NexoBI
    ↓ "Organic Search ROAS = $X revenue per $1 of SEO investment"
```

---

### Platform Stack for This Case

| Platform | Role | What it contributes to NexoBI |
|---|---|---|
| **GoHighLevel (CRM)** | Lead capture, pipeline management, appointment booking | Lead source, lead stage, booking date, contact UTMs |
| **Google Search Console (GSC)** | Organic click + impression + position data | Clicks, impressions, CTR, avg. position by query + page |
| **SEMrush** | Keyword ranking tracking, competitor gap, content audit | Keyword position history, search volume, keyword difficulty |
| **BrightLocal** | Local SEO — Google Business Profile, local pack rankings | Local pack rank, Google Maps impressions/clicks, review signals |
| **Dentrix / EHR** | Clinical outcomes | Booked, attended, production revenue |

---

### Patient Journey Scenario — Carlos Mendez

**Integration: Organic Search → GoHighLevel CRM → Dentrix → NexoBI**

| Date | Event | Platform | Data captured |
|---|---|---|---|
| Jan 10 | Carlos searches "how much do dental implants cost in Miami" | Google | — |
| Jan 10 | NexoBI practice ranks #3 organically for that query | Google Search Console | Query: "dental implants cost miami", position: 3, 1 click |
| Jan 10 | Carlos lands on `/blog/dental-implant-cost-guide` | Website / GA4 | source=google, medium=organic, page=/blog/dental-implant-cost-guide |
| Jan 10 | Reads article (4 min), clicks "Get a Free Estimate" CTA | Website | Event: cta_click |
| Jan 10 | Fills out form — GoHighLevel captures lead | GoHighLevel CRM | source=google, medium=organic, landing_page=/blog/dental-implant-cost-guide |
| Jan 11 | GoHighLevel automated SMS sent: "Thanks Carlos, we'll call you" | GoHighLevel | Nurture step 1 |
| Jan 12 | Front desk calls Carlos — books consultation | GoHighLevel / Dentrix | Opportunity stage: "Booked" |
| Jan 12 | Referral source "Organic Search – Blog" entered in Dentrix | Dentrix | Source tag |
| Jan 20 | Carlos attends, treatment plan: $6,200 implant | Dentrix | attended=1, revenue=$6,200 |
| Jan 21 | Nightly ETL runs | Python | GSC + CRM + Dentrix → Delta table |

**NexoBI Delta row:**
```
date          = 2026-01-20
data_source   = "Organic Search"
channel_group = "Organic"
campaign      = "blog/dental-implant-cost-guide"   ← landing page as "campaign"
source_medium = "google / organic"
total_cost    = 0.00      ← no direct ad spend (SEO investment tracked separately)
total_revenue = 6200.00
sessions      = 1
leads         = 1
booked        = 1
attended      = 1
```

**NexoBI AI answers:**
- *"Organic Search generated $6,200 from 1 attended patient this month — from a blog post ranking #3 for 'dental implants cost miami'."*
- *"Top organic revenue pages: /blog/dental-implant-cost-guide ($6,200), /services/implants ($4,100), /services/orthodontics ($3,800)."*
- *"Organic vs Paid comparison: Organic ROAS = ∞ (no direct spend). Including SEO agency retainer of $2,500/mo: effective ROAS = 4.1x."*

---

### SEO Data Integration Details

#### Google Search Console → NexoBI

GSC provides keyword-level data via its API — **the most direct link between rankings and traffic.**

**GSC API data pulled daily:**
```python
# Query GSC for organic performance by page + query
gsc_data = {
  "dimensions": ["date", "page", "query"],
  "startDate": "2026-01-01",
  "endDate": "2026-01-31",
  "dimensionFilterGroups": [{
    "filters": [{"dimension": "country", "operator": "equals", "expression": "USA"}]
  }]
}
# Returns: clicks, impressions, ctr, position per query per page per day
```

**Mapped to NexoBI supplementary table:**
```
date        = 2026-01-10
page        = /blog/dental-implant-cost-guide
query       = dental implants cost miami
clicks      = 1
impressions = 34
ctr         = 2.94%
avg_position= 3.1
```

**Joined to main Delta table** by `date + landing_page` to link GSC keyword data to CRM leads.

---

#### SEMrush → NexoBI (Keyword Rank Tracking)

SEMrush tracks keyword positions over time — critical for showing **rank → traffic → revenue correlation.**

**SEMrush data pulled weekly (via API or CSV export):**

| Keyword | Position (current) | Position (30d ago) | Search Volume | NexoBI revenue from this keyword |
|---|---|---|---|---|
| dental implants cost miami | 3 | 7 | 1,900/mo | $6,200 |
| dental implants near me | 12 | 15 | 4,400/mo | $1,800 |
| orthodontist miami | 5 | 5 | 2,900/mo | $8,400 |
| teeth whitening cost | 18 | 22 | 1,600/mo | $320 |

**NexoBI AI question enabled by this join:**
> *"Which keywords are ranking AND converting to revenue? 'orthodontist miami' at position 5 is generating $8,400/mo. 'dental implants near me' at position 12 has high volume but only $1,800 — worth pushing to top 5."*

---

#### BrightLocal → NexoBI (Local SEO / Google Business Profile)

For dental/healthcare practices, **local pack rankings** (the map 3-pack on Google) often drive more leads than organic blue links.

**BrightLocal tracks:**
- Local pack position for target keywords (daily)
- Google Business Profile impressions, clicks, calls, direction requests
- Review count and average rating (correlates with CTR)

**BrightLocal data → NexoBI:**
```
date            = 2026-01-10
data_source     = "Google Business Profile"
channel_group   = "Local / Maps"
sessions        = 47     ← GBP website clicks
leads           = 8      ← GBP call clicks (tracked via CallRail number on GBP)
local_pack_rank = 2      ← position in maps 3-pack for "dentist miami"
```

**NexoBI AI question:**
> *"Our Google Maps ranking improved from position 4 to position 2 last month. GBP calls went from 31 to 47 — a 52% lift. Estimated revenue impact: +$4,200 from the additional 8 leads."*

---

### GoHighLevel CRM — Integration Details

GoHighLevel (GHL) is widely used by dental/healthcare marketing agencies. It combines CRM, pipeline management, SMS/email automation, and appointment booking.

**GHL → NexoBI data flow:**

```
GoHighLevel REST API
    ↓
GET /contacts — pull leads created in date range
    ↓
For each contact:
  - source (UTM source)
  - medium (UTM medium)
  - landing_page (first page visited)
  - lead_created_date
  - pipeline_stage (New Lead / Contacted / Booked / Attended / Won)
  - opportunity_value
    ↓
Python ETL: group by date + source + medium + landing_page
    ↓
Aggregate: count(leads), count(booked), count(attended), sum(revenue)
    ↓
MERGE INTO Delta table
```

**GHL Pipeline Stages → NexoBI columns:**

| GoHighLevel Stage | NexoBI column | Notes |
|---|---|---|
| New Lead | `leads` +1 | Any form/chat/call entry |
| Contacted | — | Tracked in GHL only |
| Appointment Booked | `booked` +1 | Stage moved to "Booked" |
| Appointment Attended | `attended` +1 | Confirmed by Dentrix sync |
| Won (Treatment Accepted) | `total_revenue` | Opportunity value from GHL or Dentrix |
| Lost / No-Show | — | Show rate calculated from booked vs attended |

---

### Measuring SEO ROI in NexoBI

The killer metric this integration enables: **true organic channel ROAS**, including SEO agency cost.

**Formula:**

```
Organic ROAS = Total Revenue (organic source) ÷ Total SEO Investment

Where:
  Total Revenue (organic) = sum of total_revenue where data_source = "Organic Search"
                           + sum of total_revenue where data_source = "Google Business Profile"
  Total SEO Investment    = monthly retainer (entered as a manual cost row in the Delta table)
                           + any content/link-building spend
```

**Example (monthly):**

| Metric | Value |
|---|---|
| Organic revenue (attributed via CRM) | $38,400 |
| GBP / Local pack revenue | $12,600 |
| Total organic revenue | $51,000 |
| SEO agency retainer | $3,500 |
| Content/link-building spend | $800 |
| **Total SEO investment** | **$4,300** |
| **Organic ROAS** | **11.9x** |

**NexoBI AI question:**
> *"Compare organic vs paid ROAS this month."*
> Answer: *"Organic: $51,000 revenue on $4,300 SEO investment = 11.9x ROAS. Paid search: $38,200 on $9,400 spend = 4.1x ROAS. Organic is 2.9x more efficient per dollar. Recommendation: increase SEO investment before scaling paid."*

---

### SEO Investment Row — Manual Cost Injection

Since SEO spend doesn't flow from an ad platform, it's added as a manual cost row in the Delta table:

```sql
-- Inserted once per month by ETL or manually
INSERT INTO workspace.silver.`DemoData-marketing-crm` VALUES (
  DATE '2026-02-01',   -- date (first of month)
  'Organic Search',    -- data_source
  'Organic',           -- channel_group
  'SEO Retainer',      -- campaign
  4300.00,             -- total_cost  ← SEO agency fee
  0.00,                -- total_revenue (revenue tracked via CRM rows)
  0, 0, 0, 0, 0        -- sessions, leads, booked, attended, conversions = 0
)
```

---

### NexoBI Dashboard — What's New With This Integration

| Feature | What it shows |
|---|---|
| **Organic channel card** | Sessions, leads, booked, attended, revenue — all from organic sources |
| **Top organic pages** | Which blog posts / service pages generate the most revenue (via GSC + CRM join) |
| **Keyword → revenue map** | GSC query data joined to CRM lead source → revenue per ranking keyword |
| **Local pack performance** | BrightLocal rank + GBP clicks + attributed revenue |
| **True SEO ROAS** | Total organic revenue ÷ SEO spend (including retainer) |
| **AI Agent questions** | "Which blog post is generating the most booked appointments?", "What's our organic ROAS vs paid?" |

---

### Sales Talking Points — SEO Case

> *"Your SEO agency sends you a monthly report with rankings and traffic. But do you know which keywords are actually driving patients through the door? Not clicks — patients. With NexoBI, we connect your Google Search Console rankings to your CRM lead source to your Dentrix appointments. Now your 'dental implants cost' blog post isn't just ranking #3 — it's generating $6,200 per attended patient."*

> *"Most practices have no idea what their SEO is really worth. They pay $3,000–$5,000/month and get a PDF with graphs. NexoBI tells you the organic ROAS — in this practice it was 11.9x. That's a better return than Google Ads. But you'd never know without connecting the dots."*

> *"And for content decisions: instead of guessing what to write next, NexoBI shows you which pages are converting. Invest in more content like the ones already driving booked appointments."*

---

### Open Questions — SEO Case Discovery

- **CRM in use?** GoHighLevel, HubSpot, spreadsheet, or Dentrix alone? (Determines lead tracking method)
- **SEO agency?** Who manages SEO, and can we get access to GSC and SEMrush? (Or BrightLocal if local-focused)
- **Google Business Profile?** Is GBP claimed and optimized? Do they track calls from GBP? (CallRail integration for GBP phone number)
- **Blog / content?** Is there existing content? (Identify pages already ranking for high-intent keywords)
- **SEO spend visibility?** Does the practice owner know their monthly SEO investment? (Required for ROAS calculation)
- **Attribution model preference?** First-touch (credit the blog post) or last-touch (credit the form submission page)? NexoBI defaults to last-touch but can be configured.

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Cases 11 & 12 added*

---

---

## 13. Deep Dive — Organic Search → EHR: The Full-Funnel Attribution Problem

### The Agency Complaint

Healthcare marketing agencies run into this constantly:

> *"Google Ads attribution is clean — gclid passes through, we see the patient, done. But organic search? The trail breaks somewhere between the website visit and the EHR. By the time a patient shows up as an appointment in Dentrix, we have no idea if they came from the blog post we published, a Google Maps listing, or just typed the practice name directly."*

This is the **organic attribution gap** — and it's not a tool problem, it's a structural problem. Here's why it's hard, and how NexoBI solves it.

---

### First: The Honest Answer About UTMs and Organic Search

**UTMs work for links you control. Organic search results are not a link you control.**

| Source | Can you add UTMs? | How attribution works |
|---|---|---|
| Google Ads | ✅ Auto-tagged with `gclid` | gclid carries through form, phone, CRM, to EHR |
| Meta Ads | ✅ `fbclid` auto-tagged | Similar to gclid, less reliable |
| Google Business Profile (Maps button) | ✅ Yes — you set the URL | Add `?utm_source=google&utm_medium=gmb&utm_campaign=local_pack` |
| Email campaigns | ✅ Yes — you write the link | Standard UTM on every link |
| Social posts | ✅ Yes — you write the link | Standard UTM |
| **Organic Google search (SERP blue link)** | ❌ **No** | Google controls the URL — you cannot add UTMs to organic rankings |
| **Bing / Yahoo organic** | ❌ No | Same — search engine controls the URL |
| Direct type-in | ❌ No | No referrer at all |

> **Bottom line:** For organic search from Google SERPs, UTMs are not the answer. You need a different approach — a **first-party attribution layer** that captures session data when the visitor arrives and carries it through to the booking.

---

### The Four Break Points Where Organic Attribution Dies

```
BREAK POINT 1             BREAK POINT 2           BREAK POINT 3         BREAK POINT 4
       │                        │                       │                     │
       ▼                        ▼                       ▼                     ▼
[Google Search]  →  [Website Visit]  →  [Lead Created]  →  [EHR Booked]  →  [NexoBI]
       │                        │                       │                     │
   Patient         GA4 sees it,        Patient calls      Front desk           Revenue
   clicks          but it's            instead of         doesn't note         shows no
   organic         session-only        form filling       referral source      source
   result          — not tied to                          in Dentrix
                   any booking
```

**Break Point 1 — No tracking parameter on the click**
Google organic results don't carry gclid or UTM. When the patient lands on your site, GA4 knows `source=google / organic` and the landing page — but nothing else is tagged.

**Break Point 2 — Phone call, not form**
60–70% of dental leads call instead of filling out a form. A phone call has no hidden field to carry attribution data. Without CallRail's Dynamic Number Insertion (DNI), the call is a black hole — GA4 knows the visitor came from organic, but there's no bridge from that session to the phone call.

**Break Point 3 — CRM doesn't capture source properly**
Even when a form IS submitted, many CRM setups don't capture the UTM/referral data from the session. The lead gets created, but `source` is blank, or defaults to "Website" with no channel distinction.

**Break Point 4 — EHR referral source is left blank or generic**
The front desk books the appointment in Dentrix. The Referral Source field is either skipped ("no time"), filled with "Internet" (useless), or filled manually based on what the patient says ("I found you on Google" — but was it organic or paid?). This is the most common and most damaging break point.

---

### The Solution: A First-Party Attribution Bridge

The architecture has three components working together:

#### Component 1 — Session Attribution Capture (Website)

When any visitor arrives — organic, direct, paid, or referral — the website captures their session context and stores it in a **first-party browser cookie** and/or **hidden form fields**.

```
Patient arrives at /blog/dental-implant-cost-guide
    ↓
JavaScript attribution script runs:

  // Detect source from referrer + UTM params
  const source   = getUTM('utm_source')  || detectReferrer()  // "google"
  const medium   = getUTM('utm_medium')  || "organic"
  const campaign = getUTM('utm_campaign')|| getLandingPage()   // "/blog/dental-implant-cost-guide"
  const keyword  = getUTM('utm_term')    || "(not provided)"
  const ga_cid   = getGA4ClientId()                            // "GA1.1.123456789.1706784000"

  // Store in first-party cookie (1st party = NOT PHI, just session metadata)
  setCookie('nexobi_attr', JSON.stringify({
    source, medium, campaign, keyword, ga_cid,
    first_touch_ts: Date.now(),
    landing_page: window.location.pathname
  }), 90)  // 90-day cookie — covers long nurture cycles

  ↓
Cookie is now set on the patient's browser
It persists across sessions for 90 days
It is NOT PHI — it contains no patient identity
```

**`detectReferrer()` logic:**
```python
def detectReferrer(referrer):
    if "google.com" in referrer:    return "google"
    if "bing.com" in referrer:      return "bing"
    if "facebook.com" in referrer:  return "facebook"
    if "instagram.com" in referrer: return "instagram"
    if referrer == "":              return "direct"
    return "referral"
```

---

#### Component 2 — Attribution Carried Into the Lead (Form + Phone)

**For form submissions — hidden fields:**

```html
<!-- Every contact/booking form on the website -->
<form id="contact-form">
  <input type="text"   name="name"     placeholder="Your name" />
  <input type="email"  name="email"    placeholder="Email" />
  <input type="tel"    name="phone"    placeholder="Phone" />

  <!-- Hidden attribution fields — populated by JS from the cookie -->
  <input type="hidden" name="attr_source"   id="attr_source" />
  <input type="hidden" name="attr_medium"   id="attr_medium" />
  <input type="hidden" name="attr_campaign" id="attr_campaign" />
  <input type="hidden" name="attr_keyword"  id="attr_keyword" />
  <input type="hidden" name="attr_ga_cid"   id="attr_ga_cid" />
  <input type="hidden" name="attr_landing"  id="attr_landing" />
</form>

<script>
  // On page load, populate hidden fields from attribution cookie
  const attr = JSON.parse(getCookie('nexobi_attr') || '{}');
  document.getElementById('attr_source').value   = attr.source   || '';
  document.getElementById('attr_medium').value   = attr.medium   || '';
  document.getElementById('attr_campaign').value = attr.campaign || '';
  document.getElementById('attr_keyword').value  = attr.keyword  || '';
  document.getElementById('attr_ga_cid').value   = attr.ga_cid   || '';
  document.getElementById('attr_landing').value  = attr.landing_page || '';
</script>
```

**Result:** When Carlos submits the form, his name + email + phone arrive alongside `source=google, medium=organic, campaign=/blog/dental-implant-cost-guide`. The CRM (GoHighLevel) receives all of it. His PII is handled securely; the attribution data is stored in the marketing layer.

---

**For phone calls — CallRail Dynamic Number Insertion (DNI):**

This is the solution to Break Point 2 — the 60–70% of leads who call instead of filling out a form.

```
CallRail DNI script is added to the website (like a GA4 tag)
    ↓
When the patient's session starts:
  - CallRail reads the GA4 client_id from the browser cookie
  - CallRail reads UTM params / referrer from the URL
  - CallRail dynamically swaps the phone number displayed on the page
    with a unique tracking number assigned to this session's source
    ↓
Patient sees: (305) 555-0192  ← unique number assigned to "google / organic"
(instead of the practice's real number)
    ↓
Patient calls → CallRail captures:
  - Which tracking number was called → which source/medium/campaign
  - GA4 client_id of the calling session
  - Call duration, answered/missed, recording
    ↓
CallRail webhook → GoHighLevel CRM:
  New contact created with:
    source   = "google"
    medium   = "organic"
    campaign = "/blog/dental-implant-cost-guide"
    type     = "inbound_call"
    ← same attribution as a form fill, for a phone lead
```

**This closes the biggest hole in organic attribution.** A patient who reads your blog for 6 minutes and then calls is now attributed to that blog post — exactly like a form fill.

---

#### Component 3 — Attribution Carried Into the EHR (HIPAA-Safe)

This is the final bridge — and the most delicate because this is where PHI enters the picture.

**Option A — Automated (via CRM → EHR middleware):**

```
Patient books appointment (via CRM, online booking, or front desk)
    ↓
Zapier / Make automation triggers on CRM stage = "Booked"
    ↓
Automation reads from CRM contact:
  attr_source   = "google"
  attr_medium   = "organic"
  attr_campaign = "/blog/dental-implant-cost-guide"
    ↓
Automation writes to Dentrix (via API or form fill):
  Referral Source = "Organic – Blog (Google)"
    ↓
NO PHI travels through the automation
The automation only passes the referral source tag
The patient's name, DOB, insurance — all stay in Dentrix
```

**Option B — Front Desk Protocol (manual, with CRM display):**

If automation is not available, the CRM (GoHighLevel) shows a "Source" field on the contact card. The front desk, when booking in Dentrix, sees the source on their screen and types it into the Referral Source field.

This requires a **front desk training protocol** — ideally with a standardized picklist in Dentrix:

```
Dentrix Referral Source Picklist (standardized):
  ├── Paid – Google Ads
  ├── Paid – Meta / Facebook
  ├── Paid – Meta / Instagram
  ├── Organic – Google Search
  ├── Organic – Blog / Content
  ├── Local – Google Maps / GBP
  ├── Email – Reactivation
  ├── Social – Organic Post
  ├── Referral – Patient
  ├── Referral – Provider
  └── Other / Unknown
```

**Why standardized picklist matters:** Free-text referral source fields produce unusable data. "Google", "the internet", "I googled it", "Google ad", "google organic" all mean different things but will appear as separate values in NexoBI. A picklist enforces consistency and makes the Delta table clean.

---

### Complete Architecture: Organic Search → EHR → NexoBI (HIPAA-Safe)

```
┌──────────────────────────────────────────────────────────────────────┐
│                      ANONYMOUS LAYER (no PHI)                        │
│                                                                      │
│  Google Search                                                       │
│    Patient searches "dental implants cost miami"                     │
│    Clicks organic result (no gclid, no UTM)                          │
│         │                                                            │
│         ▼                                                            │
│  Website /blog/dental-implant-cost-guide                             │
│    ├── GA4 captures: source=google, medium=organic, landing_page     │
│    ├── Attribution script sets 90-day first-party cookie             │
│    │     { source, medium, campaign, ga_cid, landing_page }          │
│    └── CallRail DNI swaps phone number for organic-specific number   │
│         │                                                            │
│  Patient converts (EITHER):                                          │
│    ├── Form fill → hidden fields carry attribution cookie → CRM      │
│    └── Phone call → CallRail captures session → CRM                  │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  Attribution metadata (NOT PHI)
                           │  source, medium, campaign, landing_page
┌──────────────────────────▼───────────────────────────────────────────┐
│                     CRM LAYER (GoHighLevel)                          │
│                                                                      │
│  Contact record created:                                             │
│    name, email, phone  ← PII (secured, not sent to NexoBI)          │
│    source = "google"                                                 │
│    medium = "organic"                                                │
│    campaign = "/blog/dental-implant-cost-guide"                      │
│    stage → Booked → Attended → Won                                   │
│         │                                                            │
│  Automation: stage = "Booked"                                        │
│    → Push referral source tag to Dentrix appointment                 │
│    → Tag only — no PHI crosses this bridge                           │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  Referral source tag only (no PHI)
┌──────────────────────────▼───────────────────────────────────────────┐
│                    EHR / DENTRIX LAYER (PHI secured)                 │
│                                                                      │
│  Appointment record:                                                 │
│    patient_name = "Carlos Mendez"   ← stays here forever            │
│    dob = 1987-04-12                  ← stays here forever            │
│    referral_source = "Organic – Blog (Google)"  ← from CRM tag      │
│    appointment_date = 2026-01-20                                     │
│    status = "Complete"                                               │
│    production = $6,200                                               │
│         │                                                            │
│  Nightly de-identification ETL:                                      │
│    DROP: name, dob, diagnosis, insurance, notes                      │
│    AGGREGATE: group by date + referral_source                        │
│    EXPORT: de-identified aggregate row only                          │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  De-identified aggregates (no PHI)
┌──────────────────────────▼───────────────────────────────────────────┐
│              DATABRICKS DELTA TABLE (NexoBI marketing layer)         │
│                                                                      │
│  date=2026-01-20, data_source="Organic Search",                      │
│  channel_group="Organic", campaign="/blog/dental-implant-cost-guide" │
│  total_revenue=6200, booked=1, attended=1, leads=1                   │
│                                                                      │
│  NexoBI AI: "Organic blog content generated $6,200 from 1           │
│  attended patient. Keyword: 'dental implants cost miami' (pos 3)."   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

### What About "Not Provided" Keywords?

A common frustration: Google stopped passing the search keyword in the URL referrer in 2013 for privacy reasons. So even if you detect `source=google / organic`, you often can't know the exact keyword.

**Three ways NexoBI recovers keyword data:**

| Method | What you get | Limitation |
|---|---|---|
| **Google Search Console API** | Exact query + clicks + position by landing page (aggregate) | Aggregate only — not tied to individual users/sessions |
| **GA4 Search Term report** (GSC linked) | Query by landing page, sessions, conversions | Still aggregate — not individual-level |
| **UTM on Google Business Profile link** | `utm_term=local_pack` tag on GBP website button | Tells you it was a Maps/GBP click, not SERP organic |
| **Attribution cookie `attr_campaign = landing_page`** | The landing page is a proxy for keyword intent | Not the exact query, but very close for SEO |

**The landing page as keyword proxy** is the most practical approach. If a patient lands on `/blog/dental-implants-cost-miami`, the blog post was written to rank for "dental implants cost miami" — so attributing revenue to that page is almost equivalent to attributing it to that keyword cluster.

GSC then confirms the connection: *"This page received 34 clicks for 'dental implants cost miami' at position 3 last month."* Combined with NexoBI's *"This landing page generated $6,200 revenue,"* you get keyword → revenue without needing the individual-level query.

---

### HIPAA Safety Check for This Architecture

| Data element | Layer it lives in | PHI? | Crosses to NexoBI? |
|---|---|---|---|
| Patient name | EHR only | ✅ PHI | ❌ Never |
| Date of birth | EHR only | ✅ PHI | ❌ Never |
| Diagnosis / treatment | EHR only | ✅ PHI | ❌ Never |
| Insurance carrier | EHR only | ✅ PHI | ❌ Never |
| Email address | CRM (hashed if sent to ad platforms) | ⚠️ PII | ❌ Never (hashed only for CAPI) |
| Phone number | CRM (hashed if sent to ad platforms) | ⚠️ PII | ❌ Never (hashed only) |
| GA4 Client ID | Cookie (anonymous browser ID) | ❌ Not PHI | ❌ Not needed in NexoBI |
| UTM source / medium | Cookie → form hidden field → CRM | ❌ Not PHI | ✅ Yes — as `data_source` |
| Landing page path | Cookie → CRM | ❌ Not PHI | ✅ Yes — as `campaign` |
| Referral source tag | CRM → EHR | ❌ Not PHI | ✅ Yes — as `data_source` (aggregated) |
| Production revenue | EHR → de-identified aggregate | ❌ De-identified | ✅ Yes — as `total_revenue` (sum) |
| Appointment count | EHR → de-identified aggregate | ❌ De-identified | ✅ Yes — as `booked`/`attended` |

> **The HIPAA safety of this architecture rests on one principle:** the attribution data (UTMs, referral source tags, landing pages) was never PHI to begin with. It describes where someone came from — not who they are or what their health condition is. The only moment PHI is involved is inside the EHR, and it never leaves.

---

### What NexoBI Surfaces From This Integration

With the full attribution bridge in place, these AI Agent questions become answerable:

| Question | Answer enabled by |
|---|---|
| *"Which blog posts are generating the most booked appointments?"* | Landing page → CRM lead source → Dentrix booked (via referral tag) |
| *"What is our organic search ROAS vs paid search ROAS?"* | Organic revenue (from EHR via referral source) ÷ SEO retainer vs Google Ads revenue ÷ ad spend |
| *"Which organic keyword cluster brings the highest-value patients?"* | GSC query → landing page → revenue (via NexoBI join) |
| *"How many phone leads came from organic search last 30 days?"* | CallRail DNI → organic-tagged calls → CRM leads count |
| *"What's the show rate for organic leads vs paid leads?"* | Referral source in EHR → attended ÷ booked by source |
| *"Is our local pack (Google Maps) driving more leads than organic search results?"* | GBP UTM-tagged clicks vs organic referrer detection — separate `data_source` rows |
| *"Which content piece drove the most revenue this quarter?"* | Landing page as campaign column → total_revenue sum |

---

### Common Agency Mistakes This Architecture Fixes

| Mistake | What goes wrong | Fix |
|---|---|---|
| Pixel on patient portal | HIPAA violation — health-intent pages tracked with user data | Remove all pixels from `/patient-portal/*` — use server-side only |
| Free-text referral source in Dentrix | "Google", "internet", "online" are all different values — unusable | Standardized picklist with ~10 defined options |
| No CallRail DNI | 60–70% of organic leads are invisible — only form fills tracked | Install CallRail DNI script on website, link to GA4 |
| UTM not on GBP link | Maps traffic looks like "direct" or "organic" — can't separate | Add `?utm_source=google&utm_medium=gmb` to GBP website button |
| GA4 not linked to GSC | Keyword data unavailable in GA4 reports | Link GSC property to GA4 in Google Analytics settings |
| Attribution cookie not set | Return visitors (2nd session) lose first-touch source | 90-day first-party cookie with first-touch logic (`if no cookie exists → set it`) |
| CRM doesn't store UTMs | Lead created but source field is blank | Configure GoHighLevel / HubSpot to capture `utm_*` params on all contact forms |

---

### Implementation Priority for Agencies

Roll out in this order — each step unlocks the next:

```
Week 1 — Foundation
  ✅ Standardize Dentrix referral source picklist
  ✅ Train front desk on 10-option picklist
  ✅ Add UTM to Google Business Profile website button

Week 2 — Website
  ✅ Install attribution cookie script on website
  ✅ Add hidden attribution fields to all contact forms
  ✅ Verify CRM is capturing utm_source, utm_medium, landing_page

Week 3 — Phone call coverage
  ✅ Install CallRail DNI script (if CallRail already in use)
  ✅ Configure organic-specific tracking pool in CallRail
  ✅ Verify CallRail → CRM lead creation with source tag

Week 4 — Automation
  ✅ Build Zapier/Make automation: CRM "Booked" → push referral tag to Dentrix
  ✅ Verify tag is appearing in Dentrix appointment records
  ✅ Run test: submit form → check CRM → check Dentrix → check Delta table

Week 5 — NexoBI connection
  ✅ Add "Organic Search" rows to Delta table from CRM + Dentrix ETL
  ✅ Add GSC data pull to ETL pipeline
  ✅ Verify AI Agent can answer: "What's our organic ROAS?"
```

---

### Sales Talking Points — Organic Attribution Case

> *"Every agency tells you organic search is working because your rankings went up and traffic went up. But can they tell you how many attended appointments came from organic search last quarter? And what the revenue was? With NexoBI's attribution bridge — a first-party cookie that carries session data from the website click through the form, through the CRM, and into the EHR as a referral source tag — you get a clean organic attribution thread for the first time. Rankings become revenue numbers."*

> *"And here's the compliance piece: none of that attribution data is PHI. UTMs, landing pages, referral source tags — these describe where someone came from, not who they are. The PHI stays locked in the EHR. The marketing data flows to NexoBI. There's a clear wall between the two, and NexoBI is designed around that wall."*

> *"The agencies that crack this first will have a significant edge. Right now most dental practices have zero visibility into organic attribution below the traffic level. Being able to show a practice owner 'your implants blog post generated $38,000 in production last quarter' is a completely different conversation than showing them a graph of keyword rankings."*

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Case 13 added (Organic → EHR Full-Funnel Attribution)*

---

---

## 14. Software Integration Samples — Platform-by-Platform Connection Guide

> **Purpose:** Concrete, practical integration examples for each software category — showing exactly how data flows from each tool into NexoBI, what connection method is used, and what a real API/automation call looks like.

---

### 14.1 Practice Management & EHR Systems

---

#### Dentrix G-Series → NexoBI
**Connection method:** Nightly CSV export + Python ETL

```python
# dentrix_etl.py — runs nightly via cron at 2:00 AM
import pandas as pd
import re
from datetime import date

def load_dentrix_production(csv_path: str) -> pd.DataFrame:
    """
    Reads Dentrix nightly Production Summary CSV.
    Strips PHI columns. Returns de-identified aggregate rows.
    """
    df = pd.read_csv(csv_path)

    # --- DROP all PHI columns immediately ---
    phi_cols = ["PatientName", "PatientFirstName", "PatientLastName",
                "DateOfBirth", "SSN", "InsuranceCarrier", "DiagnosisCode",
                "ProviderNotes", "ChartNumber", "PatientID"]
    df = df.drop(columns=[c for c in phi_cols if c in df.columns])

    # --- Normalize referral source to NexoBI picklist ---
    source_map = {
        "google ads":          "Google Ads",
        "google - paid":       "Google Ads",
        "meta":                "Facebook",
        "facebook":            "Facebook",
        "organic":             "Organic Search",
        "organic – blog":      "Organic Search",
        "website":             "Organic Search",
        "google maps":         "Google Business Profile",
        "gbp":                 "Google Business Profile",
        "patient referral":    "Referral – Patient",
        "email":               "Email – Reactivation",
    }
    df["data_source"] = (
        df["ReferralSource"]
        .str.lower().str.strip()
        .map(lambda s: next((v for k, v in source_map.items() if k in s), "Other"))
    )

    # --- Aggregate: group by date + source (no individual patient rows) ---
    df["date"] = pd.to_datetime(df["AppointmentDate"]).dt.date
    df["attended"] = (df["AppointmentStatus"] == "Complete").astype(int)
    df["booked"]   = 1

    agg = df.groupby(["date", "data_source"]).agg(
        total_revenue = ("NetProduction", "sum"),
        booked        = ("booked", "sum"),
        attended      = ("attended", "sum"),
    ).reset_index()

    agg["channel_group"] = agg["data_source"].map({
        "Google Ads": "Paid Search",
        "Facebook":   "Paid Social",
    }).fillna("Organic")

    return agg

# Load and push to Databricks Delta
df = load_dentrix_production("/exports/dentrix/production_summary_2026-02-27.csv")
# → MERGE INTO workspace.silver.DemoData-marketing-crm
```

---

#### athenahealth → NexoBI
**Connection method:** REST API (athenaPractice API)

```python
import requests

ATHENA_BASE    = "https://api.athenahealth.com/v1/{practice_id}"
ATHENA_TOKEN   = "Bearer <oauth2_access_token>"   # OAuth2 PKCE flow

def fetch_appointments(start_date: str, end_date: str) -> list:
    """Pull appointments with referral source. No PHI fields requested."""
    resp = requests.get(
        f"{ATHENA_BASE}/appointments",
        headers={"Authorization": ATHENA_TOKEN},
        params={
            "startdate":         start_date,   # "02/01/2026"
            "enddate":           end_date,
            "appointmentstatus": "x",           # x = checked out / completed
            "fields":            "appointmentdate,departmentid,"
                                 "appointmentstatus,charges,"
                                 "referralsourceid"
                                 # ← NO patientid, NO name, NO DOB requested
        }
    )
    return resp.json().get("appointments", [])

# Map referralsourceid to human-readable source
# athenahealth uses numeric IDs — map to your standardized picklist
REFERRAL_MAP = {
    "101": "Google Ads",
    "102": "Organic Search",
    "103": "Google Business Profile",
    "104": "Facebook",
    "105": "Referral – Patient",
    "199": "Other",
}
```

---

#### Open Dental → NexoBI
**Connection method:** MySQL direct read (on-premise, inside practice network)

```python
import pymysql
import pandas as pd

# Connection to Open Dental MySQL — runs INSIDE the practice's local network
conn = pymysql.connect(
    host="localhost",    # or practice server IP
    user="nexobi_ro",   # read-only DB user (never write access)
    password="<pw>",
    database="opendental"
)

query = """
    SELECT
        DATE(a.AptDateTime)          AS date,
        rs.Description               AS referral_source,
        COUNT(*)                     AS booked,
        SUM(CASE WHEN a.AptStatus = 2 THEN 1 ELSE 0 END) AS attended,
        SUM(pl.ProcFee)              AS total_revenue
    FROM appointment a
    JOIN procedurelog pl ON pl.AptNum = a.AptNum
    LEFT JOIN referral r ON r.ReferralNum = a.ReferralNum
    LEFT JOIN definition rs ON rs.DefNum = r.ReferralType
    -- NO PHI selected: no PatNum, no LName, no FName, no Birthdate
    WHERE DATE(a.AptDateTime) = CURDATE() - INTERVAL 1 DAY
    GROUP BY DATE(a.AptDateTime), rs.Description
"""
df = pd.read_sql(query, conn)
conn.close()
# → normalize + MERGE INTO Delta table
```

---

### 14.2 CRM Systems

---

#### GoHighLevel (GHL) → NexoBI
**Connection method:** REST API + Webhook

```python
import requests

GHL_API_KEY = "<your_ghl_api_key>"
GHL_BASE    = "https://rest.gohighlevel.com/v1"

def fetch_ghl_contacts(start_date: str, end_date: str) -> list:
    """Pull contacts created in date range with UTM/attribution data."""
    contacts = []
    page = 1
    while True:
        resp = requests.get(
            f"{GHL_BASE}/contacts/",
            headers={"Authorization": f"Bearer {GHL_API_KEY}"},
            params={
                "startAfter": start_date,
                "startAfterId": "",
                "limit": 100,
                "page": page,
            }
        )
        data = resp.json().get("contacts", [])
        if not data:
            break
        contacts.extend(data)
        page += 1
    return contacts

def map_contact_to_nexobi_row(contact: dict) -> dict:
    """Extract only attribution data — no PII sent to NexoBI."""
    custom = {f["id"]: f["value"] for f in contact.get("customField", [])}
    return {
        "date":          contact.get("dateAdded", "")[:10],
        "data_source":   custom.get("utm_source", "Direct"),
        "channel_group": custom.get("utm_medium", "Unknown"),
        "campaign":      custom.get("utm_campaign", custom.get("landing_page", "")),
        "leads":         1,
        "booked":        1 if contact.get("stage") in ["Booked", "Attended", "Won"] else 0,
        "attended":      1 if contact.get("stage") in ["Attended", "Won"] else 0,
        "total_revenue": float(contact.get("monetaryValue", 0) or 0),
        # PII fields (name, email, phone) — NOT included in this output
    }

# GHL Webhook — real-time push on pipeline stage change
# Configure in GHL: Settings → Integrations → Webhooks
# Event: "Contact Stage Changed"
# URL: https://your-etl-server.com/webhooks/ghl
# Payload includes: contactId, stage, customFields (UTMs)
```

---

#### HubSpot → NexoBI
**Connection method:** REST API (HubSpot v3)

```python
import requests

HS_TOKEN = "<hubspot_private_app_token>"
HS_BASE  = "https://api.hubapi.com"

def fetch_hubspot_contacts(after_date: str) -> list:
    """Pull contacts with UTM properties. No PII sent to NexoBI."""
    resp = requests.post(
        f"{HS_BASE}/crm/v3/objects/contacts/search",
        headers={"Authorization": f"Bearer {HS_TOKEN}"},
        json={
            "filterGroups": [{
                "filters": [{
                    "propertyName": "createdate",
                    "operator": "GTE",
                    "value": after_date   # Unix timestamp ms
                }]
            }],
            "properties": [
                # Attribution fields only — NOT firstname, lastname, email, phone
                "hs_analytics_source",         # "ORGANIC_SEARCH"
                "hs_analytics_source_data_1",  # source / medium detail
                "hs_analytics_first_url",      # landing page
                "hs_analytics_last_url",       # last page before convert
                "hs_latest_source_timestamp",
                "lifecyclestage",              # lead, opportunity, customer
                "hs_deal_stage",
                "amount",                      # deal revenue
            ],
            "limit": 100
        }
    )
    return resp.json().get("results", [])

# HubSpot → NexoBI source mapping
HS_SOURCE_MAP = {
    "ORGANIC_SEARCH":     "Organic Search",
    "PAID_SEARCH":        "Google Ads",
    "SOCIAL_MEDIA":       "Facebook",
    "PAID_SOCIAL":        "Facebook",
    "EMAIL_MARKETING":    "Email – Reactivation",
    "REFERRALS":          "Referral – Patient",
    "DIRECT_TRAFFIC":     "Direct",
    "OTHER_CAMPAIGNS":    "Other",
}
```

---

### 14.3 Paid Media Platforms

---

#### Google Ads → NexoBI
**Connection method:** Google Ads API (GAQL)

```python
from google.ads.googleads.client import GoogleAdsClient

client = GoogleAdsClient.load_from_env()

def fetch_google_ads_stats(customer_id: str, start: str, end: str) -> list:
    service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            segments.date,
            campaign.name,
            metrics.cost_micros,
            metrics.conversions,
            metrics.impressions,
            metrics.clicks,
            metrics.all_conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status = 'ENABLED'
    """
    response = service.search(customer_id=customer_id, query=query)
    rows = []
    for row in response:
        rows.append({
            "date":          row.segments.date,
            "data_source":   "Google Ads",
            "channel_group": "Paid Search",
            "campaign":      row.campaign.name,
            "total_cost":    row.metrics.cost_micros / 1_000_000,
            "total_revenue": row.metrics.all_conversions_value,
            "clicks":        row.metrics.clicks,
            "impressions":   row.metrics.impressions,
            "conversions":   int(row.metrics.conversions),
        })
    return rows
```

---

#### Meta Ads → NexoBI
**Connection method:** Meta Marketing API

```python
import requests

META_TOKEN   = "<meta_system_user_token>"
META_AD_ACCT = "act_<your_account_id>"

def fetch_meta_insights(start: str, end: str) -> list:
    resp = requests.get(
        f"https://graph.facebook.com/v18.0/{META_AD_ACCT}/insights",
        params={
            "access_token": META_TOKEN,
            "level":        "campaign",
            "fields":       "campaign_name,spend,impressions,clicks,"
                            "actions,action_values,date_start",
            "time_range":   f'{{"since":"{start}","until":"{end}"}}',
            "time_increment": 1,   # daily
        }
    )
    rows = []
    for item in resp.json().get("data", []):
        # Extract lead form submissions from actions array
        leads = next(
            (int(a["value"]) for a in item.get("actions", [])
             if a["action_type"] == "lead"),
            0
        )
        revenue = next(
            (float(a["value"]) for a in item.get("action_values", [])
             if a["action_type"] == "offsite_conversion.fb_pixel_purchase"),
            0.0
        )
        rows.append({
            "date":          item["date_start"],
            "data_source":   "Facebook",
            "channel_group": "Paid Social",
            "campaign":      item["campaign_name"],
            "total_cost":    float(item.get("spend", 0)),
            "impressions":   int(item.get("impressions", 0)),
            "clicks":        int(item.get("clicks", 0)),
            "leads":         leads,
            "total_revenue": revenue,
        })
    return rows
```

---

### 14.4 SEO & Organic Search Tools

---

#### Google Search Console → NexoBI
**Connection method:** GSC Data API v3

```python
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

def fetch_gsc_data(site_url: str, start: str, end: str) -> list:
    creds   = Credentials.from_service_account_file("gsc_service_account.json",
                  scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    service = build("searchconsole", "v1", credentials=creds)

    body = {
        "startDate":  start,          # "2026-01-01"
        "endDate":    end,            # "2026-01-31"
        "dimensions": ["date", "page", "query"],
        "rowLimit":   25000,
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "country",
                "operator":  "equals",
                "expression": "usa"
            }]
        }]
    }
    resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()

    rows = []
    for row in resp.get("rows", []):
        date, page, query = row["keys"]
        rows.append({
            "date":        date,
            "page":        page,
            "query":       query,
            "clicks":      row["clicks"],
            "impressions": row["impressions"],
            "ctr":         round(row["ctr"] * 100, 2),
            "position":    round(row["position"], 1),
        })
    return rows
# → stored in supplementary Delta table: workspace.silver.gsc_organic_performance
# → joined to main table by date + landing_page to link clicks to booked revenue
```

---

#### SEMrush → NexoBI
**Connection method:** SEMrush API (keyword rank tracking)

```python
import requests

SEMRUSH_KEY = "<your_semrush_api_key>"

def fetch_semrush_rankings(domain: str, keywords: list) -> list:
    """Pull current keyword positions for target keyword list."""
    rows = []
    for kw in keywords:
        resp = requests.get(
            "https://api.semrush.com/",
            params={
                "type":      "phrase_organic",
                "key":       SEMRUSH_KEY,
                "phrase":    kw,
                "database":  "us",
                "domain":    domain,
                "display_columns": "Ph,Po,Nq,Cp",  # keyword, position, volume, CPC
                "export_columns": "Ph,Po,Nq,Cp",
            }
        )
        # Parse CSV response
        lines = resp.text.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split(";")
            rows.append({
                "keyword":       parts[0],
                "position":      int(parts[1]) if parts[1].isdigit() else 99,
                "search_volume": int(parts[2]) if parts[2].isdigit() else 0,
                "cpc":           float(parts[3]) if parts[3] else 0.0,
                "domain":        domain,
            })
    return rows
# → stored in supplementary table: workspace.silver.semrush_rankings
# → joined to gsc_organic_performance and main table by keyword/page
# → enables: "position 3 for 'implants miami' → 34 clicks → 1 lead → $6,200 revenue"
```

---

#### BrightLocal → NexoBI
**Connection method:** BrightLocal API (Local Search Grid + GBP)

```python
import requests

BL_KEY  = "<brightlocal_api_key>"
BL_BASE = "https://tools.brightlocal.com/seo-tools/api/v4"

def fetch_brightlocal_rankings(campaign_id: str) -> list:
    """Pull local pack rankings and GBP performance for a campaign."""
    resp = requests.get(
        f"{BL_BASE}/rankings/get-campaign-rankings",
        params={
            "api-key":     BL_KEY,
            "campaign-id": campaign_id,
        }
    )
    data = resp.json()
    rows = []
    for kw_data in data.get("keywords", []):
        rows.append({
            "keyword":         kw_data["keyword"],
            "local_pack_rank": kw_data.get("local_pack_rank", 99),
            "organic_rank":    kw_data.get("organic_rank", 99),
            "gbp_views":       kw_data.get("gbp_views", 0),
            "gbp_calls":       kw_data.get("gbp_calls", 0),
            "gbp_direction":   kw_data.get("direction_requests", 0),
            "date":            kw_data.get("report_date"),
        })
    return rows
# → stored in workspace.silver.brightlocal_local_seo
# → powers NexoBI: "Local pack rank 2 → 47 GBP calls → 8 booked appointments"
```

---

### 14.5 Patient Communication & Engagement

---

#### CallRail → NexoBI
**Connection method:** CallRail API v3

```python
import requests

CR_KEY  = "<callrail_api_key>"
CR_ACCT = "<callrail_account_id>"

def fetch_callrail_calls(start: str, end: str) -> list:
    """Pull call data with UTM source attribution. No patient names."""
    resp = requests.get(
        f"https://api.callrail.com/v3/a/{CR_ACCT}/calls.json",
        headers={"Authorization": f"Token token={CR_KEY}"},
        params={
            "start_date":  start,
            "end_date":    end,
            "fields":      "start_time,tracking_source,utm_source,"
                           "utm_medium,utm_campaign,utm_term,"
                           "landing_page_url,answered,duration",
            # ← NOT requesting: caller_name, caller_number (PII)
        }
    )
    rows = []
    for call in resp.json().get("calls", []):
        rows.append({
            "date":          call["start_time"][:10],
            "data_source":   call.get("utm_source", call.get("tracking_source", "Unknown")),
            "channel_group": call.get("utm_medium", "Unknown"),
            "campaign":      call.get("utm_campaign", call.get("landing_page_url", "")),
            "leads":         1,
            "answered":      1 if call.get("answered") else 0,
            # duration > 90 sec = qualified lead (common threshold)
            "qualified":     1 if int(call.get("duration", 0)) > 90 else 0,
        })
    return rows
```

---

#### Weave → NexoBI
**Connection method:** Weave API (appointment reminders + show rate signals)

```python
import requests

WEAVE_TOKEN = "<weave_api_token>"

def fetch_weave_reminders(start: str, end: str) -> list:
    """Pull reminder send/confirm data to correlate with show rate."""
    resp = requests.get(
        "https://api.getweave.com/messaging/reminders",
        headers={"Authorization": f"Bearer {WEAVE_TOKEN}"},
        params={"start": start, "end": end}
    )
    rows = []
    for r in resp.json().get("reminders", []):
        rows.append({
            "date":             r["appointment_date"][:10],
            "reminder_channel": r["channel"],       # "sms" or "email"
            "sent":             1,
            "delivered":        1 if r["status"] == "delivered" else 0,
            "confirmed":        1 if r["status"] == "confirmed" else 0,
            # No patient name — appointment_id only
        })
    return rows
# → stored in supplementary table: workspace.silver.weave_reminders
# → enables: "SMS-confirmed patients show at 91% vs email-only 71%"
```

---

### 14.6 Automation / Middleware Layer

---

#### Zapier — CRM Stage → Dentrix Referral Source
**What it does:** When a contact moves to "Booked" stage in GoHighLevel, automatically push the referral source tag to the Dentrix appointment.

```
Trigger:  GoHighLevel — Contact Stage Changed
          Filter: New Stage = "Booked"

Action:   Formatter — Text
          Input:  {{contact.utm_source}} + " – " + {{contact.utm_campaign}}
          Output: "google – /blog/dental-implant-cost-guide"

Action:   Dentrix (via HTTP POST to Dentrix Ascend API, or via email-to-Dentrix)
          Referral Source: {{formatted_source}}
          Appointment Date: {{contact.appointmentDate}}
          Patient ID lookup: by phone match
```

---

#### Make (Integromat) — Full Attribution Pipeline

```
Scenario: "Nightly Attribution Sync"
Schedule: Every day at 1:00 AM

Module 1:  Google Ads → fetch yesterday's campaign stats
Module 2:  Meta Ads → fetch yesterday's campaign stats
Module 3:  GoHighLevel → fetch contacts created yesterday
Module 4:  CallRail → fetch calls from yesterday
Module 5:  Dentrix CSV watcher → detect new export file
Module 6:  Iterator → process each source
Module 7:  Data Store → deduplicate by date + source + campaign
Module 8:  HTTP Request → POST de-identified rows to Databricks REST API
           POST https://<databricks_host>/api/2.0/sql/statements
           Body: { "statement": "MERGE INTO workspace.silver.DemoData-marketing-crm ..." }
Module 9:  Slack notification → "Nightly sync complete: 847 rows updated"
```

---

### 14.7 Full Software Stack — Quick Reference

| Category | Tool | Connection | NexoBI data contributed | HIPAA-safe? |
|---|---|---|---|---|
| **Practice Mgmt** | Dentrix G-Series | CSV export + Python | booked, attended, revenue, referral_source | ✅ (de-identified) |
| **Practice Mgmt** | Dentrix Ascend | REST API | Same as above | ✅ (de-identified) |
| **EHR** | athenahealth | REST API (OAuth2) | booked, attended, revenue | ✅ (no PHI fields requested) |
| **EHR** | Open Dental | MySQL read-only | booked, attended, revenue | ✅ (inside local network) |
| **EHR** | Eaglesoft | ODBC + CSV | booked, attended, revenue | ✅ (de-identified) |
| **CRM** | GoHighLevel | REST API + Webhook | leads, booked, attended, revenue, UTMs | ✅ (no PII to NexoBI) |
| **CRM** | HubSpot | REST API v3 | leads, booked, revenue, source | ✅ (no PII to NexoBI) |
| **Paid Search** | Google Ads | Google Ads API (GAQL) | spend, clicks, impressions, leads | ✅ (no PHI) |
| **Paid Social** | Meta Ads | Marketing API v18 | spend, impressions, leads | ✅ (no PHI) |
| **Analytics** | GA4 | Data API v1 | sessions, new_users, conversions | ✅ (no PHI) |
| **SEO** | Google Search Console | Search Console API v3 | clicks, impressions, position, query | ✅ (aggregate, no PHI) |
| **SEO** | SEMrush | SEMrush API | keyword rankings, volume | ✅ (no PHI) |
| **Local SEO** | BrightLocal | BrightLocal API | local pack rank, GBP calls | ✅ (no PHI) |
| **Call Tracking** | CallRail | CallRail API v3 | calls, answered, source, landing page | ✅ (no caller PII) |
| **Communication** | Weave | Weave API | reminder delivery, confirmation rate | ✅ (no PHI) |
| **Communication** | Podium | Podium API | review score, review count | ✅ (no PHI) |
| **Attribution pixel** | Server-side (custom) | Python function → Google Enhanced Conv. + Meta CAPI | hashed email/phone for match only | ✅ (SHA-256 hash, no PHI) |
| **Automation** | Zapier | Webhook triggers | Referral source tag to Dentrix | ✅ (source tag only) |
| **Automation** | Make / Integromat | Scheduled scenario | Nightly multi-source aggregation | ✅ (de-identified) |
| **Data warehouse** | Databricks | Delta Lake REST API | All NexoBI data | ✅ (marketing layer, no PHI) |

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 14 added (Software Integration Samples)*

---

---

## 15. SEO / Organic Search — Real-World Integration Scenarios

> These are the problems healthcare marketing agencies run into every week. All tools listed are widely available, actively maintained, and in common use. No exotic stacks, no custom infrastructure required beyond what most practices already have or can get in a day.

---

### 15.1 Google Business Profile (GBP) — The #1 Undertracked Source

**The real problem:**
A dental practice gets 40–60% of its organic leads from Google Maps / the local 3-pack. Patients search "dentist near me," see the practice in the map, and tap "Call" or "Website." In GA4, those visits show up as **direct traffic** — zero attribution. The practice thinks direct traffic is people typing the URL. It's actually their most valuable organic channel, invisible.

**Tools:** Google Business Profile (free) · CallRail · GA4 · NexoBI

**The fix — two changes, 30 minutes of work:**

**Fix 1 — UTM on the GBP website button:**
```
In Google Business Profile dashboard:
  Edit Profile → Contact → Website URL

Change from:
  https://miamidentalcenter.com

Change to:
  https://miamidentalcenter.com?utm_source=google&utm_medium=gmb&utm_campaign=local_pack&utm_content=website_button

Result: Every GBP website click now shows as
  source=google / medium=gmb in GA4 and NexoBI
  instead of "direct"
```

**Fix 2 — Dedicated CallRail number on GBP listing:**
```
In CallRail:
  Create tracking number pool: "Google Business Profile"
  Source: google / gbp
  Medium: gmb
  Assign one static number to this pool

In GBP:
  Edit Profile → Contact → Phone number
  Replace with the CallRail tracking number

Result: Every "Call" tap from Google Maps is captured
  with source=google, medium=gmb
  Caller identity NOT captured — only call count + answered/missed
```

**What NexoBI sees after this fix:**

Before:
```
data_source = "Direct"     → 47 sessions, 0 leads attributed, $0 revenue
```

After:
```
data_source = "Google Business Profile"
channel_group = "Local / Maps"
sessions = 47
leads = 31   (calls via CallRail + form fills via UTM)
booked = 22
attended = 19
total_revenue = $68,400
```

**NexoBI AI answer:**
> *"Google Business Profile is your highest-volume organic channel — 31 leads last month vs 18 from organic search results. GBP show rate: 86%. Revenue attributed: $68,400. This was previously invisible as 'Direct' traffic."*

**Why this matters in a sales conversation:**
> *"Right now your GA4 shows 'direct' as your top channel. That's not people typing your URL — that's your Google Maps listing. We know because the moment we put a UTM on your GBP website button, 'direct' dropped 40% and 'Google Business Profile' appeared at $68,000 in monthly revenue. That channel existed. You just couldn't see it."*

---

### 15.2 Organic Content ROI — Which Blog Posts Actually Convert?

**The real problem:**
A practice pays $1,500–$3,000/month to a content agency. They produce blog posts about implants, Invisalign, whitening. Traffic goes up. Rankings improve. But does any of it generate patients? Nobody knows. The content agency reports on keyword rankings. The front desk doesn't know what brought each patient in. The result: practices either overspend on content that doesn't convert, or cut content budgets that are actually working.

**Tools:** Google Search Console · GA4 · GoHighLevel or HubSpot CRM · NexoBI

**The attribution chain:**

```
Blog post ranks for "dental implants cost miami" (position 3)
    ↓ 34 organic clicks this month (GSC)
    ↓ 27 sessions land on /blog/dental-implant-cost-guide (GA4)
    ↓ 4 form submissions from that page (GA4 form_submit event)
    ↓ 4 leads in CRM with landing_page = /blog/dental-implant-cost-guide (GHL)
    ↓ 3 booked appointments (CRM stage = Booked)
    ↓ 3 attended (Dentrix: status = Complete, referral = "Organic – Blog")
    ↓ $17,400 production (Dentrix)
    ↓ NexoBI Delta row:
       campaign = "/blog/dental-implant-cost-guide"
       data_source = "Organic Search"
       leads=4, booked=3, attended=3, total_revenue=$17,400
```

**The content ROI table NexoBI generates:**

| Landing Page | GSC Clicks | Leads | Booked | Attended | Revenue | Rev/Click |
|---|---|---|---|---|---|---|
| /blog/dental-implant-cost-guide | 34 | 4 | 3 | 3 | $17,400 | $512 |
| /services/invisalign | 89 | 6 | 5 | 4 | $14,800 | $166 |
| /blog/how-long-do-implants-last | 61 | 1 | 1 | 0 | $0 | $0 |
| /services/teeth-whitening | 203 | 3 | 2 | 2 | $960 | $5 |
| /blog/implant-vs-bridge | 28 | 3 | 3 | 3 | $16,200 | $579 |

**The insight this surfaces:**
- `/blog/implant-vs-bridge` has 28 clicks but $579 revenue per click — the best-performing piece of content
- `/services/teeth-whitening` has 203 clicks (most traffic) but only $5 revenue per click — traffic that doesn't convert
- `/blog/how-long-do-implants-last` — 61 clicks, zero revenue, likely an awareness piece with no CTA

**NexoBI AI answer to "What content should we invest in?":**
> *"Your highest-revenue organic pages are comparison/decision-stage content — implant vs bridge, implant cost guide. These earn $500–$580 per organic click. Whitening content earns $5/click. For your next 3 content pieces, target decision-stage implant queries: 'implant vs dentures cost', 'same day implants miami', 'dental implant financing options'."*

**What NexoBI needs to make this work:**
1. GSC API pulling clicks + position by landing page (daily)
2. CRM capturing `landing_page` from the attribution cookie on form submit
3. Dentrix referral source = "Organic – Blog" (standardized picklist)
4. ETL joining GSC table to main Delta table on `date + landing_page`

---

### 15.3 Rank Drop → Revenue Alert (Before the Agency Calls You)

**The real problem:**
A service page drops from position 3 to position 14 after a Google algorithm update, a competitor SEO push, or a technical issue (page indexed incorrectly, canonical tag wrong). Traffic drops. Leads drop. Two weeks later the practice owner asks why revenue is down. Nobody connected those dots.

**Tools:** Google Search Console · SEMrush (or Ahrefs) · NexoBI

**How NexoBI detects and surfaces this:**

```python
# Weekly rank-drop detection — runs in ETL on Mondays
def detect_rank_drops(gsc_this_week: pd.DataFrame,
                      gsc_last_week: pd.DataFrame,
                      revenue_by_page: pd.DataFrame) -> list:
    alerts = []
    merged = gsc_this_week.merge(
        gsc_last_week, on=["page","query"], suffixes=("_now","_prev")
    )
    merged["pos_change"] = merged["position_now"] - merged["position_prev"]

    # Flag: dropped more than 5 positions AND was previously in top 10
    drops = merged[
        (merged["pos_change"] > 5) &
        (merged["position_prev"] <= 10)
    ].copy()

    for _, row in drops.iterrows():
        # Join to revenue table — how much revenue does this page drive?
        rev = revenue_by_page.get(row["page"], 0)
        weekly_rev_at_risk = rev / 4   # monthly / 4 weeks

        alerts.append({
            "page":              row["page"],
            "query":             row["query"],
            "position_was":      row["position_prev"],
            "position_now":      row["position_now"],
            "clicks_lost_est":   int(row["clicks_prev"] - row["clicks_now"]),
            "revenue_at_risk":   weekly_rev_at_risk,
            "alert_type":        "rank_drop",
        })
    return sorted(alerts, key=lambda x: -x["revenue_at_risk"])
```

**What NexoBI's Top Signals card shows:**

```
⚠ RANK DROP — /services/dental-implants
  Position dropped: 3 → 14 (week over week)
  Estimated clicks lost: 18/week
  Revenue at risk: ~$9,200/month based on historical conversion
  Possible causes: algorithm update, page speed, competitor content
  Recommended: Check GSC Coverage report + run Screaming Frog crawl
```

**The revenue impact formula:**
```
Revenue at risk =
  (clicks at position 3 - clicks at position 14)
  × page conversion rate (leads/clicks from CRM)
  × booking rate (booked/leads from CRM)
  × show rate (attended/booked from Dentrix)
  × avg production per patient (from Dentrix)

Example:
  Lost clicks: 18/week = 72/month
  × CVR: 11.8% = 8.5 leads
  × booking rate: 75% = 6.4 booked
  × show rate: 86% = 5.5 attended
  × avg production: $4,200
  = $23,100/month in lost pipeline
```

**Why this is a game-changer for agencies:**
> *"Your client doesn't know their implants page dropped out of the top 10 last Tuesday. You don't know either — until you pull the GSC report on Friday. NexoBI runs that check every Monday morning and puts it in the Top Signals card with the dollar amount. The agency gets an alert before the client asks. That changes the relationship."*

---

### 15.4 Google Business Profile Reviews → Local Rank → Revenue Cycle

**The real problem:**
Review count and recency are confirmed local ranking factors for Google Maps. Practices with more recent reviews rank higher in the local 3-pack. Higher local rank = more impressions = more calls and website clicks = more patients. But most practices don't have a systematic review generation process, and the connection between reviews and revenue is never quantified.

**Tools:** Google Business Profile · Podium or Birdeye (both widely used) · BrightLocal or SEMrush Local · NexoBI

**The full cycle:**

```
Patient attends appointment → marked "Complete" in Dentrix
    ↓
Automated trigger (Podium/Birdeye → Dentrix integration):
  SMS sent to patient: "How was your visit? Leave us a Google review →"
  Sent 2 hours post-appointment
    ↓
Patient leaves review
  → Google review count: 127 → 128
  → Review recency: last review = today
    ↓
BrightLocal weekly rank check:
  "dentist miami" local pack position: 4 → 3
    ↓
GBP impressions (next 30 days):
  Local pack impressions: +340/month
  Website button clicks: +22/month
  Call button taps: +18/month
    ↓
CallRail (GBP tracking number):
  18 additional calls captured
  Leads in CRM: +14 (qualified calls > 90 sec)
    ↓
Dentrix booked: +11 appointments
Attended: +9
Production: +$31,500 this month
```

**The NexoBI correlation query:**

```sql
-- Join review count trend to GBP lead volume trend
-- to quantify the review → revenue relationship

SELECT
  r.week,
  r.review_count,
  r.avg_rating,
  g.gbp_clicks,
  g.gbp_calls,
  m.leads,
  m.attended,
  m.total_revenue
FROM weekly_reviews r
JOIN weekly_gbp_stats g ON r.week = g.week
JOIN (
  SELECT
    DATE_TRUNC('week', date) AS week,
    SUM(leads)    AS leads,
    SUM(attended) AS attended,
    SUM(total_revenue) AS total_revenue
  FROM silver.`DemoData-marketing-crm`
  WHERE data_source = 'Google Business Profile'
  GROUP BY 1
) m ON r.week = m.week
ORDER BY r.week
```

**What the data shows (typical dental practice):**

| Month | Reviews (total) | Avg Rating | Local Pack Rank | GBP Calls | Leads | Revenue |
|---|---|---|---|---|---|---|
| Oct | 89 | 4.7 | 4 | 28 | 21 | $44,100 |
| Nov | 94 | 4.7 | 4 | 31 | 23 | $49,800 |
| Dec | 112 | 4.8 | 2 | 47 | 38 | $79,200 |
| Jan | 118 | 4.8 | 2 | 44 | 35 | $73,500 |
| Feb | 127 | 4.8 | 2 | 51 | 41 | $86,100 |

**The inflection point:** Between October and December, the practice jumped from rank 4 to rank 2 in the local pack. GBP calls went from 28 to 47 — a 68% increase. Revenue from GBP nearly doubled from $44K to $79K.

**NexoBI AI answer:**
> *"Local pack rank improved from 4 to 2 in December after review count crossed 100. Since that improvement, GBP calls are up 68% and attributed revenue from Google Business Profile is up 95% — from $44,100 to $86,100/month. Each additional Google review is worth an estimated $1,240 in incremental monthly revenue at current conversion rates."*

**This is the talking point that makes review generation a revenue conversation, not a reputation conversation.**

---

### 15.5 Directory & Citation Traffic — Healthgrades, Zocdoc, Yelp, WebMD

**The real problem:**
Healthcare practices are listed on 40–80 online directories. Healthgrades, Zocdoc, Yelp, WebMD, Vitals, RateMDs, US News Health, Castle Connolly. Patients click through from these directories to the practice website. In GA4, this shows up as referral traffic — or worse, as direct if the directory strips referrer headers. Are these directories worth the listing fees? Nobody knows.

**Tools:** Yext (listing management) · GA4 · CRM · NexoBI

**The fix:**
Add UTM parameters to the website link on every directory listing. Yext manages all listings centrally — one update pushes to all 70+ directories.

```
Yext Publisher Network — set website URL with UTMs per directory type:

Healthgrades:   ?utm_source=healthgrades&utm_medium=directory&utm_campaign=listing
Zocdoc:         ?utm_source=zocdoc&utm_medium=directory&utm_campaign=booking
Yelp:           ?utm_source=yelp&utm_medium=directory&utm_campaign=listing
WebMD:          ?utm_source=webmd&utm_medium=directory&utm_campaign=listing
Vitals:         ?utm_source=vitals&utm_medium=directory&utm_campaign=listing

→ Each directory now appears as a distinct source in NexoBI
→ Instead of "referral / unknown" you see "healthgrades / directory"
```

**What NexoBI shows after UTMs are in place:**

| Directory | Sessions | Leads | Booked | Revenue | Listing Cost/mo |
|---|---|---|---|---|---|
| Zocdoc | 89 | 34 | 28 | $67,200 | $400 |
| Healthgrades | 44 | 8 | 6 | $14,400 | $200 |
| Yelp | 67 | 4 | 2 | $4,800 | $300 |
| WebMD | 31 | 2 | 1 | $2,400 | $150 |
| Vitals | 18 | 0 | 0 | $0 | $100 |

**The business decisions this enables:**
- Zocdoc at $400/mo generating $67,200 in revenue → 168x ROAS — double down
- Yelp at $300/mo generating $4,800 → 16x ROAS — borderline, watch it
- Vitals at $100/mo generating $0 → cancel immediately
- Healthgrades converting at 18% lead rate → higher than paid search → scale the profile

**Yext integration to NexoBI:**

```python
# Yext doesn't export conversion data directly
# The UTMs on Yext-managed links flow through GA4 → CRM → NexoBI
# Yext's value in this stack: ensures UTM links are consistent
# across all 70+ directories without manual updates

# Supplementary: Yext Listings API for citation health score
import requests

YEXT_KEY = "<yext_api_key>"

def fetch_yext_listing_status(account_id: str) -> list:
    resp = requests.get(
        f"https://api.yext.com/v2/accounts/{account_id}/powerlistings/publisherstatus",
        params={"api_key": YEXT_KEY, "v": "20230901"}
    )
    listings = resp.json().get("response", {}).get("publisherStatuses", [])
    # Returns: publisher name, status (Live/Pending/Error), last sync date
    return [
        {
            "publisher":   l["publisherName"],
            "status":      l["status"],
            "last_synced": l["lastSyncedDate"],
        }
        for l in listings
    ]
# → stored as metadata: which directories are live vs broken
# → broken listing = lost traffic source = revenue leak
```

---

### 15.6 Organic Conversion Rate by Landing Page — The Invisible CRO Problem

**The real problem:**
A practice ranks #1 for "dental implants miami" — great. But the landing page converts at 2.1% while a competitor's page (ranking #4) converts at 8.3%. The competitor gets fewer clicks but more leads. Ranking is only half the equation. Conversion rate on the organic landing page is the other half — and almost no agency tracks it at the page level tied to actual leads.

**Tools:** GA4 · GoHighLevel or HubSpot · Google Optimize (or VWO/AB Tasty) · NexoBI

**The measurement setup:**

```python
# GA4 → NexoBI: track sessions + form submits per landing page

# GA4 custom event — fire on form submission
# Add to the website's form submit handler:
gtag('event', 'organic_lead_form', {
  'landing_page':  window.__nexobi_attr?.landing_page || window.location.pathname,
  'source':        window.__nexobi_attr?.source || 'organic',
  'medium':        window.__nexobi_attr?.medium || 'organic',
});

# In GA4 → Explore:
# Dimension: Landing Page
# Filter: Session source = "google", Session medium = "organic"
# Metrics: Sessions, Form Submissions (organic_lead_form event count)
# Derived metric: CVR = form submissions / sessions × 100
```

**The page-level CVR table NexoBI surfaces:**

| Page | Organic Sessions | Leads | CVR | Booked | Revenue |
|---|---|---|---|---|---|
| /services/dental-implants | 312 | 7 | 2.2% | 5 | $21,000 |
| /blog/dental-implant-cost-guide | 89 | 11 | 12.4% | 9 | $37,800 |
| /services/invisalign | 201 | 6 | 3.0% | 5 | $14,000 |
| /blog/implant-vs-bridge | 44 | 7 | 15.9% | 6 | $25,200 |
| /services/dental-implants-miami | 178 | 3 | 1.7% | 2 | $8,400 |

**The insight:**
- `/services/dental-implants` is the main service page — 312 sessions, but only 2.2% CVR
- `/blog/dental-implant-cost-guide` is a blog post — 89 sessions, but 12.4% CVR
- The blog converts 5.6× better than the main service page, despite less traffic

**Why the blog converts better:** Decision-stage content (cost, comparisons, process explanations) captures patients further along in their research. They're not window shopping — they're deciding. The main service page is too generic; the blog answers the specific question they Googled.

**NexoBI AI answer:**
> *"Your /services/dental-implants page has the most organic traffic (312 sessions) but the worst conversion rate (2.2%). Your blog posts convert at 12–16%. Adding a clear cost estimate, a before/after gallery, and a FAQ section to the service page — the elements that make the blogs work — could increase conversions by 3–5x without gaining a single new ranking."*

**The CRO ROI model:**
```
Current: 312 sessions × 2.2% CVR = 6.9 leads/month
Improved: 312 sessions × 8.0% CVR = 24.9 leads/month
Delta: +18 leads/month
× booking rate 75% = +13.5 booked
× show rate 86%   = +11.6 attended
× avg production $4,200 = +$48,720/month from same organic traffic
```

---

### 15.7 Organic vs Paid — The Budget Allocation Question

**The real problem:**
A practice spends $8,000/month on Google Ads and $2,500/month on SEO. The Google Ads agency wants more budget. The SEO agency wants more budget. The practice owner has no idea which channel is actually more efficient. They make the decision based on whoever presents a better-looking report — not on actual revenue per dollar spent.

**Tools:** Google Ads (native) · Google Search Console · CRM · Dentrix · NexoBI

**What NexoBI computes (no extra tools needed — everything already connected):**

```python
# Monthly channel efficiency comparison
# All data already in the Delta table after standard integrations

query = """
SELECT
    CASE
        WHEN data_source IN ('Google Ads') THEN 'Paid Search'
        WHEN data_source IN ('Facebook', 'Instagram') THEN 'Paid Social'
        WHEN data_source = 'Organic Search' THEN 'Organic Search'
        WHEN data_source = 'Google Business Profile' THEN 'Local / Maps'
        WHEN data_source LIKE 'Email%' THEN 'Email'
        ELSE 'Other'
    END AS channel,
    SUM(total_cost)    AS spend,
    SUM(leads)         AS leads,
    SUM(booked)        AS booked,
    SUM(attended)      AS attended,
    SUM(total_revenue) AS revenue,
    ROUND(SUM(total_revenue) / NULLIF(SUM(total_cost), 0), 2) AS roas,
    ROUND(SUM(total_cost) / NULLIF(SUM(leads), 0), 2)         AS cost_per_lead,
    ROUND(SUM(attended) / NULLIF(SUM(booked), 0) * 100, 1)    AS show_rate_pct
FROM silver.`DemoData-marketing-crm`
WHERE date >= DATE_SUB(CURRENT_DATE, 30)
GROUP BY 1
ORDER BY revenue DESC
"""
```

**Sample output (what the practice actually looks like):**

| Channel | Spend | Leads | CPL | Attended | Revenue | ROAS | Show Rate |
|---|---|---|---|---|---|---|---|
| Organic Search | $2,500 | 41 | $61 | 34 | $142,800 | 57.1x | 88% |
| Local / Maps (GBP) | $0 | 38 | $0 | 31 | $108,500 | ∞ | 84% |
| Paid Search (Google Ads) | $8,000 | 52 | $154 | 38 | $118,400 | 14.8x | 75% |
| Paid Social (Meta) | $2,200 | 29 | $76 | 18 | $39,600 | 18.0x | 66% |
| Email | $180 | 11 | $16 | 10 | $34,200 | 190x | 92% |

**The insight NexoBI surfaces:**
- Organic Search + GBP together: $251,300 revenue on $2,500 spend = 100x ROAS
- Google Ads: $118,400 on $8,000 = 14.8x ROAS — still excellent, but 7x less efficient per dollar
- Organic show rate (88%) is meaningfully higher than paid (75%) — organic patients are more committed
- The SEO agency should get more budget. The practice owner had no data to know this.

**NexoBI AI answer:**
> *"Organic search and Google Business Profile together generate $251,300 in monthly revenue on $2,500 SEO spend — a combined effective ROAS of 100x. Paid search generates $118,400 on $8,000 — a ROAS of 14.8x. Both channels are profitable, but organic is 6.8x more efficient per dollar. Recommendation: increase SEO budget before scaling paid, particularly targeting decision-stage keywords where your blog content already converts at 12–16%."*

---

### 15.8 Screaming Frog + GSC — Technical SEO Issues Costing Revenue

**The real problem:**
A practice's `/services/dental-implants` page accidentally gets a `noindex` tag added during a website update. Or the canonical tag points to the wrong URL. Or the page loads in 8 seconds on mobile. Organic traffic drops 40% in two weeks. Nobody notices until the monthly report. By then, $30,000 in pipeline has evaporated.

**Tools:** Screaming Frog (free up to 500 URLs) · Google Search Console · NexoBI

**The NexoBI signal that triggers investigation:**

NexoBI's Top Signals card already shows rank drops (Section 15.3). The additional layer here is technical — *why* did the rank drop?

```
NexoBI Top Signal:
  ⚠ TRAFFIC DROP — /services/dental-implants
  Organic clicks: 89 → 12 (week over week, -87%)
  Revenue at risk: ~$28,000/month
  Possible cause: indexing issue or manual penalty
  Action: Run Screaming Frog crawl + check GSC Coverage report NOW
```

**Screaming Frog crawl → NexoBI integration:**
Screaming Frog exports a CSV. A lightweight Python script flags pages that are:
- `noindex` tagged but were previously indexed (revenue-generating pages)
- Returning 4xx / 5xx status codes
- Canonical pointing off-site or to wrong URL
- Redirect chains (3+ hops slow crawl + pass less link equity)
- Core Web Vitals fail: LCP > 4s, CLS > 0.25

```python
import pandas as pd

def flag_technical_issues(screaming_frog_csv: str,
                          revenue_by_page: dict) -> pd.DataFrame:
    df = pd.read_csv(screaming_frog_csv)

    issues = []
    for _, row in df.iterrows():
        url   = row.get("Address", "")
        path  = url.split(".com")[-1]   # extract path
        rev   = revenue_by_page.get(path, 0)

        if rev == 0:
            continue    # only flag pages that drive revenue

        flags = []
        if str(row.get("Indexability", "")).lower() == "non-indexable":
            flags.append("NOINDEX — page excluded from Google")
        if str(row.get("Status Code", "")) in ["404", "500", "503"]:
            flags.append(f"HTTP {row['Status Code']} — page broken")
        if str(row.get("Canonical Link Element 1", "")) not in ["", url]:
            flags.append("CANONICAL mismatch — wrong page getting credit")
        if int(row.get("Redirect Hops", 0) or 0) >= 3:
            flags.append("REDIRECT CHAIN — 3+ hops, slow + loses ranking signals")

        if flags:
            issues.append({
                "page":           path,
                "monthly_revenue": rev,
                "issues":         " | ".join(flags),
            })

    return pd.DataFrame(issues).sort_values("monthly_revenue", ascending=False)

# Output: prioritized list of broken pages, sorted by revenue at risk
```

**Sample output:**

| Page | Monthly Revenue | Issue |
|---|---|---|
| /services/dental-implants | $28,000 | NOINDEX — page excluded from Google |
| /services/invisalign | $14,000 | CANONICAL mismatch — /services/invisalign-miami getting credit instead |
| /blog/dental-implant-cost-guide | $8,400 | REDIRECT CHAIN — 3 hops |

**NexoBI AI answer after fix is applied:**
> *"The noindex tag was removed from /services/dental-implants on Feb 14. Organic traffic recovered from 12 to 74 clicks/week by Feb 21. Estimated revenue recovery: $22,000/month based on pre-issue conversion rates."*

---

### 15.9 Quick Reference — Real SEO Problems & NexoBI Solutions

| Real Problem | Root Cause | Tools That Fix It | NexoBI Output |
|---|---|---|---|
| GBP traffic invisible as "direct" | No UTM on GBP website button, no tracking number on listing | Google Business Profile + CallRail | `data_source = "Google Business Profile"` with leads + revenue |
| Content spend with no ROI visibility | Landing page not tracked through CRM to Dentrix | GSC + CRM with landing_page field | Revenue per blog post / service page |
| Rank drops noticed weeks late | No automated position monitoring | GSC weekly comparison + SEMrush | Top Signals alert with dollar amount at risk |
| Reviews not driving growth | No systematic post-visit review request | Podium or Birdeye + Dentrix trigger | Review count → rank → GBP calls → revenue correlation |
| Directory traffic unattributed | No UTMs on Healthgrades/Zocdoc/Yelp listings | Yext (manages all UTMs centrally) | Per-directory ROAS; cancel or scale based on data |
| High organic traffic, low conversion | Generic service page, no decision-stage content | GA4 + CRM form-level tracking | CVR per landing page; CRO revenue model |
| SEO vs Paid budget debate | No single view of revenue by channel | GSC + Google Ads API + CRM + Dentrix | Side-by-side ROAS by channel in one table |
| Technical issue kills rankings silently | noindex / broken canonical / redirect chain | Screaming Frog + GSC Coverage report | Revenue-sorted list of broken pages needing immediate fix |

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 15 added (SEO / Organic Search Real-World Scenarios)*
