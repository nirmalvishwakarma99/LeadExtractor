# Google Maps Intelligent Master Scraper

**Variant A — Non-Image Data Extraction Pipeline**

An enterprise-oriented, fault-tolerant Google Maps scraping system built with **Python, Playwright, Pandas, and OpenPyXL**. The application is designed to discover businesses across geographic areas, extract structured Google Maps profile data, crawl linked business websites for additional contact information, normalize multilingual data, validate records, remove duplicates, and produce schema-compliant CSV and Excel datasets.

> **Current implementation:** Variant A (Non-Image Scraper)  
> **Future implementation:** Variant B (AI Image / Signboard / OCR Intelligence)

---

## 1. Key Capabilities

### Google Maps Discovery
- Searches businesses using configurable keywords.
- Generates search queries from geographic data such as pincode, district, state, and area.
- Uses asynchronous Playwright workers for concurrent processing.
- Supports configurable headless/visible browser execution.

### Business Profile Extraction
Extracts available information from Google Maps business profiles, including:
- Business/company name
- Address
- Category
- Rating
- Review count
- Phone numbers
- Website
- Google Maps profile URL
- Business/operational status

### Deep Website Contact Crawling
When a business website is available, the crawler can inspect:
- Homepage and contact pages
- Contact information embedded in HTML
- Email addresses
- Additional phone numbers
- RERA numbers
- Owner/contact names
- "View Number" / "Show Mobile" style reveal controls
- Popups and common website overlays

### Multilingual Normalization
The processing layer supports multilingual Indian business data and can translate relevant text into English while retaining important raw identifiers such as:
- Brand/business names
- Phone numbers
- Domains
- Other identifiers required by the output schema

### Phone Number Processing
The normalization layer classifies and standardizes:
- Mobile numbers
- Secondary mobile numbers
- Landline numbers
- STD codes
- Toll-free numbers

### Validation & Deduplication
The pipeline validates records and uses multiple identity signals, including:
- Google Maps CID
- Google Maps/profile URL
- Normalized business name
- Business name + phone combination
- Address-derived identity signals

### Fault-Tolerant Storage
The storage architecture is designed around incremental persistence:
- Batch checkpoints
- Atomic file replacement
- Persistent progress tracking
- Rolling backups
- Final CSV consolidation
- Excel compilation using OpenPyXL

This minimizes the risk of losing collected data during interruptions or unexpected shutdowns.

---

## 2. System Architecture

```text
User CLI
   │
   ├── Keyword
   ├── Worker Count
   ├── Headless Mode
   ├── Checkpoint Size
   └── Rest/Cooldown
   │
   ▼
Geographic Input
input/pincode_areas_output.csv
   │
   ▼
Search Query Generator
   │
   ▼
Central Async Orchestrator
   │
   ├─────────────────────────────────────────┐
   ▼                                         ▼
Variant A — Active                       Variant B — Roadmap
Non-Image Scraper                        AI Image Intelligence
   │
   ├── Google Maps profile extraction
   ├── Address/status extraction
   ├── Website crawling
   ├── Translation & normalization
   ├── Phone classification
   ├── Validation
   └── Deduplication
   │
   ▼
Fault-Tolerant Storage
   │
   ├── Checkpoint CSV files
   ├── progress.json
   ├── Rolling backups
   └── Final CSV + Excel
```

---

## 3. Project Structure

```text
google_maps_scraper/
│
├── main.py
├── config.py
├── models.py
├── requirements.txt
├── .gitignore
├── LICENSE
│
├── input/
│   └── pincode_areas_output.csv
│
├── template/
│   └── Formate_for_genral.xlsx
│
├── variants/
│   ├── base.py
│   ├── non_image/
│   │   └── scraper.py
│   └── image/
│       └── scraper.py
│
├── google_maps/
│   ├── browser.py
│   ├── search.py
│   ├── extractor.py
│   └── address_extractor.py
│
├── website/
│   └── scraper.py
│
├── processing/
│   ├── translator.py
│   ├── normalizer.py
│   ├── validator.py
│   └── deduplicator.py
│
├── storage/
│   ├── formatter.py
│   ├── csv_writer.py
│   ├── progress.py
│   └── backup.py
│
├── monitoring/
│   ├── alerts.py
│   └── logger.py
│
├── output/
│   ├── final/
│   ├── checkpoints/
│   ├── backup/
│   └── progress.json
│
└── logs/
    └── scraper_YYYY-MM-DD.log
```

---

## 4. Requirements

### Prerequisites

- Python **3.10 or newer**
- Google Chrome or Chromium-compatible environment
- Internet connection
- Sufficient disk space for checkpoints, logs, and final datasets

### Python Dependencies

The active dependency set is intentionally limited to the requirements needed by **Variant A**.

