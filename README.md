# Campus Lost & Found

Helping the campus community reconnect with lost belongings.

## Project Overview

Campus Lost & Found is a server-rendered web application for students and university staff to report, find and recover belongings through one centralized, privacy-aware workflow. This repository contains the final executable baseline for the CSW303 Software Engineering project.

## Features

- Register, login, logout and persistent session authentication.
- Create structured Lost and Found reports in SQLite.
- Browse active reports and open privacy-safe details.
- Search by keyword and combine category, location and inclusive date filters (US-06).
- Record authenticated contact requests without exposing email or phone data (US-09).
- Suggest simple opposite-type matches using category, location and date.
- Allow only the owner or administrator to mark an Active report as Returned (US-12).
- Preserve Returned history and exclude resolved cases from active search and matching.
- Return controlled validation and authorization errors.

## Technology Stack

- Python 3.11+ standard library
- WSGI application served by `wsgiref.simple_server`
- Server-rendered HTML and responsive CSS
- SQLite persistent data store
- `unittest` automated test suite

No third-party runtime dependency is required.

## Architecture

The implementation follows the final three-tier C4 baseline: browser UI, Python WSGI application, and SQLite data store. Authentication, reporting, search/filter, contact/return lifecycle and repository responsibilities are separated in `campus_lost_found/app.py`. Accepted ADR-001 and ADR-002 are implemented. ADR-003 remains Proposed, so cloud image storage is intentionally not implemented.

Official final C4 diagrams and ADRs are under `docs/final/architecture/`.

## Repository Structure

```text
campus_lost_found/   Application, domain rules and SQLite repository
templates/           Server-rendered HTML shell
static/              Responsive presentation styling
tests/               Automated acceptance, security and reliability tests
scripts/             Database, demo seed and performance utilities
docs/                Audit, traceability, test matrix and final artifacts
evidence/            Evidence generated from the current implementation
instance/            Local SQLite database (ignored by Git)
run.py               Application entry point
```

## Prerequisites

- Python 3.11 or newer
- Git
- A current desktop browser

## Installation

```powershell
git clone https://github.com/kiet20051208/csw303-campus-lost-and-found.git
cd csw303-campus-lost-and-found
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For Command Prompt, activate with `.venv\Scripts\activate.bat`.

## Environment Setup

No secrets or environment variables are required for the local demo. The optional `CAMPUS_LF_DB` variable may point to a different SQLite file. Never commit personal credentials or an `.env` file.

## Database Initialization

```powershell
python scripts\init_db.py
```

The command creates `instance/campus_lost_found.db` and all tables automatically.

## Seed Demo Data

```powershell
python scripts\seed_demo_data.py
```

The seed command deliberately resets the selected database and inserts non-personal demonstration records with varied categories, locations and dates.

## Run Application

```powershell
python run.py
```

## Application URL

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the server with `Ctrl+C`.

## Demo Accounts

| Role | Email | Password |
| --- | --- | --- |
| Nguyen Minh Anh (report owner) | `minh.anh@campus.edu` | `Demo123!` |
| Tran Gia Bao (finder/contact user) | `gia.bao@campus.edu` | `Demo123!` |
| Demo administrator | `admin@campus.edu` | `Admin123!` |

These credentials contain demonstration data only.

## Run Tests

```powershell
python -m unittest discover -s tests -v
python scripts\measure_performance.py
```

The second command regenerates `evidence/performance/PERF_Search_Filter_Timing.csv` from real local SQLite queries.

## Final Presentation Demo

### Demo A

**Story:** US-06, Filter by category, location and date.

1. Login as `minh.anh@campus.edu`.
2. Open `/reports`.
3. Search `headphones`.
4. Select `Electronics`, `Main Library`, and a date interval containing the seeded report.
5. Show that every result satisfies all filters, date boundaries are inclusive, and an impossible combination shows the empty state.

### Demo B

**Stories:** US-09 Safe Contact and US-12 Mark item as Returned.

1. Login as `gia.bao@campus.edu`, open the lost headphones detail, and submit a contact request.
2. Observe the privacy notice and confirm that no private email or phone is displayed.
3. Login as `minh.anh@campus.edu`, open the same owner report, and mark it Returned.
4. Refresh and open `/history` to show persistence; the report no longer appears in active search/matching.
5. Optionally submit the Returned action as the other user to demonstrate a controlled `403` response.

## Documentation

- `docs/FINAL_IMPLEMENTATION_AUDIT.md`: honest documented-versus-implemented audit.
- `docs/ACCEPTANCE_TEST_MATRIX.md`: Given/When/Then acceptance mapping.
- `docs/IMPLEMENTATION_TRACEABILITY.md`: requirement-to-source-to-test evidence.
- `docs/final/`: official Week 6 C4, ADR, traceability and demo artifacts.

## Known Limitations

- Editing and closing/deleting reports (US-10/US-11) are not implemented.
- Optional image upload (FR-12) is not implemented; ADR-003 remains Proposed.
- Smart matching (US-08) is a transparent local score, not semantic or AI matching.
- Match notifications (US-13) and the administration dashboard/entity management (US-14) are not implemented.
- Availability, real-user usability and broad browser compatibility require external validation beyond this local course demo.
- The standard-library WSGI server is for local demonstration, not production Internet deployment.

## Team Members

- Duong Tan Kiet
- Le Cong Thach
- Nguyen Hoang Anh Khoi
- Hy Gia Long
