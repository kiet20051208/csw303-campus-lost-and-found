# Implementation Traceability

| Req ID | Story ID | Code Location | Test ID | Evidence |
| --- | --- | --- | --- | --- |
| FR-01 | US-01 | `Store.register`, `/register` in `campus_lost_found/app.py` | AUTH-01, AUTH-02 | Automated test report |
| FR-02 | US-02 | `Store.authenticate/logout`, `/login`, `/logout` | AUTH-03 to AUTH-06 | Automated test report |
| FR-03 | US-03 | `Store.create_report`, `/reports/new` | REP-01, REP-04 | Automated test report |
| FR-04 | US-04 | `Store.create_report`, `/reports/new` | REP-02, REP-04 | Automated test report |
| FR-07 | US-05 | `Store.list_reports`, `/reports` | SEARCH-01 | Automated test report |
| FR-08 | US-06 | `Store.list_reports`, `CampusLostFoundApp.report_list` | AT-US06-01 to 03 | Test report; performance CSV |
| FR-09 | US-07 | `Store.get_report`, `CampusLostFoundApp.detail_page` | REP-03 | Automated test report |
| FR-10 | US-08 (Partial) | `Store.matches_for` | Lifecycle exclusion only | Automated test report |
| FR-11 | US-09 | `Store.contact`, `/reports/{id}/contact` | AT-US09-01 to 03, SEC-01 | Automated test report |
| FR-13 | US-12 | `Store.mark_returned`, `/reports/{id}/returned`, `/history` | AT-US12-01 to 03, REL-01 to 04 | Automated test report |
| NFR-01 | US-06 | Indexed SQLite query in `Store.init_db/list_reports` | PERF-01 | `evidence/performance/PERF_Search_Filter_Timing.csv` |
| NFR-04 | US-09, US-12 | `require_user`, `normalize_text`, owner/admin authorization | SEC-01 to SEC-06 | Automated test report |
| NFR-05 | US-09 | Public projection in `Store.get_report`; escaped templates | REP-03, AT-US09-03 | Automated test report |
| NFR-06 | US-12 | Transactional update and `status_events` | REL-01 to REL-04 | Automated test report |

Deferred requirements FR-05, FR-06, FR-12, FR-14 and FR-15 have no invented code paths or tests. FR-10 is explicitly partial. NFR-02, NFR-03 and NFR-08 require evidence outside the automated local baseline.