See:

```text
requirements.txt
```

Variant B dependencies remain commented out until the computer-vision pipeline is implemented.

---

## 5. Installation

### Step 1 — Clone the Project

```bash
git clone https://github.com/nirmalvishwakarma99/LeadExtractor.git
cd google-maps-intelligent-scraper
```


### Step 2 — Create a Virtual Environment

#### Windows PowerShell

```powershell
python -m venv venv
.env\Scriptsctivate
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Install Playwright Chromium

```bash
playwright install chromium
```

---

## 6. Input Files

Before starting the scraper, verify that the following files exist.

### `input/pincode_areas_output.csv`

This file provides the geographic lookup information used to generate searches.

Typical geographic fields include:

```text
pincode
district
state
area
```

The exact columns should match the implementation used by the query generator.

### `template/Formate_for_genral.xlsx`

This workbook acts as the master export template. It defines the expected output column names and column ordering.

---

## 7. Running the Scraper

Start the application with:

```bash
python main.py
```

The application uses an interactive CLI to configure the scraping session.

Example:

```text
=================================================================
  GOOGLE MAPS INTELLIGENT SCRAPER — NON-IMAGE VARIANT A
=================================================================

Enter search keyword (e.g. Used Bike Dealers): Used Bike Dealers

Run browser in headless mode?
1. Yes (Invisible / Faster)
2. No  (Visible / Recommended for CAPTCHA monitoring)
Select [1 or 2] (Default: 2): 2

Enter number of concurrent workers [1-6] (Default: 2): 3

Enter checkpoint size in records (Default: 50): 50

Enter rest cooldown after checkpoint in seconds (Default: 30): 30
```

---

## 8. Configuration Parameters

| Parameter | Description | Recommended |
|---|---|---|
| Keyword | Business/category search term | Depends on project |
| Headless Mode | Runs browser invisibly or visibly | Visible for monitoring |
| Workers | Number of concurrent Playwright workers | 2–4 |
| Checkpoint Size | Records processed before checkpoint | 50 |
| Rest Cooldown | Pause after checkpoint | 30 seconds |

Higher concurrency may improve throughput but can also increase resource consumption and the likelihood of anti-bot challenges.

---

## 9. CAPTCHA & Blocking Handling

The application includes a blocking circuit breaker for Google Maps anti-bot/interstitial conditions.

When a blocking condition is detected, worker activity is paused and the operator is prompted to resolve the challenge manually.

Example terminal message:

```text
======================================================================
⚠️ ACTION REQUIRED: Google Maps displayed a CAPTCHA or blocking screen.

Switch to the open browser window and complete the challenge manually.

Press [ENTER] in this console after you have resolved the verification...
======================================================================
```

After the challenge is resolved, the session can continue using the existing progress state.

> **Operational note:** Anti-bot behavior can change over time. The scraper should be used responsibly and in accordance with applicable laws, website terms, and Google policies.

---

## 10. Resume & Crash Recovery

The scraper maintains persistent progress information in:

```text
output/progress.json
```

If execution is interrupted by:
- `Ctrl + C`
- Network failure
- Application crash
- System restart

the application can restore the previous session.

Example:

```text
[RESUME DETECTED] Found 142 previously scraped records.

1. Resume previous session
2. Overwrite and start new session

Select [1 or 2] (Default: 1): 1
```

Resume mode is intended to prevent unnecessary reprocessing and duplicate records.

---

## 11. Output Structure

Final datasets are stored in:

```text
output/final/
```

Expected files include:

```text
scraped_businesses.csv
scraped_businesses.xlsx
```

### Checkpoints

Incremental checkpoint files are stored in:

```text
output/checkpoints/
```

### Backups

Rolling backups are stored in:

```text
output/backup/
```

### Logs

Daily execution logs are stored in:

```text
logs/
```

Example:

```text
scraper_YYYY-MM-DD.log
```

---

## 12. Output Schema

The final dataset is designed around the master Excel template.

Core fields include:

| Field | Purpose |
|---|---|
| Sr. no | Sequential record number |
| Business/Company Name | Normalized business name |
| Business/Company Address | Full physical address |
| Business/Company Type | Entity classification |
| Pincode | Six-digit postal code |
| District Name | District |
| State Name | State |
| Location Name | Locality / landmark |
| Mobile number | Primary mobile |
| Mobile number 2 | Secondary mobile |
| Mobile number 3 | Additional mobile |
| Landline number | Fixed-line number |
| STD code | Area/STD code |
| Toll free number | Toll-free number |
| Email | Primary email |
| Website | Business website |
| Category | Business category |
| Rating | Google Maps rating |
| Reviews Count | Public review count |
| Location Link | Google Maps profile URL |
| Business Status | Operational/closure status |
| Additional fields | Website-derived and template-specific information |

The exact final schema remains controlled by:

```text
template/Formate_for_genral.xlsx
```

---

## 13. Processing Pipeline

A typical Variant A record flows through the following stages:

```text
Geographic Input
      ↓
