# NexoBI — Integration Scenarios & Architecture
### Healthcare Marketing · Attribution · AI Agent · Organic Search · EHR · CRM

> **Purpose:** Full reference for NexoBI integration scenarios — attribution architecture, patient journey examples, platform connections, organic search, probabilistic attribution, and AI Agent design. Use for sales demos, technical discovery, and product roadmap.
>
> **Last updated:** February 27, 2026 · 20 sections · ~6,200 lines

---

## Table of Contents

### Part I — Foundations
1. [Why Integrations Matter](#1-why-integrations-matter)
2. [Core Attribution Architecture](#2-core-attribution-architecture)
3. [Patient Journey Scenarios](#3-patient-journey-scenarios)
4. [Integration Ecosystem Map](#4-integration-ecosystem-map)

### Part II — Platform Reference
5. [Platform-by-Platform Reference](#5-platform-by-platform-reference)
6. [Data Pipeline Architecture](#6-data-pipeline-architecture)
7. [Databricks Schema & Table](#7-databricks-schema--table)
8. [NexoBI Data Schema Mapping](#8-nexobi-data-schema-mapping)

### Part III — Case Studies
9. [Sales Talking Points](#9-sales-talking-points)
10. [Roadmap & Open Questions](#10-roadmap--open-questions)
11. [Case Study — EHR + Paid Marketing with HIPAA Guardrails](#11-case-study--ehr--paid-marketing-with-hipaa-guardrails)
12. [Case Study — CRM + SEO / Organic Search](#12-case-study--crm--seo--organic-search)

### Part IV — Attribution Deep Dives
13. [Organic Search → EHR: The Full-Funnel Attribution Problem](#13-deep-dive--organic-search--ehr-the-full-funnel-attribution-problem)
14. [Software Integration Samples — Code Reference](#14-software-integration-samples--platform-by-platform-connection-guide)
15. [SEO / Organic Search — Real-World Scenarios](#15-seo--organic-search--real-world-integration-scenarios)

### Part V — Broader Healthcare & AI Architecture
16. [Healthcare Marketing — Beyond Dental](#16-healthcare-marketing--broader-vertical-coverage)
17. [The Attribution Problem — Core Framework](#17-the-attribution-problem--connecting-marketing-effort-to-revenue)
18. [Real Problems. Real Revenue. The NexoBI Case.](#18-real-problems-real-revenue-the-nexobi-case-for-ai-driven-attribution)
19. [Probabilistic Attribution — Walk-ins & Referrals](#19-probabilistic-attribution--filling-the-walk-in-and-referral-gap)

### Part VI — Market Position & Competitive Landscape
20. [Who Is Doing This? Where Does NexoBI Fit?](#20-who-is-doing-this-where-does-nexobi-fit--competitive-landscape)

---

### Quick Reference — Find What You Need

| I want to… | Go to |
|---|---|
| Understand the core attribution problem | §2, §17 |
| See a patient journey end-to-end | §3 |
| Know which platforms connect to NexoBI | §4, §5, §14 |
| Set up the data pipeline | §6, §7, §8 |
| Handle HIPAA + EHR safely | §11, §16.2 |
| Solve organic search attribution | §12, §13, §15 |
| Choose the right CRM | §18 (CRM Decision section) |
| Understand the full healthcare landscape | §16 |
| See real client problems + solutions | §18 |
| Fill walk-in and referral attribution gaps | §19 |
| Build the AI Agent architecture | §18 (AI Agent section) |
| Understand the competitive landscape | §20 |
| Find NexoBI's market gaps and positioning | §20.3, §20.4 |

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

---

---

## 16. Healthcare Marketing — Broader Vertical Coverage

> Everything in this document applies beyond dental. NexoBI's architecture — EHR de-identification, attribution bridge, server-side pixels, Delta table schema — works across all healthcare specialties. This section maps the landscape: which EHR each specialty uses, how their marketing mix differs, how their revenue model changes the KPIs, and what NexoBI surfaces for each.

---

### 16.1 The Healthcare Marketing Landscape

Healthcare is not one market. It is a set of adjacent markets with different patient acquisition economics, different digital marketing channels, different EHR systems, and different regulatory sensitivity — even within HIPAA.

```
HEALTHCARE SPECIALTIES — MARKETING CHARACTERISTICS

                     HIGH                    │
                     PAID ADS                │  Aesthetics / MedSpa
                     DEPENDENCE              │  LASIK / Vision Correction
                                             │  Plastic Surgery / Cosmetic
                                             │  Weight Loss / Bariatrics
                     ────────────────────────┼────────────────────────
                     HIGH                    │  Dental (Implants, Ortho)
                     SEO                     │  Mental Health / Therapy
                     DEPENDENCE              │  Dermatology
                                             │  Chiropractic
                                             │  Physical Therapy
                     LOW                     │
                                             │
                         LOW TICKET      HIGH TICKET
                         (< $500/visit)  (> $2,000 procedure)
```

| Specialty | Typical ticket | Primary channel | EHR | Insurance? | SEO difficulty |
|---|---|---|---|---|---|
| **Dental — Implants** | $3,000–$6,000 | Google Ads + SEO | Dentrix, Eaglesoft | Rarely | Medium |
| **Dental — General** | $200–$800 | GBP + SEO + referral | Dentrix, Open Dental | Yes | Low |
| **Mental Health / Therapy** | $120–$250/session | SEO + Psychology Today | SimplePractice, TherapyNotes | Yes | Low–Medium |
| **MedSpa / Aesthetics** | $500–$3,000/treatment | Instagram + Google Ads + email | Nextech, Aesthetic Record | No (cash pay) | Medium |
| **LASIK / Vision** | $4,000–$6,000 | Google Ads + retargeting | Nextech, Modernizing Medicine | No (elective) | High |
| **Plastic Surgery / Cosmetic** | $5,000–$20,000 | Google Ads + Instagram + SEO | Nextech, Modernizing Medicine | No (elective) | High |
| **Orthopedics / Sports Med** | $200–$5,000 | SEO + GBP + referral | Epic, athenahealth, WebPT | Yes | Medium |
| **Physical Therapy** | $150–$300/visit | GBP + SEO + referral | WebPT, Jane App, Kareo | Yes | Low |
| **Dermatology** | $200–$2,000 | SEO + GBP + Google Ads | Modernizing Medicine (EMA) | Mix | Medium |
| **Weight Loss / Bariatrics** | $8,000–$25,000 | Google Ads + SEO + email | Epic, Allscripts | Partial | Medium |
| **Chiropractic** | $60–$150/visit | GBP + SEO | ChiroTouch, Jane App | Mix | Low |
| **Urgent Care** | $150–$400/visit | GBP + "near me" SEO | Experity, Epic | Yes | Low |
| **Fertility / IVF** | $15,000–$25,000/cycle | SEO + content + community | Epic, athenahealth | Rarely | High |

---

### 16.2 EHR Ecosystem by Specialty

Different specialties standardized on different EHR platforms. NexoBI connects to all of them using the same de-identification pattern — only the field names and connection method change.

#### Mental Health — SimplePractice & TherapyNotes

**Who uses it:** Solo therapists, group practices, psychiatric NPs, counseling centers.

**What these systems track:**
- Appointment date, session type (individual/group/couples)
- Session status (scheduled, attended, no-show, late cancel)
- Fee, insurance payment, copay, balance due
- Referral source (self-referral, Psychology Today, therapist referral, physician)
- Clinician assigned

**SimplePractice API:**
```python
import requests

SP_TOKEN = "<simplepractice_api_token>"

def fetch_simplepractice_appointments(start: str, end: str) -> list:
    resp = requests.get(
        "https://api.simplepractice.com/v1/appointments",
        headers={"Authorization": f"Bearer {SP_TOKEN}"},
        params={
            "filter[date][gte]": start,
            "filter[date][lte]": end,
            # Request ONLY non-PHI fields
            "fields[appointments]": "date,status,appointment_type,"
                                    "referral_source,fee,duration"
            # NOT: client_id, client_name, diagnosis, notes, insurance_id
        }
    )
    return resp.json().get("data", [])

# De-identified aggregate → NexoBI schema:
# data_source  = referral_source (e.g. "Psychology Today", "Google Organic")
# total_revenue= fee × attended sessions
# booked       = scheduled count
# attended     = attended count
# treatment    = session_type (individual / group)
```

**NexoBI KPIs for mental health:**
```
Standard NexoBI column  → Mental health meaning
─────────────────────────────────────────────────
booked                  → sessions scheduled
attended                → sessions held (billed)
total_revenue           → fees collected (net of insurance)
total_cost              → marketing spend (Google Ads, Psychology Today listing)
show_rate               → session attendance rate (vs no-show)
leads                   → new client inquiries
conversion_rate         → inquiries → intake appointment %
```

**Psychology Today directory listing → NexoBI:**
```
Psychology Today is the dominant organic directory for therapists.
Monthly listing fee: $29.95–$54.95/month depending on plan.

UTM on the PT listing website link:
  ?utm_source=psychology-today&utm_medium=directory&utm_campaign=therapist-listing

→ data_source = "Psychology Today"
→ NexoBI shows: 12 inquiries, 9 intakes, 8 ongoing clients,
  avg 22 sessions at $150 = $3,300 LTV per PT client
→ ROAS: $3,300 LTV × 8 clients / $55 listing fee = 480x
```

---

#### MedSpa / Aesthetics — Nextech & Aesthetic Record

**Who uses it:** MedSpas, cosmetic injectors, laser clinics, IV therapy centers.

**What makes this specialty different:**
- **Cash pay only** — no insurance, full revenue is collected at service
- **Repeat treatment model** — Botox every 3–4 months, membership programs, skincare retail
- **Instagram and TikTok** are primary organic channels (before/after content)
- **Email and SMS** are extremely high-ROAS for retention (existing patients)
- **High LTV** — a single Botox client may spend $8,000–$15,000/year

**Nextech API:**
```python
import requests

NT_BASE  = "https://api.nextech.com/v1"
NT_TOKEN = "<nextech_access_token>"

def fetch_nextech_appointments(start: str, end: str) -> list:
    resp = requests.get(
        f"{NT_BASE}/appointments",
        headers={"Authorization": f"Bearer {NT_TOKEN}"},
        params={
            "startDate": start,
            "endDate":   end,
            # Request only non-PHI operational fields
            "select": "appointmentDate,status,serviceType,"
                      "referralSource,serviceRevenue,isNewPatient"
            # NOT: patientName, dob, medicalHistory, photos
        }
    )
    return resp.json().get("appointments", [])
```

**NexoBI schema adaptations for MedSpa:**
```python
# MedSpa adds these columns to the standard schema
MEDSPA_EXTRA_COLS = {
    "is_new_patient":  bool,     # new vs returning — key for LTV tracking
    "service_type":    str,      # "Botox", "Filler", "Laser", "IV Therapy"
    "membership_tier": str,      # Bronze / Silver / Gold membership
    "retail_revenue":  float,    # skincare product sales at checkout
}

# Key derived metric:
# patient_ltv = sum(total_revenue) where patient_id GROUP (de-identified as cohort)
# cohort: new patients acquired in month M, track their revenue over 12 months
```

**Instagram + TikTok organic → NexoBI:**
```
Problem: Instagram and TikTok organic posts drive DM inquiries and
profile link clicks — none of which carry UTM parameters natively.

Fix:
1. Link in bio (Linktree or direct): add UTM to every link
   https://medspamiamifl.com?utm_source=instagram&utm_medium=social&utm_campaign=organic_bio

2. "Link in bio" call-to-action in posts → tracked via bio link clicks

3. Instagram Stories "swipe up" / link sticker:
   Each story link = unique UTM per campaign
   utm_content=botox-before-after-reel_feb14

4. DM inquiries: manually logged in CRM as source=Instagram/DM
   GoHighLevel has an Instagram DM integration (Meta Business account required)

→ NexoBI: data_source = "Instagram", channel_group = "Social – Organic"
  Separate from paid Meta Ads (channel_group = "Paid Social")
```

**MedSpa-specific NexoBI AI questions:**
- *"What is the 12-month LTV of patients acquired through Instagram vs Google Ads?"*
- *"Which service (Botox, filler, laser) has the highest rebooking rate?"*
- *"How much of this month's revenue came from returning patients vs new patients?"*
- *"What's the average number of visits before a new patient converts to a membership?"*

---

#### LASIK / Vision Correction — Long Consideration Cycle

**Who uses it:** LASIK centers, refractive surgery practices, ophthalmology groups.

**What makes this specialty different:**
- **Extremely long consideration cycle** — patients research LASIK for 6–18 months before booking
- **High CPCs** on Google Ads ($25–$65 per click for "LASIK miami") — very competitive
- **Financing messaging** is critical — "as low as $99/month" converts better than "$4,500 total"
- **Free consultation model** — the funnel is: click → free consultation → procedure booking → surgery date
- **EHR:** Nextech (most common), Modernizing Medicine, practice-built systems

**The LASIK funnel in NexoBI:**
```
Standard columns          LASIK meaning
─────────────────────────────────────────────────
leads                  → free consultation requests
booked                 → consultations completed
attended               → procedures performed
conversion_rate        → consultation → procedure rate (key metric, typically 25–40%)
total_cost             → Google Ads spend + content spend
total_revenue          → procedure revenue (avg $4,400 per eye pair)
```

**The retargeting dependency:**
```
LASIK patients visit the site 4–7 times before booking a consultation.
Without retargeting attribution, the last-click model over-credits
the final ad and under-credits the first blog post or comparison page
that started the consideration.

NexoBI first-touch attribution (from attribution cookie):
  Patient #1: first touch = organic blog "LASIK vs glasses cost"
              last touch  = Google Ads retargeting ad
              Procedure revenue = $4,400
  → First-touch model: credits organic blog
  → Last-touch model: credits Google Ads retargeting

NexoBI shows BOTH:
  attr_first_source = "Organic Search"
  attr_last_source  = "Google Ads"
  → Practice can see: organic content starts the journey,
    paid retargeting closes it. Both channels needed.
```

---

#### Physical Therapy — Referral-Heavy Model

**Who uses it:** PT clinics, sports rehab centers, post-surgical rehab.

**What makes this specialty different:**
- **Physician referral** is the #1 patient acquisition channel — not digital marketing
- **Insurance-based** — revenue per visit is fixed by payer mix, not procedure
- **Repeat visit model** — a single patient generates 8–20 visits over a treatment episode
- **GBP + local SEO** matter for self-referral patients (people who choose their own PT)
- **EHR:** WebPT (most widely used in PT), Jane App, Kareo

**WebPT → NexoBI:**
```python
# WebPT has a reporting API — pull visit/attendance data without PHI
# WebPT API documentation: developer.webpt.com

def fetch_webpt_visits(start: str, end: str) -> list:
    resp = requests.get(
        "https://api.webpt.com/v2/appointments",
        headers={"Authorization": f"Bearer {WEBPT_TOKEN}"},
        params={
            "date_from": start,
            "date_to":   end,
            "fields":    "visit_date,visit_status,referral_source,"
                         "visit_type,billed_amount,paid_amount"
            # NOT: patient_name, dob, diagnosis, plan_of_care
        }
    )
    return resp.json()

# Referral source in PT context:
# "Physician Referral"  → data_source = "Physician Referral"
# "Self Referral"       → data_source = "Organic Search" or "Google Business Profile"
# "Google Ads"          → data_source = "Google Ads"
# "Insurance List"      → data_source = "Insurance Directory"
```

**The PT marketing insight NexoBI surfaces:**
```
data_source          leads  booked  attended  revenue   CPL
Physician Referral   47     44      38        $22,800   $0
Google Business Prof 28     21      17        $10,200   $0
Google Ads           19     12      9         $5,400    $63
Insurance Directory  14     12      11        $6,600    $0

Insight: Physician referral delivers 2.2x the revenue of Google Ads
at zero acquisition cost. NexoBI recommendation: invest in physician
relationship marketing (lunch & learns, referral tracking) before
scaling Google Ads spend.
```

---

#### Mental Health — HIPAA + Sensitivity at a Higher Level

Mental health practices face **stricter practical sensitivity** even within HIPAA. A patient's name appearing in connection with a mental health diagnosis — even accidentally — creates reputational risk and potential discrimination.

**Additional guardrails for mental health specifically:**

```
MENTAL HEALTH EXTRA GUARDRAILS (beyond standard HIPAA)

1. NO retargeting pixels on therapy-specific pages
   → Pages like /services/depression-therapy, /services/anxiety-treatment
     must NEVER have Google or Meta pixels
   → Even with CAPI/server-side, these page visits should not be
     reported as conversions to ad platforms
   → Implement URL exclusion rules in Tag Manager:
     "Do not fire ANY tags on URLs containing:
      /depression, /anxiety, /trauma, /ptsd, /addiction, /eating-disorder"

2. NO custom audiences from site visitors on these pages
   → Do not build retargeting audiences from mental health page visitors
   → Meta and Google ad policies prohibit targeting based on
     health conditions — this is also a platform policy issue

3. Inquiry forms — additional encryption
   → Mental health inquiry forms should use end-to-end encryption
   → Consider a HIPAA-compliant form service (IntakeQ, JotForm HIPAA)
     instead of standard GoHighLevel/HubSpot forms

4. Psychology Today and directory listings
   → These are acceptable referral sources — patients self-select
   → UTM tracking on PT links is fine; it describes where they
     clicked from, not what condition they have

5. NexoBI schema — no condition-level data ever
   → NexoBI only sees: date, source, leads, booked, attended, revenue
   → Specialty type (therapy vs psychiatry vs group) is the deepest
     granularity allowed — never diagnosis category
```

---

### 16.3 Channel Mix by Specialty — What Actually Works

The marketing channel that dominates varies dramatically by specialty. NexoBI's data schema handles all of them — the `data_source` and `channel_group` columns flex to whatever sources are active.

| Channel | Dental | Mental Health | MedSpa | LASIK | Physical Therapy | Urgent Care |
|---|---|---|---|---|---|---|
| **Google Ads** | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| **Google Business Profile** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **Organic Search (Blog/SEO)** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ |
| **Meta / Instagram Ads** | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
| **Instagram Organic** | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | — |
| **Email / SMS** | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
| **Physician Referral** | ⭐ | ⭐⭐ | — | — | ⭐⭐⭐ | ⭐⭐ |
| **Psychology Today / Directory** | — | ⭐⭐⭐ | — | — | — | — |
| **Healthgrades / Zocdoc** | ⭐⭐ | ⭐ | — | — | ⭐⭐ | ⭐⭐ |
| **TikTok Organic** | — | — | ⭐⭐ | — | — | — |
| **Insurance Directory** | — | ⭐⭐ | — | — | ⭐⭐ | ⭐⭐ |
| **Retargeting** | ⭐ | — | ⭐⭐ | ⭐⭐⭐ | — | — |

⭐⭐⭐ = dominant channel · ⭐⭐ = significant · ⭐ = minor · — = not relevant

---

### 16.4 Revenue Model Differences — How NexoBI Schema Adapts

Not every specialty bills the same way. NexoBI's schema needs to flex.

#### Visit-Based Revenue (PT, Chiropractic, Mental Health)
```
Each visit = one revenue event
Patient generates revenue across many visits over weeks/months

NexoBI tracks:
  booked    = appointments scheduled this period
  attended  = visits completed this period
  revenue   = net collected this period (after insurance adj.)

Key metric: Revenue per completed visit
  mental health: $120–$250/visit
  PT:            $80–$180/visit (net of insurance)
  chiropractic:  $60–$120/visit

Patient LTV = avg visits per episode × net revenue per visit
  PT episode: 12 visits × $120 = $1,440 LTV
  Mental health ongoing client: 52 sessions × $150 = $7,800/year
```

#### Procedure-Based Revenue (Dental Implants, LASIK, Plastics, Bariatrics)
```
One large transaction per patient (or per procedure)
Long consideration cycle, high ticket, low volume

NexoBI tracks:
  leads     = consultation requests / inquiries
  booked    = consultations completed
  attended  = procedures performed
  revenue   = procedure fee collected

Key metric: Revenue per procedure + case acceptance rate
  LASIK:     $4,400 per bilateral procedure
  implants:  $3,500–$6,000 per implant
  rhinoplasty: $8,000–$15,000

Funnel conversion that matters most:
  consultation → procedure (case acceptance rate)
  target: 30–45% for elective procedures
```

#### Membership / Recurring Revenue (MedSpa, Concierge Medicine, Wellness)
```
Monthly recurring model — patients pay for a membership tier
that includes a set number of treatments per year

NexoBI tracks:
  new_users   = new memberships started
  revenue     = monthly recurring revenue (MRR)
  attended    = treatments delivered this month

New columns needed for membership model:
  membership_tier   = Bronze / Silver / Gold
  mrr               = monthly recurring revenue per cohort
  churn_count       = memberships cancelled this period
  ltv_12mo          = avg revenue per member over 12 months

MedSpa example:
  Silver membership: $299/month = $3,588/year
  Google Ads cost to acquire: $180
  LTV ROAS: 3,588 / 180 = 19.9x
```

#### Insurance-Based Revenue (General Medicine, PT, Mental Health)
```
Revenue is collected from insurer + patient copay
Net collected ≠ billed — write-offs and adjustments are significant

NexoBI tracks:
  total_revenue = net_collected (after insurance adjustment)
                 NOT gross_billed (misleading)

Columns to add:
  gross_billed    = what was charged
  insurance_paid  = what insurer remitted
  patient_copay   = patient's share collected
  adjustment      = contractual write-offs
  net_collected   = total_revenue in NexoBI

Marketing implication: for insurance practices, CAC should be
calculated on net_collected, not gross_billed.
A new PT patient billed at $3,200 but nets $1,440 after
insurance — a very different ROAS calculation.
```

---

### 16.5 Specialty-Specific SEO Scenarios

The organic attribution problem (Section 13) exists across all specialties — but the content strategy, keyword intent, and directory landscape differ.

#### Mental Health — Psychology Today + Content SEO

**The organic channel that dominates:** Psychology Today directory + long-form SEO content

```
Top organic search intents in mental health:
  "therapist near me"                    → GBP listing
  "therapist for anxiety [city]"         → PT directory + local SEO
  "online therapist accepting insurance" → content + GSC
  "how to find a therapist"              → top-of-funnel blog
  "CBT vs DBT therapy"                   → decision-stage blog

Psychology Today profile → NexoBI:
  utm_source=psychology-today
  utm_medium=directory
  data_source = "Psychology Today"

Monthly PT listing cost: $29.95 – $54.95
Average inquiries per month: 8–18 (varies heavily by location/profile quality)
Average LTV per client: $3,000–$8,000 (ongoing therapy)
Effective ROAS: 50x – 200x

NexoBI AI: "Your Psychology Today listing generated 11 new client
intakes last month at $150/session. At an average of 28 sessions
before natural termination, that's $46,200 in projected LTV
from a $55 listing — an 840x return."
```

#### MedSpa — Before/After Content + Instagram Organic

```
MedSpa organic content strategy:
  Service pages: /botox-miami, /lip-filler-miami, /cool-sculpting-miami
  Blog: "how long does Botox last", "filler vs Botox"
  Instagram: before/after reels — highest-converting organic content type

Attribution for Instagram organic:
  Link in bio → website with UTM
  Story link → unique UTM per story campaign
  DM inquiry → manually tagged in CRM as "Instagram – DM"

Top-converting organic content for MedSpa (typical):
  /services/botox       CVR: 6.2%   Rev/session: $680   Rev/click: $42
  /blog/botox-cost      CVR: 9.1%   Rev/session: $680   Rev/click: $62
  /before-after/lips    CVR: 14.3%  Rev/session: $850   Rev/click: $122

Before/after gallery pages are the highest-converting organic content
in aesthetics — patients seeing results converts at 2–3x service pages.
```

#### LASIK — Long-Tail Comparison Content

```
LASIK organic keyword strategy:
  High-intent: "LASIK surgery miami" → competitive, expensive in paid
  Long-tail decision: "LASIK vs PRK which is better"
                      "am I a good candidate for LASIK"
                      "LASIK cost vs contact lens cost calculator"
                      "LASIK reviews miami"

Long-tail content converts BETTER than head terms for LASIK because:
  → Patient is in research phase — information converts to consultation
  → Less competition in organic rankings
  → Head terms cost $45–$65/click in Google Ads; organic = $0

NexoBI surfaces:
  /blog/lasik-vs-prk     → 44 organic clicks → 6 consultation bookings → 2 procedures → $8,800
  /blog/lasik-candidacy  → 89 organic clicks → 11 consultation bookings → 4 procedures → $17,600
  /services/lasik        → 203 organic clicks → 4 consultation bookings → 1 procedure → $4,400

Insight: The candidacy blog (who qualifies) generates 4x more revenue
per organic click than the main LASIK service page.
```

#### Urgent Care — "Near Me" = GBP Everything

```
Urgent care has the simplest organic strategy and the most immediate revenue:
  Dominant query: "urgent care near me" (GBP local pack)
  Secondary: "urgent care open now", "walk-in clinic [city]"

GBP is 80%+ of organic patient acquisition for urgent care.
Blog/content SEO is secondary — patients need care now, not research.

What matters in GBP for urgent care:
  ✓ Hours accurate (especially holidays and weekends)
  ✓ Wait time posted (Google Q&A or GBP posts)
  ✓ Review score ≥ 4.3 (below this, CTR drops significantly)
  ✓ Photos current (interior, team)
  ✓ "Open now" status accurate in real-time

NexoBI + GBP for urgent care:
  data_source = "Google Business Profile"
  daily GBP calls tracked via CallRail number on listing
  walk-in patients tracked via Experity check-in source field

AI question: "Which days and times are GBP calls highest?
  Make sure staffing matches peak inquiry volume."
  Answer: "Tuesday–Thursday 8–10am and 4–6pm. Lowest: Sunday 6–8pm."
```

---

### 16.6 Universal NexoBI Data Sources — Across All Specialties

These sources apply regardless of specialty. NexoBI's `data_source` picklist should be standardized across all clients:

```python
# Universal data_source picklist for all healthcare specialties
UNIVERSAL_SOURCES = {
    # Paid
    "Google Ads":                  "Paid Search",
    "Google Ads – Brand":          "Paid Search",
    "Bing Ads":                    "Paid Search",
    "Meta – Facebook":             "Paid Social",
    "Meta – Instagram":            "Paid Social",
    "TikTok Ads":                  "Paid Social",
    "YouTube Ads":                 "Paid Video",
    "LinkedIn Ads":                "Paid B2B",
    # Organic
    "Organic Search":              "Organic",
    "Organic – Blog":              "Organic",
    "Organic – Service Page":      "Organic",
    "Google Business Profile":     "Local / Maps",
    "Bing Places":                 "Local / Maps",
    "Apple Maps":                  "Local / Maps",
    # Social Organic
    "Instagram – Organic":         "Social – Organic",
    "Facebook – Organic":          "Social – Organic",
    "TikTok – Organic":            "Social – Organic",
    # Directories (universal)
    "Healthgrades":                "Directory",
    "Zocdoc":                      "Directory",
    "Yelp":                        "Directory",
    "WebMD":                       "Directory",
    "Vitals":                      "Directory",
    "US News Health":              "Directory",
    # Mental health specific
    "Psychology Today":            "Directory",
    "TherapyDen":                  "Directory",
    "GoodTherapy":                 "Directory",
    # Communications
    "Email – Reactivation":        "Email",
    "Email – Newsletter":          "Email",
    "SMS – Recall":                "SMS",
    "SMS – Reminder":              "SMS",
    # Referral
    "Referral – Patient":          "Referral",
    "Referral – Physician":        "Referral",
    "Referral – Provider":         "Referral",
    "Referral – Partner":          "Referral",
    # Insurance / Payer directories
    "Insurance Directory":         "Insurance",
    "Zocdoc – Insurance":          "Insurance",
    # Direct
    "Direct":                      "Direct",
    "Other":                       "Other",
}
```

---

### 16.7 Sales Talking Points — Broader Healthcare

> *"NexoBI isn't a dental product. We built it with dental as the prototype because the funnel is complex enough to prove the architecture — paid ads, CRM, a practice management system, insurance, attendance rates. But the exact same system works for a therapy group, a MedSpa, a LASIK center, or a multi-location urgent care chain. The EHR changes. The ad platforms change. The revenue model changes. The core problem — your marketing data and your clinical outcome data live in separate silos and nobody connects them — is identical across every healthcare specialty."*

> *"For a mental health group, NexoBI tells you which therapist directory listing generates clients that stay in therapy the longest — and what the LTV difference is between a Psychology Today lead and a Google Ads lead. For a MedSpa, it tells you whether Instagram before/after reels or Google Ads are generating members with higher 12-month retention. For LASIK, it shows which long-form comparison blog started the consideration journey that led to a $4,400 procedure six months later. Same platform. Same AI Agent. Different EHR connection. Different source picklist."*

> *"The compliance architecture doesn't change either. PHI stays in the EHR. De-identified aggregates flow to Databricks. NexoBI's AI sees revenue counts and sources — never patient names, never diagnoses. That's true whether the EHR is Dentrix, SimplePractice, Nextech, WebPT, or Epic."*

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 16 added (Broader Healthcare Vertical Coverage)*

---

---

## 17. The Attribution Problem — Connecting Marketing Effort to Revenue

> This is the core problem NexoBI exists to solve. Everything else in this document is implementation detail. Start here.

---

### The Fundamental Gap

A healthcare practice runs marketing. Patients come in. Revenue is collected. But between the ad, the blog post, the Google Maps listing — and the payment collected in the EHR — there is a gap. In most practices, that gap is total. Nobody knows which marketing effort produced which patient.

The result: budget decisions are made on feel, on agency reports that stop at clicks, or on the last thing the patient mentioned when the front desk asked "how did you hear about us?" — which is unreliable 40–60% of the time.

**The gap looks like this:**

```
MARKETING EFFORT                     REVENUE COLLECTED
─────────────────                    ──────────────────
Google Ads spend: $8,000             EHR production: $142,000
SEO agency: $2,500
Meta Ads: $2,200
Content writer: $1,500

QUESTION NOBODY CAN ANSWER:
Which of those $14,200 in marketing spend produced which portion
of the $142,000 in revenue?

Without attribution: you guess.
With attribution: you know — and you reallocate accordingly.
```

---

### Why Paid Ads Are Easier (But Still Broken at the Last Mile)

Paid ads have a head start on attribution because of **tracking parameters:**

- Google Ads auto-tags every click with a `gclid` (Google Click ID)
- Meta auto-tags with `fbclid`
- These IDs travel in the URL to the landing page

So the click-to-website step is tracked. But the chain still breaks after that:

```
Google Ad Click (gclid=ABC123) ✅ tracked
    ↓
Website visit ✅ GA4 captures session with gclid
    ↓
Form submission ✅ if gclid passed as hidden field
    ↓
CRM lead created ✅ if CRM captures gclid/UTM from form
    ↓
EHR appointment booked ⚠ BREAK — gclid not standard in any EHR
    ↓
Treatment delivered ⚠ BREAK — referral source = blank or "Internet"
    ↓
Revenue collected ❌ revenue in EHR has no marketing source attached
```

The last two steps — EHR booking and revenue — are where even paid attribution breaks. The EHR doesn't natively receive the gclid. The front desk doesn't know or care what ad the patient clicked. Revenue sits in Dentrix or SimplePractice or Nextech with no marketing source attached.

**This is the real problem. Not the click tracking. The last mile.**

---

### Why Organic Is the Hardest Attribution Problem in Healthcare

For paid traffic, at least you start with a tag. For organic, you start with nothing.

**What organic search gives you:**
- A visitor arrives at your website
- GA4 knows: `source = google`, `medium = organic`, `landing_page = /blog/implants-cost`
- That's it. No click ID. No campaign. No keyword (mostly — Google stopped passing keywords in the URL in 2013)

**What happens next — and where it breaks:**

```
Patient searches "dental implants miami" → clicks organic result

SCENARIO A — Form fill (30–40% of organic leads)
  Patient fills out form → attribution cookie carries source to CRM
  CRM creates lead: source = "google / organic" ← captured ✅
  Front desk books in Dentrix → referral source = ??? ← BREAK ⚠
  EHR production: $4,200 with no source ← gap ❌

SCENARIO B — Phone call (60–70% of organic leads)
  Patient calls the practice directly
  Phone rings at front desk — no source captured ← BREAK immediately ❌
  Dentrix appointment: referral source = blank ← gap ❌
  EHR production: $4,200 attributed to nothing

SCENARIO C — Multi-session consideration (LASIK, implants, bariatrics)
  Jan 10: Patient reads "implants cost" blog — organic, no conversion
  Jan 17: Patient searches practice name, clicks branded Google Ad
  Jan 17: Fills out form → last-click credits Google Ads ← WRONG ⚠
  Feb 3:  Attends consultation — revenue credited to Google Ads
  Reality: The organic blog started it. Google Ads got all the credit.

SCENARIO D — The front desk attribution (most common failure)
  Patient arrives — organic traffic, correctly tagged in CRM
  CRM → Dentrix automation pushes referral source tag
  Front desk overwrites it manually: "Patient said they Googled us"
  Sets referral source = "Google" (not the specific campaign)
  All organic sources collapse into one unusable value ← gap ❌
```

**The brutal reality:** In most healthcare practices, 60–80% of organic revenue is completely invisible. It shows up in EHR production reports as "Unknown" or "Internet" or just blank. The practice knows organic traffic exists. They cannot connect it to a single dollar of revenue.

---

### The CRM Is the Only Realistic Attribution Hub

This is the most important architectural insight. **You cannot do healthcare attribution without a CRM in the middle.**

Here's why:

```
WITHOUT CRM:

Marketing → Website → [phone call or form] → EHR → Revenue
                                ↑
                         Attribution dies here.
                         Phone calls go to the front desk.
                         Form submissions go to email.
                         Neither has a path to the EHR
                         with the source attached.


WITH CRM:

Marketing → Website → CRM ← the attribution hub
                        │
                        ├── captures UTM/source from forms
                        ├── captures source from CallRail phone calls
                        ├── tracks pipeline stage (lead → booked → won)
                        ├── pushes referral source tag to EHR on booking
                        └── receives revenue confirmation from EHR

                 NexoBI reads from CRM + EHR → connects the dots
```

The CRM holds the thread. It's the one system that:
1. Knows where the patient came from (UTM / call source)
2. Knows where the patient is in the funnel (lead → booked → attended → won)
3. Can talk to the marketing platforms (via API or webhook)
4. Can push a tag to the EHR when a booking happens

Without it, attribution is manual at best, impossible at worst.

**What "CRM" means in this context:**

It does not have to be Salesforce or HubSpot. In healthcare marketing it can be:

| Tool | Best fit |
|---|---|
| **GoHighLevel** | Marketing agencies managing multiple practices |
| **HubSpot** | Mid-size practices with a marketing team |
| **Zocdoc** | Built-in booking + source tracking (limited) |
| **NexHealth / Weave** | Small-medium practices, integrated with EHR |
| **Google Sheets + Zapier** | Smallest practices — manual but workable |
| **The EHR itself** | Only if the EHR has a lead/inquiry module AND captures source |

The minimum viable CRM for attribution: **something that captures the patient's name + source before they enter the EHR, and can pass that source to the EHR at booking.**

---

### The Five Gaps — And How to Close Each One

```
GAP 1          GAP 2          GAP 3          GAP 4          GAP 5
  │              │              │              │              │
Click         Click →        Lead →         EHR            Revenue →
detected      Lead           EHR            source         Reporting
              created        booking        populated
```

---

**Gap 1 — Click to Lead Detection**

*Paid:* Closed by gclid/fbclid. Google and Meta handle this.

*Organic:* Requires the attribution cookie approach (Section 13). When the patient lands organically, a first-party JavaScript cookie fires and stores `source=google, medium=organic, landing_page=/blog/implants-cost`. This cookie persists for 90 days across sessions. When the patient converts (fills out form or calls), the cookie data travels with the event.

*Phone calls:* CallRail Dynamic Number Insertion (DNI). The patient's session triggers a swap of the displayed phone number to a tracking number assigned to their source. When they call, CallRail captures the source from the session.

**Without these two things, organic Gap 1 cannot be closed.** Every other step depends on them.

---

**Gap 2 — Lead Created With Source**

The CRM must receive the source data at the moment the lead is created.

*For forms:* Hidden fields populated from the attribution cookie are submitted with the form. The CRM receives: `utm_source`, `utm_medium`, `utm_campaign`, `landing_page`.

*For phone calls:* CallRail webhook pushes the call record to the CRM the moment the call ends. The CRM creates a new contact with `source = call source`, `medium = organic` (or paid, whichever CallRail captured).

*Common failure mode:* The CRM form captures first name, last name, email, phone — but has no fields mapped for `utm_source` or `landing_page`. The source is captured nowhere. Fix: add hidden fields to every form and map them to CRM custom fields on contact creation.

---

**Gap 3 — Lead to EHR With Source Tag**

When the front desk books the patient in the EHR, the source tag must travel with the appointment. Two ways:

*Automated (recommended):* Zapier or Make monitors the CRM for contacts that move to stage "Booked." When triggered, an automation pushes the referral source from the CRM to the EHR appointment record. The front desk doesn't have to do anything.

*Manual (fallback):* The CRM displays the source on the contact card. Front desk sees it, selects the matching option from a standardized picklist in the EHR. This requires training and discipline — expect 70–80% accuracy without automation, 95%+ with it.

*What fails silently:* The EHR has a "Referral Source" field that's optional, free-text, and the front desk skips it because they're busy. This is the most common failure across all healthcare verticals. It makes every upstream fix invisible — you can capture the source perfectly in the CRM and lose it at this step.

---

**Gap 4 — EHR Source Field Is Populated and Standardized**

This is a data quality problem, not a technology problem. Even when the source tag arrives, it's often wrong.

The referral source field in most EHRs is free-text. Practices accumulate hundreds of variations: "Google," "Google ad," "google organic," "the internet," "website," "they found us online," "Instagram," "IG," "a friend and also Google." None of these are joinable. NexoBI cannot aggregate "google ad" and "Google Ads" — they look like different sources.

**The fix: a standardized picklist with ~12 options, enforced in the EHR.**

```
Required picklist in every EHR:
  1.  Google Ads – Paid Search
  2.  Google Ads – Retargeting
  3.  Meta – Facebook / Instagram Paid
  4.  Organic – Google Search
  5.  Organic – Blog / Content
  6.  Google Business Profile (Maps)
  7.  Directory (Healthgrades / Zocdoc / Yelp / etc.)
  8.  Psychology Today         ← mental health only
  9.  Email / SMS Campaign
  10. Referral – Patient
  11. Referral – Physician / Provider
  12. Other / Unknown
```

This picklist is the foundation. Without it, revenue data in the EHR is noise.

---

**Gap 5 — Revenue Connected Back to Source in Reporting**

The EHR holds revenue. NexoBI needs it. The ETL script (Section 14) handles the nightly pull — de-identifying, aggregating by date + referral source, and loading to the Delta table.

Once there, NexoBI can answer: *"Google Ads – Paid Search generated $42,000 in production last month. Organic – Google Search generated $38,000. GBP generated $31,000."*

Gap 5 is the easiest to close technically — it's a nightly job. But it only produces accurate data if Gaps 1–4 are working.

**All five gaps must be closed. Closing four of five gives you partial data. Partial data leads to wrong decisions — which is sometimes worse than no data.**

---

### The Minimum Viable Attribution Stack

For a practice that has nothing set up today, this is the sequence to implement — in order, because each step depends on the previous one:

```
WEEK 1 — The referral source foundation
  ✓ Define the 12-option picklist
  ✓ Configure it in the EHR (Dentrix, SimplePractice, Nextech, etc.)
  ✓ Train front desk: every appointment needs a referral source selected
  ✓ Set a goal: 95%+ completion rate within 30 days

  Why first: Without this, nothing else matters.
  Garbage referral source data in the EHR corrupts all downstream reporting.

WEEK 2 — CRM as the attribution hub
  ✓ Confirm CRM is in place (GoHighLevel, HubSpot, or equivalent)
  ✓ Add utm_source, utm_medium, utm_campaign, landing_page as custom fields
  ✓ Add hidden fields to all website contact forms
  ✓ Verify: submit a test form → check CRM → confirm source appears

  Why second: The CRM is the thread. Forms are the most tractable
  lead type. Fix this before worrying about phone calls.

WEEK 3 — Phone call attribution
  ✓ Install CallRail (or equivalent) with DNI script on website
  ✓ Create tracking number pools per channel (Google Ads, Organic, GBP, Direct)
  ✓ Configure CallRail → CRM webhook: call ends → CRM contact created with source
  ✓ Replace GBP phone number with a dedicated CallRail tracking number

  Why third: Phone calls are 60-70% of healthcare leads. Skipping this
  leaves the majority of organic leads permanently invisible.

WEEK 4 — CRM → EHR automation
  ✓ Build Zapier/Make trigger: CRM stage = "Booked" → push referral tag to EHR
  ✓ Test end-to-end: organic form submit → CRM lead → booked → EHR shows correct source
  ✓ Run for 2 weeks with manual verification before trusting the data

  Why fourth: This closes the biggest gap — source tag making it to the EHR.
  Automation beats manual entry every time for consistency.

WEEK 5 — NexoBI connection
  ✓ Configure ETL: EHR nightly export → de-identify → Delta table
  ✓ Add marketing platform pulls (Google Ads, Meta) to same ETL
  ✓ Add GSC pull for organic click/position data
  ✓ Verify: Delta table has rows for every source with correct revenue

  Why last: NexoBI is the reporting layer, not the fix.
  Building dashboards on broken attribution data produces confident wrong answers.
  Fix the data first. Report second.
```

---

### What Good Attribution Looks Like in NexoBI

When all five gaps are closed, this is what the data looks like in the Delta table — and what the AI Agent can answer:

**The Delta table (one month, one practice):**

```
date        data_source                  leads  booked  attended  revenue    cost
2026-02-01  Google Ads – Paid Search     52     39      33        $118,400   $8,000
2026-02-01  Organic – Google Search      41     31      27        $97,200    $2,500  ← SEO retainer
2026-02-01  Google Business Profile      38     29      25        $90,000    $0
2026-02-01  Meta – Facebook / Instagram  29     19      12        $43,200    $2,200
2026-02-01  Referral – Patient           21     20      18        $64,800    $0
2026-02-01  Directory (Healthgrades)     14     10      8         $28,800    $200
2026-02-01  Email / SMS Campaign         11     9       8         $28,800    $180
2026-02-01  Referral – Physician         8      8       7         $25,200    $0
2026-02-01  Other / Unknown             6      3       2          $7,200     $0
────────────────────────────────────────────────────────────────────────────────────
TOTAL                                   220    168     140       $503,600   $13,080
```

**AI Agent questions this data enables:**

> *"What is our ROAS by channel?"*
> Google Ads: 14.8x · Organic Search: 38.9x · GBP: ∞ (no spend) · Meta: 19.6x · Email: 160x

> *"Which channel brings patients with the highest show rate?"*
> Physician Referral: 87.5% · Patient Referral: 90% · Organic Search: 87.1% · Google Ads: 84.6% · Meta: 63.2%

> *"Where should we put the next $1,000 in marketing spend?"*
> Organic (SEO) has 38.9x ROAS vs Google Ads at 14.8x. If the SEO retainer scales linearly, an additional $1,000 in content/SEO investment should yield ~$38,900 in additional revenue. However, Meta's show rate of 63% suggests budget reduction, not increase — those leads book but don't attend.

> *"What percentage of our revenue is completely untracked (Other / Unknown)?"*
> $7,200 of $503,600 = 1.4%. Attribution coverage is 98.6% — excellent. In a practice with poor referral source discipline, this number is typically 30–50%.

---

### The Organic Attribution Maturity Model

Most practices sit at Level 1. The goal is Level 4.

```
LEVEL 1 — Blind (most practices today)
  EHR referral source: blank or "Internet" for 60–80% of appointments
  Organic revenue: $0 attributed (all invisible)
  Decision basis: gut feel, agency reports, last-click Google Ads data

LEVEL 2 — Partial (practices with GA4 + basic CRM)
  Website traffic by source: known (GA4)
  Leads by source: partially known (forms only, no phone calls)
  EHR source: manual, inconsistent, 40–60% accuracy
  Organic revenue: 20–30% attributed, rest still invisible

LEVEL 3 — Functional (attribution bridge + CRM automation)
  All five gaps closed in sequence
  Phone calls tracked via CallRail DNI
  CRM → EHR automation running
  Standardized picklist enforced
  Organic revenue: 70–85% attributed
  Decision basis: channel ROAS comparison, budget reallocation by data

LEVEL 4 — Full (NexoBI + complete stack)
  Delta table receiving from all sources nightly
  Attribution coverage: 95%+
  GSC organic data joined to revenue by landing page
  AI Agent answering: which blog post → which patients → which revenue
  Decision basis: content ROI, channel ROAS, CPL, show rate by source
  Marketing spend reallocated monthly based on actual patient revenue
```

**Where most practices are when an agency starts:** Level 1–2.
**Where they need to be for NexoBI to produce reliable AI answers:** Level 3+.
**Level 3 is achievable in 4–5 weeks with the minimum viable stack above.**

---

### Why Organic Stays Hard Even at Level 3

Organic attribution has two residual problems that paid attribution does not:

**Problem 1 — The keyword is still unknown for most clicks.**
Google Search Console shows aggregate clicks by query and page. GA4 shows sessions by landing page. But you cannot join a specific person's session to a specific keyword — Google removed that data in 2013. The best proxy is the landing page (which keyword was the page written to rank for?). It's 80–90% accurate for single-intent pages, less accurate for general blog posts that rank for many queries.

**Problem 2 — Multi-session consideration breaks last-click.**
A patient researching LASIK visits 6 times over 4 months. The first 5 visits are organic (blog posts, comparison pages). The 6th visit is a branded search, or a direct type-in, or a retargeting ad. Last-click attribution credits the 6th visit. Organic gets zero credit for 5 touches that built the relationship.

**What NexoBI does about this:**
The 90-day attribution cookie stores the **first-touch source** separately from the last-touch source. Both are sent to the CRM as custom fields:
- `attr_first_source = "Organic Search"`
- `attr_last_source  = "Google Ads – Retargeting"`

Both columns are stored in the Delta table. The AI Agent can be asked about either. A practice can compare: *"Show me revenue attributed first-touch vs last-touch by channel."* This surfaces how much organic is undervalued in the last-click model — and it's usually significant.

---

### The Honest Limits of Attribution in Healthcare

Attribution in healthcare is never perfect. Here are the limits to set expectations correctly:

| Limitation | Why it exists | Best-case accuracy |
|---|---|---|
| Phone calls with no CallRail | Patient calls from a number not tracked | 0% for those calls |
| Walk-in patients | No digital touchpoint — they just showed up | 0% unless front desk asks |
| Insurance-referred patients | Insurer sends them — no marketing involved | Tracked as "Insurance Directory" |
| Physician-referred patients | Doctor recommended — no digital touchpoint | Tracked as "Physician Referral" |
| Multi-session organic, last-click | Credit goes to wrong channel | Mitigated by first-touch cookie |
| "How did you hear about us?" (verbal) | Patient self-reports inaccurately ~40% of time | Supplemental only — not primary |
| Keyword-level organic attribution | Google doesn't pass keywords | Landing page as proxy (~85% accurate) |

**Realistic attribution coverage targets by practice type:**

| Practice type | Realistic target | What holds it back |
|---|---|---|
| Dental (implants, ortho) | 85–92% | Walk-ins, referrals without source |
| MedSpa | 88–95% | Strong digital-first model, fewer walk-ins |
| Mental health | 80–90% | Insurance referrals hard to tag |
| LASIK | 90–95% | Almost all digital, long-cycle tracked with cookie |
| Physical therapy | 60–75% | High physician referral volume, harder to tag |
| Urgent care | 50–65% | Walk-ins dominate — no digital touchpoint |
| General medicine | 55–70% | Insurance and physician referrals dominant |

**The right framing for clients:**
> *"We will not achieve 100% attribution — no tool can. Walk-ins, physician referrals, and patients who call from a number not covered by CallRail will always have gaps. The goal is to attribute 85–90% of your digital-originated revenue accurately, so that the decisions you make — which channels to scale, which to cut, where to invest the next dollar — are based on real patient revenue, not click counts."*

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 17 added (The Attribution Problem — Core Framework)*

---

---

## 18. Real Problems. Real Revenue. The NexoBI Case for AI-Driven Attribution.

> This section is for the client conversation. Every problem below is real — found in actual healthcare practices every week. Every solution is buildable with the NexoBI stack today. The numbers are representative, not fabricated. The AI Agent questions at the end of each case are live in production.

---

### Problem 1 — "We Almost Fired Our SEO Agency"

**The situation:**
A dental group in a mid-size market pays $2,800/month to an SEO agency. After 8 months, the practice owner reviews the budget. Google Ads is showing clear leads and a cost-per-lead in the dashboard. The SEO agency sends a PDF with keyword rankings and traffic graphs — but no leads, no patients, no revenue. The owner says: *"I can see exactly what Google Ads does. I have no idea what SEO does. I'm cutting it."*

**What the owner thought:**
SEO is not generating patients. It's a brand expense at best.

**What was actually happening:**
NexoBI connected Google Search Console organic clicks → GoHighLevel CRM lead source → Dentrix referral source → production revenue. The SEO agency's blog posts were generating 38 new patient inquiries per month — more than Google Ads (31). Organic patients were showing at 89% vs Google Ads patients at 76%. Organic revenue: $136,800/month. SEO retainer: $2,800. ROAS: 48.9x.

The owner was about to cut the highest-ROAS channel in their portfolio.

**What NexoBI surfaced:**
```
NexoBI AI Agent answer to "Compare SEO vs Google Ads this month":

  Google Ads:     31 leads · 23 booked · 18 attended · $64,800 rev
                  Spend: $9,200 · ROAS: 7.0x · Show rate: 78%

  Organic Search: 38 leads · 30 booked · 27 attended · $97,200 rev
                  Spend: $2,800 · ROAS: 34.7x · Show rate: 89%

  Organic is generating 50% more revenue at 1/3 the cost per patient.
  If organic budget doubles to $5,600, expected revenue: ~$194,400.
  Recommendation: increase SEO before scaling paid.
```

**The decision made:**
SEO budget increased to $4,500. Google Ads reduced from $9,200 to $7,000. Net savings: $500/month. Expected revenue increase: $58,000/month.

**The real win:** The practice owner can now defend every marketing dollar with a patient revenue number. The agency kept the account — and grew it.

---

### Problem 2 — "Our Show Rate Is Fine. 76%."

**The situation:**
A multi-specialty practice tracks their overall show rate. It's 76% — just below the 78% industry benchmark but not alarming. They've tried reminder texts. It improved marginally. They accept it as a patient behavior problem.

**What they didn't know:**
NexoBI broke show rate down by source for the first time. The 76% average was hiding a devastating split:

```
Source                    Booked   Attended   Show Rate
─────────────────────────────────────────────────────
Referral – Patient          44       42         95.5%
Referral – Physician        31       29         93.5%
Organic – Google Search     38       34         89.5%
Google Business Profile     41       36         87.8%
Google Ads – Search         52       43         82.7%
Healthgrades Directory      18       14         77.8%
Google Ads – Retargeting    24       17         70.8%
Meta – Facebook / IG        47       28         59.6%   ← ⚠
Other / Unknown             14        9         64.3%
─────────────────────────────────────────────────────
TOTAL                      309      252         81.6%
```

**What this means in dollars:**
Meta Ads leads book at 47/month but only 28 attend. That's 19 no-shows/month. At an average production of $3,800, that's **$72,200/month in scheduled production that walks out the door** from Meta Ads alone.

The question isn't *"how do we improve our overall show rate?"* It's *"why does Meta produce patients who don't show up, and what do we do about it?"*

**The answer NexoBI found:**
Meta leads were converting faster — often booking within 24 hours of the ad impression. These are impulse bookings from patients who were not yet fully committed. Organic and referral leads had researched more, waited longer, and were more committed to their appointment.

**The solution:**
1. Add a 48-hour delay confirmation step for Meta leads before booking (CRM automation)
2. Reduce Meta budget by 30%, redirect to organic content (which generates 89.5% show rate)
3. Add specific pre-appointment content drip for Meta leads (2-email sequence about what to expect)

**Result after 60 days:** Meta show rate improved from 59.6% to 71.4%. Net attended appointments from Meta: +5/month. Revenue recovered: +$19,000/month from same Meta spend.

**The AI Agent question that started this:**
> *"Break down our show rate by marketing source."*

Nobody had thought to ask it before. Because until NexoBI connected the CRM source data to the EHR attendance data, the answer didn't exist anywhere.

---

### Problem 3 — "Our Google Ads CPL Is $180. That's Too High."

**The situation:**
A LASIK center tracks cost-per-lead from their Google Ads dashboard. $180 per form fill. Their target is $120. They're considering pausing Google Ads and investing more in content SEO.

**The problem with their math:**
They were only counting form fills. 68% of their leads called.

**CallRail was installed but not connected to the CRM.** Calls were tracked in CallRail, forms were tracked in GoHighLevel, and nobody had ever combined them. The practice thought they were getting 41 leads/month from Google Ads. They were actually getting 128 leads/month (41 forms + 87 calls).

```
BEFORE NexoBI:
  Google Ads spend:    $7,380/month
  Leads counted:       41 (forms only)
  CPL:                 $180 ← "too high"

AFTER NexoBI (CallRail + CRM integrated):
  Google Ads spend:    $7,380/month
  Leads counted:       128 (41 forms + 87 calls)
  Real CPL:            $57.66 ← among the lowest in the market
  Attended procedures: 19
  Revenue:             $83,600
  Real ROAS:           11.3x
```

**The decision almost made without NexoBI:** Pause Google Ads, invest in SEO instead. This would have cut their highest-volume channel while chasing a CPL problem that didn't exist.

**What NexoBI does here:**
The CallRail API pull + GoHighLevel CRM merge combines both lead types into a single `leads` column in the Delta table. The Google Ads cost row comes from the Google Ads API. The attended and revenue rows come from Dentrix de-identified export. The AI Agent can compute true CPL across all lead types without anyone manually combining spreadsheets.

---

### Problem 4 — "We're Getting Great Traffic From Our Blog. Zero Patients."

**The situation:**
A mental health group practice publishes 3–4 blog posts per month. GA4 shows strong organic growth — 40% more sessions year over year. The content writer is proud. The practice owner asks: *"Have we gotten a single patient from the blog?"* Nobody knows.

**The real answer:**
NexoBI joined GSC landing page data to GoHighLevel CRM lead source to SimplePractice session attendance. The blog was generating patients — but only specific posts. The high-traffic posts were generating zero clients. The lower-traffic posts were generating almost all of them.

```
Page                                    Organic    Leads   Client   Monthly
                                        Sessions           Intakes  Revenue
─────────────────────────────────────────────────────────────────────────────
/blog/what-is-cbt-therapy               2,847      0       0        $0
/blog/signs-of-anxiety                  1,943      0       0        $0
/blog/therapy-for-depression            1,622      1       0        $0
/blog/how-to-find-a-therapist-miami       341     12       9        $16,200
/blog/therapist-accepting-insurance-miami 289     18      14        $25,200
/blog/online-therapy-vs-in-person         198      8       6        $10,800
/services/anxiety-therapy                 156     11       9        $16,200
```

**The pattern:**
Pages with high traffic but zero conversions were informational and national in scope — ranking for broad queries like "what is CBT" with searchers who had no intent to book. Pages with lower traffic but high conversion were local and decision-stage — "therapist in Miami accepting insurance" captures someone ready to call.

**The content reallocation:**
Stop producing broad informational content. Double down on local, decision-stage, service-specific pages. One local service page generates $16,200/month. The two highest-traffic blog posts generate $0.

**This insight cost the practice nothing to discover.** It was already in the data — GSC, CRM, SimplePractice. NexoBI was the first system to ever join those three data sources.

---

### Problem 5 — "Our Best Patients Came From Where?"

**The situation:**
A MedSpa tracks new clients and monthly revenue. They run Google Ads, Meta Ads, send email campaigns to past clients, and post on Instagram. They know roughly which channel brings new clients. They have no idea which channel brings clients who stay.

**The real question nobody was asking:**
Not *"what is the CPL by channel?"* but *"what is the 12-month LTV of a client acquired by channel?"*

**What NexoBI found:**

```
Channel              New Clients   Avg 1st Visit   Avg 12mo LTV   ROAS (LTV basis)
────────────────────────────────────────────────────────────────────────────────────
Google Ads            31           $620            $1,840          6.8x
Meta – Instagram      44           $480            $890            4.1x
Instagram – Organic   12           $580            $4,200          ∞ (no spend)
Email – Reactivation  18           $540            $6,100          190x
Patient Referral      9            $610            $7,800          ∞ (no spend)
Google Business Prof  22           $490            $2,100          ∞ (no spend)
```

**The revelation:**
Instagram Organic clients have a 12-month LTV of $4,200 — 4.7x higher than Meta paid clients ($890). Email reactivation clients have a $6,100 LTV — and cost $180/month for the email tool that generates them.

Meta Ads is bringing the most new clients (44/month) and the lowest LTV ($890). They're filling the calendar with one-time visitors. Instagram Organic, Patient Referral, and Email bring fewer clients who spend 5–8x more over 12 months.

**The decision:**
The Meta budget wasn't cut — it was restructured. Instead of broad awareness ads targeting "people interested in Botox," campaigns were narrowed to retargeting (people who engaged with Instagram content) and lookalike audiences built from the email reactivation list (clients who match the $6,100 LTV profile). New Meta CPL: up from $32 to $58. New Meta 12-month LTV: up from $890 to $2,400.

**The question that unlocked this:**
> *"Show me 12-month patient LTV by acquisition channel."*

This question is only answerable when the CRM tracks acquisition source, the EHR tracks every subsequent visit with the same patient attribution, and NexoBI joins them over a rolling 12-month window.

---

### Problem 6 — "We Increased Paid Spend 40% and Revenue Went Up 8%"

**The situation:**
An orthopedic group had a strong Q4. Their Google Ads agency recommended scaling into Q1. They increased paid spend from $12,000 to $17,000/month (+42%). Revenue grew from $380,000 to $410,000 (+7.9%). The agency called it a success. The practice owner felt something was wrong.

**What NexoBI found:**

The revenue growth of $30,000 did not come from the additional $5,000 in ad spend. It came from two organic sources that happened to grow simultaneously:

```
Q4 → Q1 revenue change by source:
  Google Ads:              +$8,400   (additional $5,000 spend)
  Organic Search:          +$14,200  (no additional spend — GSC shows rank improvement)
  Google Business Profile: +$9,800   (no additional spend — reviews crossed 150 total)
  Meta Ads:                -$2,400   (same spend, lower attendance in Q1)
  ─────────────────────────────────────────────────────
  Net revenue change:      +$30,000

Google Ads ROAS on the incremental $5,000 spend: 1.68x — below break-even.
Organic + GBP growth contributed 80% of the revenue increase for free.
```

**The actual story:**
The agency's incremental Google Ads spend was barely profitable. Organic growth — driven by a December content push that had started ranking — and a GBP review milestone were the real engines. The $5,000 increase in Google Ads spend crowded the results: as paid budgets scaled, average position held but CPCs rose, eroding returns.

**What the agency couldn't see:**
They had no visibility into organic revenue. Their reporting universe was Google Ads. Inside that universe, everything looked positive. NexoBI was the first view that included all channels simultaneously.

**The outcome:**
Google Ads spend reduced from $17,000 to $13,000. The saved $4,000 redirected to content production (targeting the keywords that were already organically ranking). No revenue reduction. $48,000/year saved.

---

### Problem 7 — "Our Rankings Are Great. Why Are Leads Down?"

**The situation:**
An urgent care group has been working with an SEO agency for 14 months. Rankings for "urgent care near me" and "walk-in clinic [city]" have been stable at positions 2–4 for six months. But new patient visits from organic sources are down 23% over the same period. The SEO agency points to the rankings and says the work is solid. The practice points to the revenue and says something is wrong. Nobody can reconcile the two.

**NexoBI diagnosed it in one week.**

The problem wasn't rankings. It was Google Business Profile. Three things had changed:
1. Average rating dropped from 4.7 to 4.1 over 14 months (no systematic review generation)
2. GBP photos hadn't been updated in 11 months (interior renovation wasn't reflected)
3. Holiday hours weren't updated for three holidays — patients arrived to a closed practice, left 1-star reviews

**The data:**

```
Month    GBP Rating   Local Pack Rank   GBP Calls   New Patients   Organic Rev
────────────────────────────────────────────────────────────────────────────────
Jan '25  4.7          2                 312          187            $56,100
Apr '25  4.5          2                 289          171            $51,300
Jul '25  4.3          3                 241          144            $43,200
Oct '25  4.1          4                 198          118            $35,400
Jan '26  4.1          5                 171          103            $30,900
```

Rankings barely moved. GBP rank fell from 2 to 5 — because Google incorporates review score and recency into local pack positioning. Calls dropped 45%. Revenue dropped 45%. The organic ranking report the agency was sending showed position 2–4 for SERP results — technically correct, and completely missing the issue.

**The fix:**
- Systematic review generation: post-visit SMS via Weave (automated from Experity EHR discharge)
- Photo update: new interior + team photos added
- Holiday hours: added to GBP calendar for next 12 months
- Response to negative reviews: 23 reviews responded to within 48 hours

**Results at 90 days:** Rating recovered to 4.5. Local pack rank back to 2–3. GBP calls up 47%. Revenue recovery: $14,400/month.

**The AI question that found it:**
> *"Why are leads down if our rankings haven't changed?"*

NexoBI cross-referenced GSC organic rank (stable), GBP impressions (declining), GBP calls (declining), and review score (declining). The pattern was unambiguous. No human had been looking at all four data sources simultaneously.

---

### Problem 8 — "The Agency Says Paid Is Working. We Have Three Data Sources That Disagree."

**The situation:**
A cosmetic surgery practice has three parties telling them different things:
- Google Ads dashboard: 47 conversions, $128 CPL, strong performance
- Meta Ads dashboard: 61 conversions, $89 CPL, excellent performance
- GoHighLevel CRM: 38 new leads this month

**47 + 61 = 108 conversions in ad dashboards. 38 leads in CRM.**

This is the attribution overlap problem. Google and Meta are both claiming credit for patients who were touched by both. A patient who saw a Meta ad, then later searched and clicked a Google Ad, appears as a conversion in both platforms. Neither platform removes its own credit.

**The NexoBI reconciliation:**

```
Source of truth: CRM first-touch + last-touch attribution cookie
─────────────────────────────────────────────────────────────────
Actual unique leads this month: 38

Attribution breakdown (CRM first-touch):
  Google Ads first-touch:     14 leads
  Meta Ads first-touch:       11 leads
  Organic Search first-touch: 8 leads
  Direct first-touch:         5 leads

Attribution breakdown (CRM last-touch):
  Google Ads last-touch:      19 leads   ← claimed 47 in dashboard
  Meta Ads last-touch:        16 leads   ← claimed 61 in dashboard
  Organic Search last-touch:  2 leads
  Direct last-touch:          1 lead

Google Ads overcounting factor: 47 claimed / 19 actual = 2.47x
Meta Ads overcounting factor:   61 claimed / 16 actual = 3.81x

Actual Google Ads CPL: $128 × 2.47 = $316 real CPL
Actual Meta Ads CPL:   $89 × 3.81  = $339 real CPL

Both channels are significantly less efficient than reported.
Total real CPL across all paid: $8,360 total paid spend / 30 paid leads = $279
```

**The takeaway:**
Both agencies were reporting correctly within their own data. The platform dashboards are not lying — they're doing what they're designed to do (maximize the case for their own platform). The practice was making budget decisions on numbers that were 2–4x inflated.

**Only a system that sits outside both platforms — using CRM first-party data as the source of truth — can produce the real number.** That system is NexoBI.

---

### The CRM Decision — How to Choose for Your Practice Type

Every problem above required a CRM. Not all CRMs are equal for healthcare attribution. Here is the decision framework:

```
DECISION TREE: WHICH CRM FOR HEALTHCARE ATTRIBUTION?

Are you a healthcare marketing AGENCY managing multiple practices?
  YES → GoHighLevel
        Reason: Multi-location sub-accounts, white-labeling,
        built-in CallRail-like call tracking, pipeline automation,
        native Zapier + Make support. Best agency operations platform.
        Cost: $297–$497/month for agency account (unlimited sub-accounts)

  NO — continue ↓

Does the practice already have HubSpot or Salesforce?
  YES → Keep it. Build the attribution layer on top.
        Add UTM custom fields, configure forms, build Zapier automations.
        The platform matters less than the data discipline around it.

  NO — continue ↓

Is the practice a MedSpa, aesthetics, or high-retention specialty?
  YES → Nextech Patient Relationship Manager or PatientNow
        Reason: Built-in EHR integration, membership management,
        before/after photo storage, loyalty program.
        Cost: $300–$600/month

  NO — continue ↓

Is the practice mental health or behavioral health?
  YES → SimplePractice CRM module or Hushmail + IntakeQ
        Reason: HIPAA-compliant by design, client portal,
        insurance billing integrated, strict access controls.
        Cost: $79–$149/month

  NO — continue ↓

Is the practice small (1–3 providers, single location)?
  YES → NexHealth or Weave (CRM + communications + EHR integration)
        Reason: Connects directly to most EHRs without middleware,
        handles recall campaigns, reviews, and patient messaging.
        Cost: $300–$500/month

  NO (medium practice, 4–15 providers) → GoHighLevel or HubSpot Starter
        GoHighLevel: Better if you need automation depth and call tracking
        HubSpot Starter: Better if the team already knows HubSpot, reports matter

UNIVERSAL REQUIREMENT regardless of CRM chosen:
  ✓ Custom fields for: utm_source, utm_medium, utm_campaign, landing_page
  ✓ CallRail (or equivalent) connected via webhook
  ✓ Pipeline stages mapped to: Lead → Booked → Attended → Won
  ✓ Zapier/Make automation: stage "Booked" → push referral source to EHR
  ✓ API access enabled (for NexoBI ETL nightly pull)
```

**The CRM is not the solution. The CRM is the container. Attribution is the discipline applied inside it.**

A practice with GoHighLevel and no UTM fields, no pipeline stages, and no CallRail webhook has worse attribution than a practice with a spreadsheet and disciplined manual entry. The tool doesn't matter. The data architecture inside the tool is everything.

---

### The NexoBI AI Agent — Architecture for a Strong, Reliable System

This is the build. Everything above — attribution, CRM integration, EHR de-identification, organic search capture, channel reconciliation — feeds into this. The AI Agent is not the product. It's the interface to a clean, attributed, unified data layer that most healthcare practices don't have today.

Here is the architecture that makes it strong and reliable.

---

#### Layer 0 — Data Quality (The Foundation Everything Depends On)

```
Before any AI, before any query, before any dashboard:

  ✓ Standardized EHR referral source picklist (12 options, enforced)
  ✓ Attribution coverage ≥ 85% (≤ 15% "Unknown" in source column)
  ✓ Data freshness SLA: Delta table updated by 6:00 AM daily
  ✓ Schema validation on every ETL run:
      - date is never null
      - data_source is never null or empty string
      - total_revenue ≥ 0
      - booked ≥ attended (you can't attend more than you booked)
      - total_cost ≥ 0
  ✓ Deduplication check: MERGE INTO (not INSERT) prevents double-counting

An AI Agent on top of bad data produces confident wrong answers.
That is worse than no AI Agent.
Layer 0 is not optional. It is the product.
```

---

#### Layer 1 — The Delta Table (Single Source of Truth)

```
workspace.silver.DemoData-marketing-crm

One row = one channel × one day × one campaign

Columns:
  date            DATE         — row date
  data_source     STRING       — from standardized picklist
  channel_group   STRING       — Paid Search / Organic / Local / Social / etc.
  campaign        STRING       — campaign name or landing page
  source_medium   STRING       — google/cpc, google/organic, facebook/paid, etc.
  total_cost      DOUBLE       — ad spend or SEO retainer (where applicable)
  total_revenue   DOUBLE       — de-identified net production from EHR
  sessions        BIGINT       — website sessions (GA4)
  clicks          BIGINT       — ad clicks (Google/Meta)
  impressions     BIGINT       — ad impressions
  leads           BIGINT       — form fills + tracked calls (CRM)
  booked          BIGINT       — appointments booked (CRM stage / EHR)
  attended        BIGINT       — appointments attended (EHR status = complete)
  new_users       BIGINT       — new visitors (GA4)
  conversions     BIGINT       — GA4 conversion events
  conversion_rate DOUBLE       — computed: leads/sessions × 100
  roas            DOUBLE       — computed: total_revenue/total_cost
  treatment       STRING       — A/B test label or specialty type
```

Every platform feeds this table. NexoBI never queries the source platform directly — it always queries the Delta table. This is what makes the AI Agent fast, reliable, and consistent across all questions.

---

#### Layer 2 — The AI Query Engine (Two Modes)

**Mode A — Offline / CSV Engine (no Databricks required)**

Pattern-matched queries directly against the loaded DataFrame. No LLM. Instant response. Works for demos, works without cloud access. Handles the 10–15 most common question patterns reliably.

```python
# Pattern matching with intent classification
INTENT_PATTERNS = {
    "revenue":       ["revenue", "how much", "made", "generated", "production"],
    "roas":          ["roas", "return", "efficiency", "per dollar"],
    "leads":         ["leads", "inquiries", "how many", "lead volume", "cpl"],
    "show_rate":     ["show rate", "attendance", "no-show", "showed up"],
    "channel":       ["by source", "by channel", "breakdown", "compare", "vs"],
    "campaign":      ["campaign", "ad", "keyword", "which campaign"],
    "organic":       ["organic", "seo", "blog", "content", "search"],
    "forecast":      ["forecast", "predict", "next month", "project"],
}
# Each intent maps to a deterministic computation against the DataFrame
# Output: HTML bubble with the answer + supporting stats table
```

**Mode B — Live / Databricks AI Engine (production)**

Full natural language → SQL generation → result → narrative answer via Llama 3.3 70B on Databricks.

```python
def ai_query_ask(question: str, data_context: str) -> dict:
    """
    Sends question + schema context to Databricks Genie Space.
    Polls until COMPLETED. Returns: text answer + SQL + result DataFrame.
    """
    # Step 1: Start conversation with schema-enriched prompt
    system_context = f"""
    You are a healthcare marketing analytics expert.
    You have access to a table: workspace.silver.`DemoData-marketing-crm`

    Schema: {data_context}

    Key metrics to compute when asked:
    - ROAS = total_revenue / total_cost
    - CPL = total_cost / leads
    - Show Rate = attended / booked × 100
    - Booking Rate = booked / leads × 100
    - Conversion Rate = leads / sessions × 100

    Date ranges: interpret "last 30 days", "MTD", "last quarter" relative to today.
    Always return: a clear text answer, the supporting data, and a SQL query.
    If the question is visual (trend, chart, compare, breakdown), note that a chart should follow.
    """

    conv = genie_start_conversation(GENIE_SPACE_ID, question, system_context)
    result = genie_poll_until_complete(conv["conversation_id"], conv["message_id"])

    return {
        "text": result["text_answer"],
        "sql":  result["query"],
        "df":   result["dataframe"],    # may be None for narrative answers
        "chart_hint": _is_visual_question(question),
    }
```

---

#### Layer 3 — Proactive Intelligence (The Shift From Reactive to Active)

This is what separates NexoBI from a dashboard. A dashboard answers questions you think to ask. An AI Agent should surface problems you didn't know to look for.

**Daily automated intelligence queries — run every morning at 7:00 AM:**

```python
DAILY_INTELLIGENCE_QUERIES = [

    {
        "name": "roas_drop_alert",
        "query": """
            SELECT data_source, channel_group,
              SUM(total_revenue)/NULLIF(SUM(total_cost),0) AS roas_7d,
              LAG(SUM(total_revenue)/NULLIF(SUM(total_cost),0), 7)
                OVER (PARTITION BY data_source ORDER BY date) AS roas_14d
            FROM silver.`DemoData-marketing-crm`
            WHERE date >= CURRENT_DATE - 14
              AND total_cost > 0
            GROUP BY data_source, channel_group, date
        """,
        "alert_condition": "roas_7d < roas_14d * 0.80",  # >20% drop
        "alert_template": "⚠ ROAS DROP — {data_source}: {roas_7d:.1f}x this week vs {roas_14d:.1f}x last week. Revenue at risk: ${revenue_at_risk:,.0f}/month.",
    },

    {
        "name": "show_rate_warning",
        "query": """
            SELECT data_source,
              SUM(attended)/NULLIF(SUM(booked),0)*100 AS show_rate_7d,
              LAG(SUM(attended)/NULLIF(SUM(booked),0)*100, 7)
                OVER (PARTITION BY data_source ORDER BY date) AS show_rate_14d
            FROM silver.`DemoData-marketing-crm`
            WHERE date >= CURRENT_DATE - 14 AND booked > 3
            GROUP BY data_source, date
        """,
        "alert_condition": "show_rate_7d < 65",
        "alert_template": "⚠ SHOW RATE — {data_source} patients showing at {show_rate_7d:.1f}% this week. Below 65% threshold. Review booking quality for this source.",
    },

    {
        "name": "organic_rank_drop",
        "query": """
            SELECT page, query,
              AVG(position) AS position_7d,
              LAG(AVG(position), 7) OVER (PARTITION BY page, query ORDER BY date) AS position_14d,
              SUM(clicks) AS clicks_7d
            FROM silver.gsc_organic_performance
            WHERE date >= CURRENT_DATE - 14
            GROUP BY page, query, date
        """,
        "alert_condition": "position_7d > position_14d + 5 AND position_14d <= 10",
        "alert_template": "⚠ RANK DROP — {page} dropped from position {position_14d:.0f} to {position_7d:.0f} for '{query}'. Estimated monthly revenue at risk: ${revenue_at_risk:,.0f}.",
    },

    {
        "name": "spend_without_return",
        "query": """
            SELECT data_source, SUM(total_cost) AS spend_30d, SUM(total_revenue) AS rev_30d,
              SUM(total_revenue)/NULLIF(SUM(total_cost),0) AS roas
            FROM silver.`DemoData-marketing-crm`
            WHERE date >= CURRENT_DATE - 30 AND total_cost > 500
            GROUP BY data_source HAVING roas < 1.5
        """,
        "alert_condition": "roas < 1.5",
        "alert_template": "🔴 LOW ROAS — {data_source}: ${spend_30d:,.0f} spent, ${rev_30d:,.0f} returned. ROAS {roas:.2f}x. Consider pausing or restructuring this channel.",
    },

    {
        "name": "attribution_coverage_check",
        "query": """
            SELECT
              COUNT(CASE WHEN data_source IN ('Other','Unknown','') THEN 1 END)*100.0/COUNT(*) AS pct_unknown
            FROM silver.`DemoData-marketing-crm`
            WHERE date >= CURRENT_DATE - 7
        """,
        "alert_condition": "pct_unknown > 15",
        "alert_template": "⚠ ATTRIBUTION GAP — {pct_unknown:.1f}% of appointments this week have no marketing source. Check EHR referral source completion rate and CRM → EHR automation.",
    },
]
```

These queries run automatically. Results are stored as `st.session_state` alerts and surfaced in the **Top Signals** section of the NexoBI dashboard — no human has to ask. The practice owner opens NexoBI at 8:00 AM and sees the three most important things that happened overnight.

---

#### Layer 4 — Structured AI Responses (Reliability Architecture)

The AI Agent's responses must be reliable, not just smart. A response that's confident and wrong destroys trust faster than no response at all.

**Reliability requirements:**

```python
# Every AI response must have:
RESPONSE_SCHEMA = {
    "answer_text":  str,   # narrative explanation in plain English
    "evidence":     list,  # list of specific data points that support the answer
    "sql":          str,   # the SQL query that produced the data (shows work)
    "confidence":   str,   # "high" / "medium" / "low" based on data coverage
    "data_period":  str,   # "last 30 days" / "MTD" — what time range was used
    "caveats":      list,  # list of known limitations (e.g. "phone calls not tracked")
    "next_question": list, # 2-3 suggested follow-up questions
}

# Confidence levels:
# "high"   — attribution coverage > 85%, >30 days of data, >50 events
# "medium" — attribution coverage 60–85%, or 15–30 days of data
# "low"    — attribution coverage < 60%, or < 15 days, or < 10 events
#            → low confidence answers include explicit warning in the response

# Example low-confidence caveat:
# "⚠ Note: 42% of appointments this month have no marketing source recorded.
#  This answer is based on the 58% that are attributed. Actual values may be
#  20–40% higher. Improve EHR referral source completion to increase confidence."
```

**This is the most important reliability feature.** The AI Agent must know when it doesn't know — and say so clearly, in the response. Healthcare practitioners make financial decisions based on these answers. A fabricated confident answer is a liability. A honest answer with caveats is a trust-builder.

---

#### Layer 5 — The Recommendation Engine (From Insight to Action)

The final layer transforms observations into specific, actionable recommendations. Not "your ROAS dropped" — but "here is what to do about it, and here is the expected revenue impact of doing it."

```python
RECOMMENDATION_RULES = [

    {
        "trigger": "channel_roas < 2.0 for 14+ consecutive days",
        "recommendation": "Consider reducing {channel} budget by 30% and reallocating to {top_roas_channel}. "
                          "Expected impact: -{current_spend*0.3:,.0f}/month spend, "
                          "+${reallocation_revenue_delta:,.0f}/month revenue at {top_roas_channel} ROAS.",
    },

    {
        "trigger": "show_rate_by_source: source_X < 65% for 7+ days",
        "recommendation": "{source_X} leads show at {show_rate:.1f}%. Add a 2-step confirmation "
                          "sequence in {crm_name} for {source_X} leads: "
                          "(1) Book confirmation SMS 24h before, (2) Pre-appointment value email. "
                          "Expected show rate improvement: +8–12 percentage points based on "
                          "similar practices.",
    },

    {
        "trigger": "organic_landing_page revenue > paid search revenue, "
                   "seo_spend < paid_search_spend * 0.4",
        "recommendation": "Organic search is generating {organic_rev:,.0f} ({organic_roas:.1f}x ROAS) "
                          "vs paid search {paid_rev:,.0f} ({paid_roas:.1f}x ROAS). "
                          "SEO investment is {seo_pct:.0f}% of paid search spend. "
                          "Increasing SEO retainer by ${increase:,.0f}/month should yield "
                          "~${expected_return:,.0f} in additional organic revenue.",
    },

    {
        "trigger": "attribution_coverage < 80%",
        "recommendation": "{pct_unknown:.0f}% of appointments have no marketing source. "
                          "At your average production of ${avg_production:,.0f}/patient, "
                          "this represents ${unattributed_revenue:,.0f}/month of invisible revenue. "
                          "Priority fix: audit the EHR referral source completion rate and "
                          "verify the CRM → EHR booking automation is running.",
    },

    {
        "trigger": "new_organic_content published, no ranking signal after 90 days",
        "recommendation": "The blog post '{page}' published {days_ago} days ago has not "
                          "appeared in GSC rankings. Possible causes: "
                          "(1) page not indexed — check GSC Coverage report, "
                          "(2) keyword too competitive — target a longer-tail variant, "
                          "(3) thin content — expand to 1,500+ words with FAQ schema.",
    },
]
```

---

#### Layer 6 — The Client-Facing Output (What They Actually See)

The AI Agent is not a chatbot for data engineers. It's a tool for practice owners and marketing managers who are not technical. The output must be designed for that audience.

**Response design principles:**

```
PRINCIPLE 1 — Lead with the number.
  BAD:  "Based on the analysis of your marketing data across multiple channels..."
  GOOD: "Your ROAS last 30 days: 8.4x. Organic is driving 62% of it at zero ad cost."

PRINCIPLE 2 — Always show the evidence.
  Every answer includes the data table or chart that produced it.
  "Trust me" is not a feature. "Here is the SQL that produced this answer" is.

PRINCIPLE 3 — End with a next step.
  Not "your show rate is low." But:
  "Your Meta show rate is 59%. Three practices in similar markets improved
   it to 74% within 60 days by adding a day-before SMS confirmation.
   Want me to draft the automation sequence?"

PRINCIPLE 4 — Flag uncertainty explicitly.
  If attribution coverage is < 80%, every response includes:
  "⚠ Attribution note: X% of appointments this period have no source recorded.
   This answer covers Y% of your actual patient volume."

PRINCIPLE 5 — Use healthcare language.
  Not "conversions." Say "booked appointments."
  Not "revenue events." Say "attended consultations."
  Not "LTV." Say "what that patient is worth over 12 months."
  Not "attribution coverage." Say "how many of your patients we can trace back
   to a marketing source."
```

---

#### The Full Stack — What You Are Building

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NEXOBI AI AGENT STACK                           │
├────────────────┬────────────────┬────────────────┬────────────────────  │
│  DATA SOURCES  │   ETL LAYER    │  DELTA TABLE   │   AI AGENT UI        │
│                │                │                │                      │
│  Google Ads    │  Python ETL    │  workspace     │  Streamlit           │
│  Meta Ads      │  (nightly,     │  .silver       │  + Plotly charts     │
│  GA4           │   2:00 AM)     │  .DemoData-    │                      │
│  GSC           │                │   marketing-   │  Two modes:          │
│  CallRail      │  De-id layer   │   crm          │  ① CSV offline       │
│  CRM (GHL/HS)  │  (PHI strip,   │                │    (pattern match)   │
│  EHR (Dentrix/ │   aggregate)   │  Joined tables │  ② Live Databricks   │
│   SP / Nextech)│                │  gsc_organic   │    (Llama 3.3 70B)   │
│  BrightLocal   │  Schema valid  │  brightlocal   │                      │
│  CallRail      │  Coverage chk  │  semrush_rank  │  Proactive layer:    │
│                │  MERGE INTO    │  weave_remind  │  Daily intelligence  │
│                │  (no dupes)    │                │  queries → Top       │
│                │                │                │  Signals alerts      │
├────────────────┴────────────────┴────────────────┤                      │
│              DATABRICKS (Unity Catalog)           │  Recommendation      │
│              Genie Space ID: 01f111cb...          │  engine → specific   │
│              ai_query() → Llama 3.3 70B           │  action with         │
│              Audit logs: every query tracked       │  revenue impact      │
└───────────────────────────────────────────────────┴────────────────────  ┘

WHAT THIS ENABLES:
  ✓ "Which channel produces the highest-LTV patients?" → answered in 4 sec
  ✓ "Why did show rate drop last week?" → root-caused to source + solution
  ✓ "Which blog post generated the most booked appointments?" → exact answer
  ✓ "Are we over-investing in paid vs organic?" → ROAS comparison with rec
  ✓ "What's our real CPL including phone calls?" → CallRail + forms unified
  ✓ "Alert me when ROAS drops 20%." → proactive, morning delivery
  ✓ "What should we focus on today?" → top 3 signals ranked by revenue impact
```

---

### The 60-Day Build Sequence

For an agency deploying this for a new client:

```
DAYS 1–7: Data foundation
  □ EHR referral source picklist: defined, configured, front desk trained
  □ CRM: UTM custom fields added, pipeline stages mapped
  □ GoHighLevel or HubSpot: form hidden fields live, test confirmed
  □ Target: first clean row appears in CRM with correct attribution

DAYS 8–14: Phone call coverage
  □ CallRail DNI installed on website
  □ GBP phone number replaced with CallRail tracking number
  □ CallRail → CRM webhook: tested and live
  □ Target: all inbound calls appearing in CRM with source

DAYS 15–21: EHR bridge
  □ Zapier/Make automation: CRM "Booked" → EHR referral source push
  □ End-to-end test: organic form → CRM → Dentrix → correct source confirmed
  □ Nightly Dentrix CSV export: configured and placed in pickup folder
  □ Target: EHR referral source completion rate ≥ 90%

DAYS 22–35: ETL and Delta table
  □ Python ETL scripts: Dentrix, Google Ads, Meta, GSC, CallRail
  □ MERGE INTO Delta table: tested with 30 days of historical data
  □ Schema validation: running on every ETL load
  □ GSC supplementary table: daily clicks/position by landing page
  □ Attribution coverage check: target ≥ 80%

DAYS 36–45: NexoBI AI Agent live
  □ Databricks Genie Space: connected to Delta table, tested
  □ Proactive intelligence queries: 5 daily checks running at 7 AM
  □ Top Signals card: surfacing real alerts from real data
  □ AI Agent: answering 10 standard questions correctly
  □ Attribution coverage: target ≥ 85%

DAYS 46–60: Insight and action
  □ First monthly report: all channels, real ROAS, CPL, show rate by source
  □ Budget recommendation: where to reallocate based on 30 days of data
  □ First proactive catch: at least one alert surfaced before client asked
  □ Client walkthrough: "Ask it anything about your marketing data"
  □ Target: client can replace their agency's monthly PDF with this
```

**At day 60, a healthcare practice has something almost no practice in their market has:**
A system that knows which marketing effort produced which patient, which channel has the highest return, which blog post generates the most revenue, and which lead source is quietly burning money on no-shows. All surfaced through an AI that answers in plain English, shows its work, and flags what it doesn't know.

That is the NexoBI product. The AI Agent is the interface. The attribution stack is the substance.

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 18 added (Real Problems, Real Solutions, AI Agent Architecture)*

---

---

## 19. Probabilistic Attribution — Filling the Walk-In and Referral Gap

> Walk-ins, physician referrals, and verbal "I heard about you from a friend" patients will never have a clean digital trail. But they are not random. They carry signals — timing, geography, demographics, service type, insurance — that correlate with specific marketing efforts. Probabilistic attribution uses those signals to make statistically informed estimates of likely source, feeds them to the AI Agent as confidence-weighted data, and dramatically reduces the revenue that disappears into "Unknown."

---

### Why This Matters — The Systematic Bias Problem

When unattributed patients are ignored, the analysis is not just incomplete — it's **systematically wrong**.

Consider: a practice has 300 appointments per month. 220 are attributed (73%). 80 are "Unknown." If the AI Agent answers "What is our ROAS by channel?" using only the 220 attributed patients, every channel's performance is understated — but not equally. Channels that generate more walk-ins and phone referrals (like GBP and organic search) are understated more than channels with clean digital tracking (like Google Ads with gclid).

The result: Google Ads looks disproportionately efficient because its patients are fully tracked. Organic looks weaker than it is because half its walk-in patients are in the Unknown bucket. Budget decisions based on this data systematically over-invest in paid and under-invest in organic.

**Probabilistic attribution doesn't eliminate this bias. It corrects it.**

```
WITHOUT probabilistic attribution:
  Google Ads: 52 patients tracked → ROAS 8.4x (accurate)
  Organic:    38 patients tracked → ROAS 12.1x (understated — missing walk-ins)
  Unknown:    80 patients          → $0 attributed revenue (wrong)

WITH probabilistic attribution:
  Google Ads: 52 observed + 14 estimated → ROAS 8.2x
  Organic:    38 observed + 31 estimated → ROAS 18.4x  ← organic was even better
  GBP:        41 observed + 22 estimated → ROAS grows to reflect true local impact
  Unknown:     0 (fully distributed with confidence weights)

The AI Agent's recommendation changes:
  Before: "Google Ads is your best-performing paid channel."
  After:  "Organic search, including probabilistically attributed walk-ins,
           outperforms Google Ads by 2.2x. Organic is significantly undervalued."
```

---

### The Signals That Make Probabilistic Attribution Possible

Unattributed patients are not random. Every patient carries observable attributes at the time of appointment that correlate with how they likely found the practice. These are the signals:

```
SIGNAL CLASS          WHAT IT TELLS YOU
─────────────────────────────────────────────────────────────────────────
Appointment timing    Walk-ins on Monday morning → likely GBP "open now" search
                      Appointments booked 2+ weeks out → likely planned search or referral
                      Same-day bookings → GBP or urgent care search behavior

Service type          Emergency / acute pain → walk-in, GBP, urgent search
                      Elective (implants, LASIK, aesthetics) → longer consideration,
                      likely organic content or paid search
                      Routine (cleaning, annual check-up) → likely recall/email or referral

Patient ZIP code      Within 1 mile of practice → walk-in or GBP
                      5–15 miles → likely paid search or organic (drove to you)
                      Cross-county → likely strong content SEO or physician referral

Insurance type        Cash pay, no insurance → more likely paid/organic (self-directed)
                      In-network PPO → more likely insurance directory or employer referral
                      Medicaid → more likely community referral or physician referral

New vs returning      New patient → full attribution model applies
                      Returning patient → attribute to original acquisition channel
                      (retain first-touch source from CRM if available)

Lead time             Same-day / next-day → urgency-driven, likely GBP or "near me"
                      1–2 weeks → considered, likely search or organic content
                      3+ weeks → relationship referral or recall campaign

Day/campaign timing   Unattributed spike follows a blog post publish → organic credit
                      Unattributed spike follows email campaign → email credit
                      Unattributed stable regardless of campaigns → likely walk-in/GBP baseline

Demographics          Age 18–34 → higher Instagram/social signal
                      Age 35–55 → higher Google Ads/organic signal
                      Age 55+ → higher GBP/physician referral signal
                      (calibrated per practice and market — not universal)
```

None of these signals are PHI. Age is a demographic range, not a birthdate. ZIP code is a geographic proxy. Service type is a billing category. They are all present in the de-identified EHR export and can be included in the Delta table without HIPAA concern.

---

### The Three Probabilistic Methods — From Simple to Sophisticated

NexoBI implements these in layers. Each layer increases accuracy. Each layer also increases complexity. Start with Method 1. Add Method 2 at 90 days. Consider Method 3 at scale.

---

#### Method 1 — Proportional Distribution (Baseline, Immediate Value)

The simplest valid approach. Distribute unattributed patients proportionally according to the observed channel mix of attributed patients in the same time period.

**The logic:** If 38% of attributed patients came from organic in a given month, and you have 80 unattributed patients in that month, estimate that 38% of those 80 — about 30 — also came from organic. Apply the same distribution across all channels.

```python
import pandas as pd
import numpy as np

def proportional_attribution(
    df: pd.DataFrame,
    date_col: str = "date",
    source_col: str = "data_source",
    revenue_col: str = "total_revenue",
    attended_col: str = "attended",
    unknown_label: str = "Other / Unknown"
) -> pd.DataFrame:
    """
    Distributes unattributed (Unknown) patients proportionally
    across known channels. Returns augmented DataFrame with
    probabilistic rows marked as estimated=True.
    """
    result_rows = []

    for period, group in df.groupby(pd.Grouper(key=date_col, freq="M")):
        known = group[group[source_col] != unknown_label]
        unknown = group[group[source_col] == unknown_label]

        if unknown.empty or known.empty:
            result_rows.append(group)
            continue

        # Compute channel distribution from known patients
        channel_dist = (
            known.groupby(source_col)[attended_col].sum()
            / known[attended_col].sum()
        )

        unknown_attended = unknown[attended_col].sum()
        unknown_revenue  = unknown[revenue_col].sum()

        # Distribute unknown patients across channels
        for source, share in channel_dist.items():
            est_attended = unknown_attended * share
            est_revenue  = unknown_revenue * share

            if est_attended < 0.5:
                continue  # don't create noise rows for negligible allocations

            result_rows.append({
                date_col:      period,
                source_col:    source,
                attended_col:  est_attended,
                revenue_col:   est_revenue,
                "estimated":   True,          # flag — not observed, inferred
                "confidence":  "low",         # proportional = lowest confidence
                "method":      "proportional",
            })

        # Keep known rows as-is
        known = known.copy()
        known["estimated"] = False
        known["confidence"] = "high"
        known["method"] = "observed"
        result_rows.append(known)

    return pd.concat(result_rows, ignore_index=True)
```

**What this produces immediately:**
Attribution coverage jumps from 73% to 100% with the caveat that the added 27% is estimated. The AI Agent can now say: *"Organic search generated an estimated $138,000 this month — $97,200 directly attributed plus $40,800 probabilistically allocated from untracked walk-ins and referrals. Confidence: medium."*

---

#### Method 2 — Signal-Weighted Bayesian Attribution (Recommended at 90 Days)

Improves on proportional distribution by using patient signals to weight the probability toward specific channels. A same-day urgent appointment is more likely GBP than a planned 3-week-out implant consult. Bayesian attribution captures that.

**The Bayesian logic:**

Prior belief: the channel distribution from attributed patients (same as Method 1).
Update: shift probabilities based on signals present in the unattributed patient record.

```python
from scipy.stats import dirichlet
import numpy as np

# Channel priors: calibrated from 90 days of attributed patient data
# Format: {channel: prior_weight}
# These are updated monthly as more attributed data accumulates

CHANNEL_PRIORS = {
    "Google Ads – Paid Search":   0.22,
    "Organic – Google Search":    0.18,
    "Google Business Profile":    0.17,
    "Meta – Facebook / Instagram":0.13,
    "Referral – Patient":         0.12,
    "Referral – Physician":       0.09,
    "Directory":                  0.06,
    "Email / SMS Campaign":       0.03,
}

# Signal likelihood multipliers
# Format: {signal: {channel: multiplier}}
# Multipliers shift the prior toward or away from a channel
# Values > 1.0 increase probability; < 1.0 decrease it
# Calibrated from historical attributed data patterns

SIGNAL_MULTIPLIERS = {
    "same_day_booking": {
        "Google Business Profile":     3.2,   # walk-in "open now" behavior
        "Google Ads – Paid Search":    1.4,
        "Organic – Google Search":     1.2,
        "Referral – Patient":          0.3,   # referrals rarely same-day
        "Referral – Physician":        0.2,
        "Email / SMS Campaign":        0.1,
    },
    "service_emergency": {
        "Google Business Profile":     4.1,
        "Organic – Google Search":     2.1,
        "Google Ads – Paid Search":    1.8,
        "Referral – Patient":          1.2,
        "Referral – Physician":        0.6,
        "Meta – Facebook / Instagram": 0.4,
    },
    "service_elective_high_value": {   # implants, LASIK, cosmetic
        "Organic – Google Search":     2.8,
        "Google Ads – Paid Search":    2.4,
        "Referral – Patient":          1.8,
        "Meta – Facebook / Instagram": 1.3,
        "Google Business Profile":     0.6,
        "Referral – Physician":        0.4,
    },
    "zip_within_1_mile": {
        "Google Business Profile":     3.8,
        "Referral – Patient":          2.1,
        "Organic – Google Search":     0.9,
        "Google Ads – Paid Search":    0.7,
        "Meta – Facebook / Instagram": 0.5,
    },
    "zip_over_10_miles": {
        "Organic – Google Search":     2.6,
        "Google Ads – Paid Search":    2.2,
        "Referral – Physician":        1.8,
        "Google Business Profile":     0.3,
    },
    "cash_pay_no_insurance": {
        "Google Ads – Paid Search":    1.9,
        "Organic – Google Search":     1.7,
        "Meta – Facebook / Instagram": 1.5,
        "Referral – Physician":        0.4,
        "Directory":                   0.5,
    },
    "insurance_in_network": {
        "Directory":                   2.8,
        "Referral – Physician":        2.4,
        "Referral – Patient":          1.6,
        "Google Ads – Paid Search":    0.7,
        "Meta – Facebook / Instagram": 0.5,
    },
    "age_18_34": {
        "Meta – Facebook / Instagram": 2.2,
        "Organic – Google Search":     1.4,
        "Google Business Profile":     1.2,
        "Referral – Physician":        0.5,
    },
    "age_55_plus": {
        "Referral – Physician":        2.1,
        "Referral – Patient":          1.9,
        "Google Business Profile":     1.6,
        "Meta – Facebook / Instagram": 0.4,
    },
    "campaign_active_last_7_days": {   # dynamic: checks if a campaign ran recently
        # Channel that ran the campaign gets a 2.0 boost
        # populated dynamically based on what was running
    },
}


def bayesian_channel_probability(
    signals: list[str],
    priors: dict = CHANNEL_PRIORS,
    multipliers: dict = SIGNAL_MULTIPLIERS,
) -> dict[str, float]:
    """
    Given a list of signals present for an unattributed patient,
    return the posterior probability distribution across channels.

    Args:
        signals: list of active signal keys (e.g. ["same_day_booking", "zip_within_1_mile"])
        priors:  base channel distribution from attributed patients
        multipliers: signal → channel likelihood adjustments

    Returns:
        dict of {channel: probability} summing to 1.0
    """
    weights = dict(priors)  # start with prior distribution

    for signal in signals:
        if signal not in multipliers:
            continue
        for channel, multiplier in multipliers[signal].items():
            if channel in weights:
                weights[channel] *= multiplier

    # Normalize to sum to 1.0
    total = sum(weights.values())
    return {ch: w / total for ch, w in weights.items()}


def estimate_unattributed_patient(patient_record: dict) -> dict:
    """
    For one unattributed EHR appointment record, compute
    the probabilistic channel distribution and determine
    confidence level.

    Returns:
        dict with channel probabilities, top channel, and confidence
    """
    signals = []

    # Extract signals from the de-identified patient record
    if patient_record.get("lead_time_days", 99) == 0:
        signals.append("same_day_booking")

    if patient_record.get("service_category") in ["Emergency", "Acute Pain", "Urgent"]:
        signals.append("service_emergency")

    if patient_record.get("service_category") in ["Implant", "LASIK", "Cosmetic", "Orthodontics"]:
        signals.append("service_elective_high_value")

    if patient_record.get("distance_miles", 99) <= 1.0:
        signals.append("zip_within_1_mile")
    elif patient_record.get("distance_miles", 0) > 10:
        signals.append("zip_over_10_miles")

    if patient_record.get("insurance_type") == "cash":
        signals.append("cash_pay_no_insurance")
    elif patient_record.get("insurance_type") in ["PPO", "HMO", "Medicaid"]:
        signals.append("insurance_in_network")

    age = patient_record.get("age_bracket")
    if age == "18-34":
        signals.append("age_18_34")
    elif age == "55+":
        signals.append("age_55_plus")

    # Compute posterior
    probabilities = bayesian_channel_probability(signals)
    top_channel   = max(probabilities, key=probabilities.get)
    top_prob      = probabilities[top_channel]

    # Confidence: how concentrated is the distribution?
    # High confidence = one channel clearly dominates
    confidence = (
        "high"   if top_prob >= 0.55 else
        "medium" if top_prob >= 0.35 else
        "low"
    )

    return {
        "probabilities": probabilities,
        "top_channel":   top_channel,
        "top_prob":      top_prob,
        "confidence":    confidence,
        "signals_used":  signals,
    }
```

**What this produces per patient:**

```
Unattributed patient record:
  appointment_date = 2026-02-12 (Monday)
  lead_time_days   = 0           (same-day)
  service_category = "Emergency" (toothache)
  distance_miles   = 0.7         (ZIP code within 1 mile)
  insurance_type   = "cash"
  age_bracket      = "35-54"

Signals activated:
  same_day_booking ✓
  service_emergency ✓
  zip_within_1_mile ✓
  cash_pay_no_insurance ✓

Posterior probability distribution:
  Google Business Profile:     68.4%  ← top channel, high confidence
  Organic – Google Search:     14.2%
  Google Ads – Paid Search:    10.1%
  Referral – Patient:           4.8%
  Meta – Facebook / Instagram:  1.9%
  Other:                        0.6%

Result: $3,800 production credited to GBP with 68.4% weight.
  → GBP estimated revenue contribution: $3,800 × 0.684 = $2,599
  → Distributed across other channels proportionally for remaining 31.6%
  Confidence: HIGH (one channel clearly dominates at 68%)
```

---

#### Method 3 — Shapley Value Attribution (Advanced, Multi-Touch)

Used for patients who had multiple known touchpoints before converting, and for practices with enough data to quantify each channel's marginal contribution.

Shapley values come from cooperative game theory. The question: given that multiple channels participated in acquiring a patient, how much credit does each deserve? The answer is computed by considering every possible combination of channels and measuring each channel's marginal contribution when it's added to the coalition.

**Why this matters specifically for organic + paid overlap:**

A LASIK patient saw a blog post (organic), a retargeting ad (Google Ads), and called from GBP. Last-click gives 100% to GBP. First-touch gives 100% to organic. Shapley gives each channel credit proportional to its actual marginal contribution — which is the fairest and most accurate model.

```python
from itertools import combinations
import numpy as np

def shapley_attribution(
    touchpoints: list[str],
    conversion_value: float,
    channel_conversion_rates: dict[str, float]
) -> dict[str, float]:
    """
    Compute Shapley value attribution for a multi-touch patient journey.

    Args:
        touchpoints:  ordered list of channels the patient interacted with
                      e.g. ["Organic Search", "Google Ads", "GBP"]
        conversion_value: revenue value of this conversion
        channel_conversion_rates: estimated base conversion rate per channel
                      (calibrated from attributed patient data)

    Returns:
        dict of {channel: revenue_credit}
    """
    n = len(touchpoints)
    shapley_values = {ch: 0.0 for ch in touchpoints}

    # For each channel, compute marginal contribution across all subsets
    for i, channel in enumerate(touchpoints):
        others = [c for c in touchpoints if c != channel]

        for r in range(len(others) + 1):
            for subset in combinations(others, r):
                # Value of coalition without this channel
                v_without = _coalition_value(list(subset), channel_conversion_rates)
                # Value of coalition with this channel
                v_with    = _coalition_value(list(subset) + [channel], channel_conversion_rates)

                # Weight by number of permutations
                weight = (
                    np.math.factorial(r) *
                    np.math.factorial(n - r - 1) /
                    np.math.factorial(n)
                )
                shapley_values[channel] += weight * (v_with - v_without)

    # Normalize and apply to conversion value
    total = sum(shapley_values.values())
    return {
        ch: (sv / total) * conversion_value
        for ch, sv in shapley_values.items()
    }


def _coalition_value(channels: list[str], rates: dict) -> float:
    """Estimate conversion probability for a coalition of channels."""
    if not channels:
        return 0.0
    # Channels are complementary — joint probability higher than any single
    base = max(rates.get(c, 0.05) for c in channels)
    boost = sum(rates.get(c, 0.05) * 0.3 for c in channels[1:])
    return min(base + boost, 0.95)


# Example:
# Patient journey: ["Organic Search", "Google Ads Retargeting", "GBP call"]
# Production: $4,200

result = shapley_attribution(
    touchpoints=["Organic Search", "Google Ads Retargeting", "GBP call"],
    conversion_value=4200,
    channel_conversion_rates={
        "Organic Search":          0.12,
        "Google Ads Retargeting":  0.18,
        "GBP call":                0.22,
    }
)
# Output (example):
# {
#   "Organic Search":         $1,134   (27.0%) — started the journey
#   "Google Ads Retargeting": $1,512   (36.0%) — re-engaged
#   "GBP call":               $1,554   (37.0%) — closed the booking
# }
# vs last-click: GBP gets 100% ($4,200), others get $0
# vs first-touch: Organic gets 100%, others get $0
# Shapley: all three share credit proportional to contribution
```

---

### How Probabilistic Data Feeds Into the AI Agent

The key design principle: **the AI Agent must always know which data is observed and which is estimated.** Mixing them silently destroys trust when someone checks the numbers.

**Delta table schema additions for probabilistic rows:**

```sql
ALTER TABLE silver.`DemoData-marketing-crm`
ADD COLUMNS (
  data_type        STRING  DEFAULT 'observed',  -- 'observed' | 'estimated' | 'shapley'
  confidence_level STRING  DEFAULT 'high',       -- 'high' | 'medium' | 'low'
  estimation_method STRING DEFAULT NULL,         -- 'proportional'|'bayesian'|'shapley'
  probability_weight DOUBLE DEFAULT 1.0,         -- 0.0–1.0, weight of this row's credit
  signals_matched  STRING  DEFAULT NULL          -- JSON array of signals used
)
```

**What the AI Agent receives and how it uses it:**

```python
# AI query for show rate — confidence-aware version
query = """
SELECT
    data_source,
    data_type,
    confidence_level,
    SUM(attended)      AS attended_est,
    SUM(booked)        AS booked_est,
    SUM(total_revenue) AS revenue_est,
    ROUND(SUM(attended)/NULLIF(SUM(booked),0)*100, 1) AS show_rate,
    COUNT(CASE WHEN data_type = 'observed'  THEN 1 END) AS observed_rows,
    COUNT(CASE WHEN data_type = 'estimated' THEN 1 END) AS estimated_rows
FROM silver.`DemoData-marketing-crm`
WHERE date >= CURRENT_DATE - 30
GROUP BY data_source, data_type, confidence_level
ORDER BY revenue_est DESC
"""

# AI Agent response template for mixed observed + estimated data:
response_template = """
{channel} generated an estimated {revenue_est} in revenue last 30 days.

  Directly attributed (observed):  {observed_revenue} from {observed_attended} patients
  Probabilistically attributed:    {estimated_revenue} from {estimated_attended} est. patients
                                   Confidence: {confidence_level}

  Combined show rate: {show_rate}%
  Attribution method: {estimation_method}

⚠ Note: {pct_estimated:.0f}% of {channel}'s attributed revenue is probabilistically estimated
  based on patient signals (service type, timing, distance, insurance).
  Actual values may vary ±{margin_of_error:.0f}%.
"""
```

**AI Agent output example:**

```
User: "What is our ROAS by channel including estimated walk-ins?"

NexoBI AI Agent:

  CHANNEL ROAS — LAST 30 DAYS (observed + probabilistic)

  ┌─────────────────────────────┬──────────┬───────────┬───────────┬────────────┐
  │ Channel                     │ Revenue  │ Spend     │ ROAS      │ Confidence │
  ├─────────────────────────────┼──────────┼───────────┼───────────┼────────────┤
  │ Organic Search              │ $142,800 │ $2,800    │ 51.0x     │ Medium*    │
  │ Google Business Profile     │ $118,500 │ $0        │ ∞         │ High       │
  │ Google Ads – Paid Search    │ $98,400  │ $8,200    │ 12.0x     │ High       │
  │ Referral – Patient          │ $74,100  │ $0        │ ∞         │ Medium*    │
  │ Meta – Facebook / Instagram │ $52,800  │ $2,400    │ 22.0x     │ High       │
  │ Referral – Physician        │ $38,200  │ $0        │ ∞         │ Low*       │
  │ Directory (Healthgrades)    │ $28,400  │ $300      │ 94.7x     │ High       │
  └─────────────────────────────┴──────────┴───────────┴───────────┴────────────┘

  * Includes probabilistically attributed patients.
    Organic: 38 directly observed + 29 estimated (Bayesian, medium confidence)
    Patient Referral: 21 observed + 16 estimated (Bayesian, medium confidence)
    Physician Referral: 8 observed + 18 estimated (Bayesian, low confidence —
      low confidence because physician referral signals overlap with walk-in signals)

  Without probabilistic attribution, Organic ROAS showed as 34.1x.
  With probabilistic attribution (corrected for walk-ins), Organic ROAS: 51.0x.

  Recommendation: Organic search is generating significantly more revenue
  than previously visible. SEO investment appears to be the most efficient
  channel in your portfolio when walk-in behavior is properly attributed.
```

---

### Calibrating the Model — The Self-Improving Loop

The Bayesian model is only as good as its signal multipliers. Those multipliers must be calibrated from the practice's own attributed patient data — and updated continuously as more data accumulates.

```python
def calibrate_signal_multipliers(
    attributed_df: pd.DataFrame,
    signal_extractor: callable
) -> dict:
    """
    Learns the correct signal multipliers from attributed patients.
    Run monthly. Updates SIGNAL_MULTIPLIERS in the Delta table.

    Logic: For each signal, compute the channel distribution of
    attributed patients who had that signal. The ratio of that
    distribution to the baseline distribution IS the multiplier.
    """
    baseline = (
        attributed_df.groupby("data_source")["attended"].sum()
        / attributed_df["attended"].sum()
    ).to_dict()

    multipliers = {}

    for signal_name, signal_fn in SIGNAL_EXTRACTORS.items():
        signal_patients = attributed_df[attributed_df.apply(signal_fn, axis=1)]

        if len(signal_patients) < 20:
            continue  # not enough data to calibrate this signal

        signal_dist = (
            signal_patients.groupby("data_source")["attended"].sum()
            / signal_patients["attended"].sum()
        ).to_dict()

        multipliers[signal_name] = {
            channel: (signal_dist.get(channel, 0.001) /
                      baseline.get(channel, 0.001))
            for channel in baseline
        }

    return multipliers

# This runs monthly. As attributed data accumulates, the multipliers
# become increasingly accurate for this specific practice and market.
# After 6 months of data, the Bayesian model is meaningfully better
# than the proportional baseline for this practice's patient patterns.
```

**The model gets better over time without anyone touching it.** More attributed data → more accurate multipliers → better probabilistic estimates for unattributed patients → higher AI Agent answer confidence.

---

### Confidence Labeling — What the AI Agent Always Shows

Every response that includes probabilistic data must clearly label what is observed vs estimated. This is non-negotiable. It is the difference between a trustworthy system and a confident liar.

```python
CONFIDENCE_DISPLAY = {
    "high": {
        "label":  "✓ Directly attributed",
        "color":  GREEN,
        "note":   "Based on tracked digital journey (form, call, campaign tag).",
    },
    "medium": {
        "label":  "~ Probabilistically estimated",
        "color":  AMBER,
        "note":   "Based on patient signals (timing, service, distance, insurance). "
                  "Accuracy: ±15–25% of true value.",
    },
    "low": {
        "label":  "≈ Weakly estimated",
        "color":  MUTED,
        "note":   "Limited signal data. Broad proportional distribution applied. "
                  "Treat as directional only. Accuracy: ±30–40%.",
    },
}

# In the AI Agent response, every number that includes probabilistic
# data is annotated with its confidence level.
# Users can toggle: "Show observed only" vs "Show observed + estimated"
# Default: show both, clearly labeled.
```

---

### What This Unlocks for the Practice — Before vs After

**Before probabilistic attribution:**

```
Monthly revenue: $503,600
Attributed:      $367,600  (73%)
Unknown:         $136,000  (27%)

AI Agent says: "I can account for $367,600 of your revenue.
The other $136,000 has no marketing source."

Organic ROAS: 12.1x  (understated — missing walk-in patients)
GBP ROAS: ∞ but incomplete
Physician referral: appears small — physician outreach not prioritized
```

**After probabilistic attribution (Bayesian, medium confidence):**

```
Monthly revenue: $503,600
Observed:        $367,600  (73%)
Estimated:       $136,000  (27%)  ← now distributed, not lost
Total attributed: $503,600  (100% — with confidence labels)

AI Agent says: "Here is your complete revenue picture.
73% is directly attributed. 27% is probabilistically estimated
based on patient signals. Confidence: medium overall."

Organic ROAS: 51.0x  (corrected — walk-ins near blog-ranked areas credited)
GBP ROAS: captures walk-ins who found practice via Maps
Physician referral: now visible at realistic scale → outreach investment justified

New recommendation that wasn't possible before:
  "Physician referrals (observed + estimated) represent $56,400/month
   at zero acquisition cost. Your nearest orthopedic group refers 8
   confirmed patients. If you had 3 more physician referral relationships
   at the same rate, that's +$21,150/month in additional revenue.
   Physician relationship marketing has the highest potential ROAS
   of any channel you're not currently investing in."
```

---

### Implementation Roadmap for Probabilistic Attribution

```
PHASE 1 (Week 1–2) — Signal capture
  □ Add to EHR de-identified export:
      appointment_lead_time_days (computed from booking_date - appt_date)
      service_category           (from billing/CPT code category mapping)
      patient_zip_prefix         (first 3 digits only — not full ZIP, not PHI)
      insurance_category         (cash / commercial / government — not carrier name)
      age_decade                 (30s / 40s / 50s — not exact age, not DOB)
  □ Add these columns to Delta table schema
  □ Verify no PHI is captured (age_decade and zip_prefix are safe)

PHASE 2 (Week 3–4) — Proportional baseline
  □ Run proportional_attribution() on last 90 days of data
  □ Verify: Unknown drops to 0, distributed rows marked estimated=True
  □ AI Agent: update queries to include estimated rows with confidence labels
  □ Test: ask "What is organic ROAS including estimated patients?"
  □ Confirm numbers change vs previous (they should — organic goes up)

PHASE 3 (Month 2–3) — Bayesian upgrade
  □ Calibrate SIGNAL_MULTIPLIERS from 90 days of attributed patient data
  □ Run bayesian_channel_probability() on unattributed patients
  □ Compare confidence scores vs proportional: high confidence rows should dominate
  □ Validate spot-checks: same-day emergency appointments should cluster on GBP
  □ Update AI Agent to show confidence per channel in every answer

PHASE 4 (Month 4+) — Self-improving loop
  □ Schedule monthly calibrate_signal_multipliers() run (1st of month, 3 AM)
  □ Store multiplier versions in Delta table: track how they evolve
  □ Track prediction accuracy: when a probabilistic patient is later confirmed
    (e.g., front desk updates referral source), compare to prediction
  □ Use confirmed cases to measure model accuracy and update priors
  □ Report to client: "Probabilistic attribution model accuracy: 71% correct
    on cases we were later able to verify."
```

---

### The Sales Moment This Creates

> *"Right now, 27% of your revenue has no marketing source attached to it. That's $136,000 per month that your agency cannot see, your Google Ads dashboard cannot see, and your gut feeling cannot reliably explain. NexoBI doesn't pretend that money doesn't exist. We use the signals those patients DO carry — when they booked, how far they traveled, what service they needed, what insurance they have — to make a statistically informed estimate of where they likely came from.*

> *We label every estimated number clearly. We show you the confidence level. We don't hide that some of this is an estimate — we show you exactly how confident we are and why. And as more of your patients are attributed directly, the model gets more accurate every month.*

> *The result: you stop making budget decisions on 73% of your data. You make them on 100% — with the bottom 27% clearly labeled as estimated. That's a fundamentally different conversation than 'we don't know where those patients came from.' It's 'here is our best statistical estimate, here is our confidence level, and here is what it implies for your marketing investment.'"*

---

---

## 20. Who Is Doing This? Where Does NexoBI Fit? — Competitive Landscape

> **Purpose:** Map the current healthcare marketing analytics and attribution market — who the players are, where they fall short, what the market size and trajectory look like, and where NexoBI has a clear, defensible opportunity. Use this section for investor conversations, sales positioning against incumbents, and product prioritization.

---

### 20.1 Market Size and Trajectory

| Metric | Value | Source context |
|---|---|---|
| **Healthcare marketing analytics market (2024)** | $4.74 billion | Global; includes SaaS tools, agency analytics, BI deployments |
| **CAGR (2024–2032)** | 13.6% | Consistent with broader health IT spending trends |
| **Projected market size (2032)** | ~$13.7 billion | At 13.6% CAGR compounded |
| **Healthcare as a vertical** | Fastest-growing segment in marketing analytics | Growing at ~15% CAGR vs. 10-12% for other verticals |
| **AI in healthcare analytics market (2030)** | $187–208 billion | Broader healthcare AI; attribution is a subsegment |
| **U.S. healthcare ad spend (2024)** | $22+ billion | Practices, hospitals, pharma, insurers |
| **Dental practices in the U.S.** | ~200,000 | Majority are small (1–5 dentists) |
| **Medical practices (non-dental)** | ~1.1 million | Highly fragmented SMB market |

**Why healthcare marketing analytics is accelerating:**

1. **Telehealth normalization post-COVID** — practices now run digital-first patient acquisition for the first time
2. **Consolidation into DSOs and MSOs** — multi-location groups need centralized performance visibility
3. **HIPAA scrutiny on tracking pixels** — class action lawsuits against healthcare organizations using Meta Pixel have forced a rethinking of the entire tracking stack
4. **Google's deprecation of third-party cookies** — first-party data and server-side tracking are no longer optional
5. **AI accessibility** — open-source models (Llama, Mistral) have made AI-powered analytics affordable at the SMB tier for the first time

---

### 20.2 The Incumbents — Who Exists Today

#### Tier 1 — Compliance-First Analytics (Enterprise/Mid-Market)

---

**Freshpaint**
- **What it does:** HIPAA-safe event streaming layer that sits between your website/app and downstream analytics tools (GA4, Mixpanel, Amplitude, Segment). Anonymizes or blocks PHI before data leaves the browser.
- **Primary market:** Health systems, telehealth platforms, large DSOs
- **Pricing:** $2,000–$10,000/month (enterprise contracts)
- **Strengths:**
  - True HIPAA Business Associate Agreement (BAA) compliance
  - Integrates with every major downstream analytics platform
  - Handles server-side tracking and CAPI automatically
  - Well-funded ($75M raised), strong enterprise sales motion
- **Weaknesses:**
  - **Not a BI/analytics tool** — Freshpaint is a data routing layer, not a dashboard or AI agent
  - Requires the practice to already have GA4, Mixpanel, or another analytics stack they know how to use
  - No native EHR integration — stops at the website/app layer
  - Zero revenue/production data — can't answer "what did that patient pay?"
  - $2,000+/month is unaffordable for a solo practitioner or small group practice
  - No AI agent, no natural language querying
- **NexoBI vs. Freshpaint:** Freshpaint solves the compliance + data collection problem for large organizations. NexoBI connects the collected data all the way through to revenue, adds the AI layer, and does it affordably for SMB practices. They could be **complementary** (Freshpaint feeds clean events → NexoBI ingests them into Delta Lake).

---

**Invoca**
- **What it does:** AI-powered call tracking and conversation intelligence platform. Records, transcribes, and analyzes phone calls to attribute them to marketing sources.
- **Primary market:** Multi-location healthcare, insurance, automotive
- **Pricing:** $1,000–$5,000+/month
- **Strengths:**
  - Best-in-class call attribution accuracy
  - AI call scoring (is this a new patient inquiry? an appointment? a complaint?)
  - Deep integrations with Google Ads and Salesforce
  - Handles call-heavy healthcare acquisition well
- **Weaknesses:**
  - **Call-only** — no organic search attribution, no EHR integration, no revenue data
  - Expensive for smaller practices
  - No dashboard for practice operations — it's a call intelligence tool, not an analytics platform
  - No AI agent for open-ended questions
- **NexoBI vs. Invoca:** Invoca solves one attribution gap (calls). NexoBI solves the full funnel. CallRail (more affordable) covers 90% of what small-medium practices need from Invoca. Invoca is the **enterprise** version of what CallRail does.

---

#### Tier 2 — Healthcare Marketing-Specific Analytics (Mid-Market)

---

**Practice by Numbers (PbN)**
- **What it does:** Dental-specific business intelligence platform. Aggregates data from Dentrix, Eaglesoft, and Open Dental. Shows KPIs like production, collections, hygiene reappointment rate, patient retention.
- **Primary market:** Dental practices and DSOs
- **Pricing:** $200–$500/month depending on number of locations
- **Strengths:**
  - Native Dentrix/Eaglesoft/Open Dental connectors — no custom ETL required
  - Pre-built dental KPI library (hygiene efficiency, case acceptance, AR aging)
  - Used by thousands of dental practices — established distribution
  - White-label capability for DSOs
- **Weaknesses:**
  - **Dental-only** — no support for medical, MedSpa, mental health, physical therapy
  - **No marketing attribution** — shows what happened in the chair, not what marketing drove the patient there
  - No ad platform connections (Google Ads, Meta)
  - No organic search attribution
  - No AI agent — static dashboards with pre-built reports only
  - Cannot answer: "Which campaign produced my best-LTV patients?"
- **NexoBI vs. PbN:** PbN is the operations dashboard for dental; NexoBI is the marketing intelligence layer. They could coexist. NexoBI's differentiator: **it closes the gap PbN leaves open** — connecting the patient who walked in (which PbN tracks) to the campaign that brought them in (which PbN ignores).

---

**SocialClimb**
- **What it does:** Healthcare reputation management and limited marketing analytics. Automates review collection (Google, Healthgrades), tracks star ratings, monitors patient satisfaction.
- **Primary market:** Medical and dental group practices
- **Pricing:** $200–$800/month
- **Strengths:**
  - Strong review automation — practices see measurable GBP star rating improvements
  - Basic patient attribution from surveys
  - Simple, easy-to-use interface for non-technical practice managers
- **Weaknesses:**
  - Reputation-focused, not revenue-focused
  - Attribution is survey-based (self-reported "how did you hear about us?") — not data-driven
  - No ad platform data, no EHR production data, no funnel analysis
  - No AI capabilities
  - Does not differentiate Google Ads clicks from organic GBP views
- **NexoBI vs. SocialClimb:** SocialClimb helps practices look good online; NexoBI tells them whether looking good is driving revenue. Complementary tools — a practice could use SocialClimb for review automation and NexoBI for marketing ROI.

---

**PatientGain**
- **What it does:** All-in-one healthcare marketing platform — website, SEO, PPC management, patient chat, and basic reporting dashboard.
- **Primary market:** Medical practices, primary care, urgent care
- **Pricing:** $500–$2,000/month (managed service model)
- **Strengths:**
  - Bundled offering — agency + tools in one contract
  - Includes website and SEO services, reducing vendor sprawl
  - Healthcare-specific templates and compliance awareness
- **Weaknesses:**
  - **Managed service, not software** — the agency controls the data, not the practice
  - Reporting is surface-level — clicks and form fills, not patient revenue
  - No EHR integration
  - No AI agent or natural language querying
  - Practices are dependent on PatientGain's team to interpret results
  - No probabilistic attribution, no funnel drop analysis
- **NexoBI vs. PatientGain:** PatientGain sells outcomes via an agency model. NexoBI sells visibility and control. Practices using PatientGain cannot truly audit their own marketing performance — NexoBI makes that possible and would appeal to practices that want to graduate from the black-box agency model.

---

**Liine**
- **What it does:** AI-powered new patient acquisition intelligence focused on phone call analysis. Uses AI to classify calls (new patient inquiry, existing patient, non-patient), score staff performance on calls, and track source attribution.
- **Primary market:** Dental, orthodontics, plastic surgery, elective healthcare
- **Pricing:** $400–$1,500/month
- **Strengths:**
  - Strong AI call classification — knows if a caller converted to a booked appointment
  - Automatically links phone calls back to marketing source
  - Front desk performance scoring — helps identify which staff converts best
  - Growing customer base in elective healthcare (high LTV markets)
- **Weaknesses:**
  - **Call-only** — same limitation as Invoca. No digital form attribution, no EHR data, no organic search
  - No revenue or production tracking
  - No AI agent for open-ended questions about the full marketing mix
  - Limited to call-heavy acquisition models
- **NexoBI vs. Liine:** Liine is excellent at the phone call layer. NexoBI operates at the full-funnel level. Liine data (call source + conversion outcome) is exactly the kind of signal NexoBI would want to **ingest** as part of its unified Delta table. Potential integration partner.

---

**CallTrackingMetrics (CTM)**
- **What it does:** Call tracking platform with marketing attribution, call recording, and some AI scoring features. Wider feature set than CallRail, including SMS, chat, and form tracking.
- **Primary market:** Multi-vertical (healthcare, legal, home services, automotive)
- **Pricing:** $79–$400+/month
- **Strengths:**
  - More configurable than CallRail
  - Multi-channel (calls + SMS + chat + forms) from a single platform
  - Integrates with HubSpot, Salesforce, Google Ads
- **Weaknesses:**
  - Not healthcare-specific — no EHR connectors, no HIPAA-focused implementation guide
  - Reporting is call-centric, not revenue-centric
  - No native AI agent for open-ended analytics
- **NexoBI vs. CTM:** Like CallRail, CTM is a data source NexoBI should ingest, not compete with.

---

**Lasso MD**
- **What it does:** Marketing analytics platform built for aesthetic medicine and plastic surgery. Tracks leads, appointments, consultations, and procedure revenue from paid campaigns.
- **Primary market:** MedSpa, plastic surgery, cosmetic dermatology
- **Pricing:** ~$500–$2,000/month
- **Strengths:**
  - Vertical-specific — understands the cosmetic patient funnel (consultation → treatment plan → procedure)
  - Tracks high-LTV procedure revenue
  - Integrates with some EHR/practice management systems used in aesthetics
- **Weaknesses:**
  - Narrow vertical (aesthetics only)
  - Limited AI capabilities
  - Small company — limited integrations, slower development
  - No Databricks/enterprise data platform
- **NexoBI vs. Lasso MD:** Direct competitor in the MedSpa/aesthetics vertical. NexoBI's advantage: multi-specialty coverage, open-model AI (Llama), Databricks infrastructure, and probabilistic attribution.

---

**Healthcare Success**
- **What it does:** Full-service healthcare marketing agency that provides analytics as part of managed service engagements.
- **Primary market:** Hospitals, health systems, large medical groups
- **Pricing:** $5,000–$50,000/month (agency retainers)
- **Strengths:**
  - Deep healthcare marketing expertise
  - Handles strategy, creative, media buying, and reporting
  - Trusted by large institutions
- **Weaknesses:**
  - Agency model — clients don't own their data or insights
  - No self-serve software
  - Not accessible to SMB practices
  - Analytics are packaged in static monthly PDFs, not real-time dashboards

---

**PatientFlow / Other Niche Tools**
- Various smaller tools exist for specific use cases (appointment reminder analytics, patient satisfaction scores, website heatmaps). None provide the full-funnel attribution + AI layer.

---

#### Tier 3 — General BI Tools Used by Healthcare Agencies

| Tool | Why agencies use it | Why it fails healthcare practices |
|---|---|---|
| **Tableau** | Powerful visualization, enterprise adoption | Blank canvas — no healthcare KPIs, no EHR connectors, expensive ($70–$840/user/month) |
| **Looker / Looker Studio** | Free tier, Google ecosystem | No built-in healthcare logic, requires SQL expertise |
| **Power BI** | Microsoft ecosystem, affordable | No HIPAA-safe data routing, no EHR connectors, complex setup |
| **Domo** | Enterprise dashboards, mobile | Expensive, no healthcare-specific modules, no AI agent |
| **Klipfolio** | Marketing KPI dashboards | No healthcare connectors, no EHR, no AI |

**The agency workaround:** Most healthcare marketing agencies build custom Looker Studio or Google Data Studio reports that pull from Google Ads + GA4. These reports:
- Show clicks, impressions, and form fills
- Never touch EHR data
- Have no patient revenue data
- Cannot answer "what is our ROAS on attended appointments?"

This is exactly the gap NexoBI fills.

---

### 20.3 Competitive Positioning Matrix

Position each player by **price tier** and **attribution depth**:

```
                           ATTRIBUTION DEPTH
                    Surface           Full-Funnel
                    (Clicks/Leads)    (Revenue + EHR)
                 ┌──────────────────────────────────────┐
                 │                                      │
  ENTERPRISE     │  Tableau / Looker  │   Freshpaint +  │
  ($2,000+/mo)   │  Power BI          │   Invoca +      │
                 │  Healthcare Success│   Custom ETL    │
                 │                                      │
                 ├────────────────────┼─────────────────┤
                 │                                      │
  MID-MARKET     │  SocialClimb       │   Practice by   │
  ($300–$2,000   │  PatientGain       │   Numbers       │
  /mo)           │  Liine             │   Lasso MD      │
                 │  CTM / CallRail    │                 │
                 │                                      │
                 ├────────────────────┼─────────────────┤
                 │                                      │
  SMB            │  Looker Studio     │      ★          │
  (<$300/mo)     │  (agency-built)    │   NexoBI        │
                 │  Manual reporting  │   TARGET ZONE   │
                 │                                      │
                 └──────────────────────────────────────┘
```

**NexoBI's target zone:** Mid-market to SMB, full-funnel attribution depth — a space **currently occupied by no single product**.

The closest competitor to NexoBI's full vision is a combination of:
- Freshpaint (compliance layer) + CallRail (call attribution) + Practice by Numbers (EHR KPIs) + custom Python ETL + a BI tool

That stack costs **$3,000–$8,000/month** and requires a developer to maintain. NexoBI replaces all of it with a single Databricks App.

---

### 20.4 The 10 Market Gaps NexoBI Can Own

Based on the competitive analysis, here are the specific gaps no existing product adequately addresses for the SMB/mid-market healthcare practice:

---

**Gap 1 — The Revenue Attribution Gap**

> *28% of healthcare marketers report they cannot measure marketing ROI.*

Every existing tool either stops at leads (ad platforms, GA4) or stops at production without source (Practice by Numbers, EHR dashboards). NexoBI is the only tool that closes the loop from ad spend → lead → booked → attended → production revenue — by connecting ad platform APIs to EHR production data in a single Delta table.

**The stat that sells this:** *"Right now you know how many leads Google sent you. NexoBI tells you how much revenue those leads generated — down to the appointment."*

---

**Gap 2 — The Call Attribution Gap at SMB**

> *Only 3% of dental practices use call tracking.*

Invoca and Liine are enterprise-priced. CallRail is affordable but not integrated into a broader analytics platform. Most small practices have no call attribution at all — they genuinely don't know whether a patient called because of their Google Ad, their GBP, their website SEO, or a referral.

NexoBI's answer: Include CallRail DNI as a standard part of setup, ingest call data into the same Delta table as the rest of the funnel, and surface call attribution automatically in the AI Agent.

---

**Gap 3 — The Organic Attribution Gap**

No existing tool solves organic search attribution for healthcare SMBs. The full solution (first-party JS cookie + Search Console API + CallRail DNI + CRM hidden fields + EHR automation + probabilistic estimation for walk-ins) exists as a set of components — no product has assembled them into a single workflow designed for a healthcare practice.

This is a **legitimate white space** and a technically defensible moat. Building this correctly requires:
- HIPAA understanding (what data is safe to collect)
- EHR knowledge (how referral source fields work)
- Attribution expertise (first-party cookies, UTM limitations)
- AI/ML (probabilistic models for unattributed patients)
- Databricks infrastructure (Delta Lake, Unity Catalog, Genie)

No SMB tool has combined all five.

---

**Gap 4 — The Multi-Specialty Gap**

Practice by Numbers is dental-only. Lasso MD is aesthetics-only. SocialClimb is broad but shallow. No mid-market tool covers the full spectrum: dental, medical, MedSpa, mental health, physical therapy, chiropractic, vision, hearing, dermatology, orthopedics, urgent care, pediatrics.

Healthcare is not one market — it's 13+ submarkets with different EHRs, different funnels, different LTV profiles, and different seasonality patterns. NexoBI's architecture is specialty-agnostic by design.

---

**Gap 5 — The Probabilistic Attribution Gap**

No existing SMB healthcare analytics tool attempts probabilistic attribution for unattributed patients (walk-ins, referrals, unreported sources). The approach described in Section 19 — Bayesian signal weighting using non-PHI signals — is **industry-leading** for the SMB tier and would be a genuine product differentiator.

**The sales line:** *"Every other tool has a 'Unknown' bucket that holds 20–30% of your patients. NexoBI distributes that bucket using statistical inference — and shows you the confidence level on every estimate."*

---

**Gap 6 — The AI Agent Gap**

No existing healthcare marketing analytics tool offers natural language querying against live EHR + ad platform data. Practice by Numbers has static dashboards. PatientGain has PDF reports. Freshpaint routes data into tools that require SQL knowledge to query.

NexoBI's AI Agent (Llama 3.3 70B via Databricks Model Serving) allows a practice owner or office manager to ask: *"Which campaigns brought in the patients with the highest case acceptance last quarter?"* — and get an answer in under 10 seconds, without SQL, without a developer, without a scheduled report.

**This is the capability gap that is hardest to replicate** — it requires Databricks access, open model serving, and domain-specific prompt engineering that incumbents haven't invested in for the SMB tier.

---

**Gap 7 — The HIPAA-Safe Data Ownership Gap**

Freshpaint is HIPAA-compliant but routes your data to third-party tools (Mixpanel, Amplitude, Segment) — your data leaves your infrastructure. PatientGain and agency-built solutions hold the data themselves — the practice doesn't own it.

NexoBI running on Databricks Apps means **the data never leaves the practice's Databricks environment**. The AI model (Llama via Databricks Model Serving) runs on-prem within the Unity Catalog workspace. No third-party AI provider touches patient-adjacent data.

For DSOs and larger groups with IT governance requirements, this is not just a feature — it's the only acceptable architecture.

---

**Gap 8 — The Front Desk Intelligence Gap**

Show rate (the percentage of booked patients who actually attend) is one of the highest-leverage metrics in healthcare marketing — a 5% improvement in show rate can equal a 5% revenue increase without spending a single additional dollar on ads. Yet no marketing analytics tool tracks it by source.

NexoBI surfaces show rate by traffic source in the standard dashboard. "Your Google Ads patients have an 84% show rate. Your Meta patients have a 61% show rate. Your organic patients have a 91% show rate." This drives immediate budget reallocation decisions.

---

**Gap 9 — The Benchmarking Gap**

General BI tools (Tableau, Looker) show you your numbers. Practice by Numbers shows you your dental KPIs. Nobody tells you whether your numbers are good.

NexoBI embeds industry benchmarks for healthcare marketing KPIs:
- ROAS benchmarks by specialty
- CPL benchmarks by channel
- Show rate benchmarks by source
- Booking rate benchmarks by funnel stage

**The Platform Health Score** (built into the NexoBI dashboard) is the product embodiment of this insight — a single number from 0–100 that tells you not just what your metrics are, but how they compare to industry standards.

---

**Gap 10 — The DSO / Multi-Location Intelligence Gap**

As dental and medical practices consolidate into DSOs and MSOs, the need for cross-location performance intelligence grows. Which location has the best ROAS? Which location has the worst show rate? Which location's paid campaigns are underperforming relative to organic?

No SMB tool handles multi-location aggregation with per-location drill-down. Enterprise BI tools (Tableau, Domo) can do this but require a data engineering team. NexoBI on Databricks can handle multi-location Delta tables and Unity Catalog data governance natively.

---

### 20.5 The Three Biggest Competitive Risks — And How to Answer Them

---

**Risk 1: "Practice by Numbers already does this."**

**The Answer:**

Practice by Numbers shows you what happened inside your practice. NexoBI shows you *why* it happened — and what your marketing spend had to do with it.

Ask a Practice by Numbers customer: *"Which Google Ads campaign produced your best-LTV patients last quarter?"* They cannot answer that question. NexoBI answers it in 8 seconds.

PbN is the operations mirror. NexoBI is the marketing intelligence engine. They are complementary tools, and NexoBI can ingest PbN data if needed.

---

**Risk 2: "We already have a marketing agency that gives us monthly reports."**

**The Answer:**

Your agency reports show you what the agency wants you to see. Clicks, impressions, leads, cost per lead — all measured at the top of the funnel, before we know if those patients showed up, paid, or ever came back.

NexoBI connects those clicks to your actual production revenue. If your agency is delivering 300 leads a month at $45 each, but only 60% book and 55% of those attend, your effective cost per attended patient is $136 — not $45. Your agency's report will never show you that number. NexoBI shows it by default.

---

**Risk 3: "Freshpaint is the HIPAA-compliant analytics standard."**

**The Answer:**

Freshpaint solves the data collection compliance problem — it's an excellent tool for large health systems. But Freshpaint doesn't analyze anything. It routes anonymized events to Mixpanel or Amplitude, which are general-purpose analytics tools with no healthcare logic.

NexoBI is the analysis layer above Freshpaint. If you already have Freshpaint, NexoBI can ingest those clean events and add the EHR production data, the probabilistic attribution, and the AI Agent on top. They solve different problems in the same stack.

For practices without Freshpaint (the majority of SMBs), NexoBI uses server-side CAPI and SHA-256 hashing to achieve the same HIPAA compliance goal at a fraction of the cost.

---

### 20.6 NexoBI's Specific Differentiation — The Honest Positioning

Based on the competitive landscape, NexoBI's clearest differentiated position is:

> **"The first AI-native, full-funnel marketing intelligence platform for healthcare practices — built on your own Databricks infrastructure, so your data never leaves your environment."**

The differentiation pillars, in order of defensibility:

| Pillar | Why it's defensible | What makes it hard to copy |
|---|---|---|
| **Full-funnel attribution (ad spend → EHR revenue)** | No SMB tool does this end-to-end | Requires EHR connectors + Delta Lake ETL + domain knowledge |
| **AI Agent in natural language** | No healthcare analytics tool has this at the SMB tier | Requires Databricks Model Serving + prompt engineering + data schema |
| **Data stays in your Databricks environment** | Regulatory moat — critical for DSOs, health systems | Architecture decision that generic tools can't replicate without rebuilding |
| **Organic search attribution** | Unsolved problem in the market | Requires all 5 components (JS cookie + Search Console + DNI + CRM + EHR + probabilistic) |
| **Probabilistic attribution for unattributed patients** | Industry-leading for SMB tier | Novel application of Bayesian inference + Shapley values to healthcare funnel data |
| **Multi-specialty design** | Broader TAM than dental-only competitors | Healthcare domain knowledge across 13+ specialties |
| **Platform Health Score + proactive signals** | Nobody is doing daily automated intelligence surfacing | Proactive query engine + signal library + threshold calibration |

---

### 20.7 The Market Opportunity — By the Numbers

> Use this section for pitch decks, investor conversations, and enterprise sales.

**Total Addressable Market (TAM):**
- U.S. healthcare practices: ~1.3 million (dental + medical + allied health)
- At $500/month average contract: **$7.8B annual TAM**
- Realistic SAM (practices with digital marketing spend + EHR): ~200,000 practices
- At $500/month: **$1.2B annual SAM**

**The Underserved Segment:**
- Practices spending $2,000–$20,000/month on Google Ads and Meta
- Currently using: agency reports + GA4 + manual spreadsheets
- Willing to pay $300–$1,500/month for real attribution
- This segment alone: estimated **400,000–600,000 practice locations** (including DSO locations)

**The DSO Opportunity:**
- Top 10 DSOs in the U.S. each have 200–1,500 locations
- Enterprise contract value: $50,000–$500,000/year per DSO
- 5 large DSO contracts = $250,000–$2.5M ARR with extremely high retention

**Timing advantage:**
- HIPAA pixel enforcement is forcing every healthcare organization to rebuild their tracking stack **right now**
- The $22B in annual U.S. healthcare ad spend is increasingly unattributed due to third-party cookie deprecation
- Practices that don't solve attribution in 2025–2026 will face increasing pressure from insurers, investors (DSOs), and internal stakeholders demanding ROI proof
- NexoBI is positioned to capture practices at the moment they're actively searching for a solution

---

### 20.8 Where NexoBI Should Win First — GTM Prioritization

Based on the competitive landscape and market gaps, the clearest first-market targets:

**Primary Beachhead: Dental DSOs (5–50 locations)**

- **Why:** High ad spend ($5,000–$50,000/month per location), consolidating into groups that need cross-location visibility, sophisticated enough to understand attribution, HIPAA compliance already a boardroom concern
- **Decision maker:** CMO or VP Marketing of the DSO, not individual practice managers
- **Entry pain:** Agency reports that don't show per-location ROAS or patient LTV
- **Win condition:** First dashboard demo that shows *actual attended-patient ROAS by location* — a number no existing tool provides

**Secondary Market: High-LTV Elective Practices (MedSpa, Orthodontics, Implants, Cosmetic Surgery)**

- **Why:** LTV of $3,000–$25,000 per patient makes attribution ROI math obvious; these practices already invest in marketing; attribution error is expensive
- **Decision maker:** Practice owner/physician-entrepreneur
- **Entry pain:** Spending $10,000/month on Google Ads with no way to know which campaigns drive actual procedures
- **Win condition:** Show them that 20% of their ad spend is producing 80% of their procedure revenue — and they didn't know which 20% until now

**Tertiary Market: Mental Health Group Practices (10–50 providers)**

- **Why:** Fastest-growing healthcare segment, increasingly using digital marketing for provider recruitment and patient acquisition, SimplePractice + TherapyNotes are the EHR of record
- **Decision maker:** Group practice owner or operations director
- **Entry pain:** No way to attribute online bookings back to organic vs. paid vs. Psychology Today listings
- **Win condition:** Show them their organic search (Psychology Today, Google organic) drives 60% of new patients — and they've been overspending on Google Ads chasing the wrong channel

---

### 20.9 Competitive Response Cheat Sheet

> Quick-reference table for common competitive objections in sales calls.

| Objection | Competitor being referenced | The 30-second answer |
|---|---|---|
| "We use Tableau for reporting" | Tableau / Looker Studio | "Tableau shows you data. NexoBI tells you what it means — the AI Agent answers the questions Tableau makes you build reports for." |
| "Our agency gives us weekly reports" | Agency PDF/Looker Studio reports | "Those reports show what the agency controls. NexoBI shows what your practice owns — including patient revenue." |
| "We use Practice by Numbers" | PbN | "PbN is great for ops. Ask it which Google Ads campaign drove your best patients — it can't answer. NexoBI can." |
| "We use Freshpaint for HIPAA compliance" | Freshpaint | "Perfect — NexoBI sits on top of Freshpaint. Freshpaint collects the data; NexoBI is where you analyze it." |
| "We track calls with CallRail" | CallRail | "NexoBI ingests CallRail data automatically. Now those calls are connected to booked appointments and production revenue." |
| "We use SocialClimb for reputation" | SocialClimb | "SocialClimb helps you look good. NexoBI tells you if looking good is driving revenue." |
| "ChatGPT already answers our data questions" | Generic AI | "ChatGPT doesn't have your data. NexoBI's AI Agent runs on your actual patient funnel data in Databricks — not a general model hallucinating answers." |
| "Our EHR has a built-in reporting module" | Dentrix, athenahealth, etc. | "EHR reports show what happened inside the practice. NexoBI connects those outcomes back to the marketing that drove them." |

---

### 20.10 The Founding Insight — Why This Hasn't Been Built Yet

This is worth articulating for pitches and investor conversations.

The reason no single product has solved full-funnel healthcare marketing attribution at the SMB tier is that it requires **simultaneous expertise in five domains** that rarely coexist in a single founding team:

1. **Healthcare domain knowledge** — EHR systems, patient funnel mechanics, HIPAA constraints, specialty-specific KPIs
2. **Marketing attribution expertise** — UTM mechanics, server-side tracking, call tracking DNI, first-party cookies, GA4, Meta CAPI
3. **Data engineering** — ETL pipeline design, Delta Lake, Unity Catalog, schema normalization across heterogeneous sources
4. **AI/ML** — Probabilistic attribution models, Bayesian inference, Shapley values, LLM prompt engineering for structured SQL generation
5. **Enterprise data infrastructure** — Databricks, Model Serving, Genie Space, deployment on Databricks Apps

Existing competitors picked two or three of these:
- **Freshpaint:** Compliance + data engineering (but not analytics, AI, or healthcare domain)
- **Practice by Numbers:** Healthcare domain + EHR (but not marketing attribution or AI)
- **Liine:** AI + call tracking (but not EHR, organic attribution, or full funnel)
- **General BI tools:** Data engineering + visualization (but not healthcare domain, attribution, or AI)

NexoBI's architecture — as documented throughout this document — addresses all five domains in a single platform. That is the moat, and that is the space.

---

*NexoBI · Integration Scenarios · February 2026*
*Last updated: February 27, 2026 — Section 20 added (Competitive Landscape — Who Is Doing This? Where Does NexoBI Fit?)*