Search Query Generation
      ↓
Google Maps Discovery
      ↓
Business Profile Extraction
      ↓
Address & Status Processing
      ↓
External Website Detection
      ↓
Deep Website Crawling
      ↓
Translation & Normalization
      ↓
Phone Classification
      ↓
Schema Validation
      ↓
Deduplication
      ↓
Checkpoint Storage
      ↓
Final Consolidation
      ↓
CSV + Excel Export
```

---

## 14. Deduplication Strategy

The system uses multiple signals rather than relying on a single field.

Priority signals can include:

1. Google Maps CID
2. Google Maps profile URL
3. Normalized profile URL
4. Business name + normalized mobile number
5. Address-derived identity

This multi-factor approach is intended to reduce duplicate leads caused by:
- Multiple Google Maps URLs for the same business
- Formatting differences
- Repeated search results
- Duplicate phone records
- Similar business names

---

## 15. Data Normalization

The processing layer handles common data-quality issues such as:

- Whitespace normalization
- Phone-number classification
- Mobile/landline separation
- Translation of supported multilingual text
- Business type classification
- Address normalization
- Invalid or incomplete record filtering

Raw identifiers that should not be translated or altered are preserved where required by the schema.

---

## 16. Performance & Reliability

The architecture is designed for large scraping workloads through:

- Async Playwright workers
- Controlled concurrency
- Resource filtering
- Incremental checkpoints
- Persistent progress tracking
- Atomic storage operations
- Rolling backups
- In-memory deduplication structures
- Separate processing and storage modules

For production workloads, start with a low worker count and increase gradually while monitoring CPU, RAM, network usage, and blocking behavior.

---

## 17. Variant Architecture

### Variant A — Active

**Non-Image Google Maps + Website Intelligence**

Focus:

```text
Google Maps
    +
Business Website
    +
Text/Data Processing
```

This is the currently active implementation.

### Variant B — Planned

**AI Image / Signboard / OCR Intelligence**

The planned image pipeline will introduce computer vision capabilities for:
- Business signboard detection
- Scene text extraction
- Signboard/entity matching
- Visual evidence scoring
- Visiting-card or image-based business identification

Planned technologies include:
- PaddleOCR
- OpenCV
- Pillow
- PyTorch
- RT-DETR / compatible object-detection tooling

These dependencies are intentionally excluded from the active installation to avoid unnecessary multi-gigabyte ML downloads.

---

## 18. Development Guidelines

When extending the project:

- Keep browser automation isolated from processing logic.
- Keep storage operations separate from scraping logic.
- Preserve the master Excel schema.
- Do not remove checkpoint functionality.
- Maintain resume compatibility when modifying progress state.
- Add new extraction logic through modular components.
- Validate new fields before final export.
- Keep Variant A and Variant B independently replaceable.

---

## 19. Troubleshooting

### Playwright browser not found

Run:

```bash
playwright install chromium
```

### Dependency installation problems

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Then reinstall:

```bash
pip install -r requirements.txt
```

### Scraper stops at a Google blocking page

Use visible browser mode, complete the displayed verification manually, and return to the terminal when prompted.

### Resume state is not behaving as expected

Check:

```text
output/progress.json
output/checkpoints/
logs/
```

Do not delete these files if you need to preserve the current session.

### Excel export problems

Verify that:

```text
template/Formate_for_genral.xlsx
```

exists and that its expected headers have not been changed.

---

## 20. Responsible Use

This software is intended for legitimate data collection, research, and business-data workflows.

Users are responsible for ensuring that their use complies with:
- Applicable laws and regulations
- Website terms of service
- Google policies
- Data-protection requirements
- Applicable privacy obligations

Do not use the system to collect, process, or distribute information in ways that violate applicable requirements.

---

## 21. License

Distributed under the **MIT License**. See `LICENSE` for details.

---

## 22. Project Status

| Component | Status |
|---|---|
| Variant A — Non-Image Scraper | **Active** |
| Google Maps discovery | **Active** |
| Business profile extraction | **Active** |
| Website crawling | **Active** |
| Translation/normalization | **Active** |
| Validation/deduplication | **Active** |
| Checkpoint/resume system | **Active** |
| CSV/Excel export | **Active** |
| Variant B — AI Image Intelligence | **Roadmap** |
| Signboard detection | **Planned** |
| OCR pipeline | **Planned** |
| Visual entity matching | **Planned** |

---

**Google Maps Intelligent Master Scraper — Variant A**  
*Modular • Fault-Tolerant • Resumeable • Schema-Oriented*
