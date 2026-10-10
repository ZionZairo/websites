# Job Hunter — logistics & supply chain opportunities + tailored ATS CVs

Finds **graduate programmes, internships, learnerships and entry-level jobs** in logistics and supply
chain management, ranks them by fit, and generates a **tailored, ATS-friendly CV for each one** from a
single master CV. A built-in tracker records what you applied for.

```
 Sources ──► Classify & score ──► Tracker (SQLite) ──► Tailor (Claude) ──► Integrity check ──► .docx CV + report
 Adzuna API      grad/intern/         dedupes across       rewords bullets      strips anything        per job, with ATS
 Company feeds   learnership/job,     sources, keeps       in the advert's      not in master CV       score before/after
 Manual adds     fit 0-100            status + CV path     language                                    and honest gaps
```

## 1. Setup (once)

```bash
cd job-hunter
pip install -r requirements.txt
cp config.example.yaml config.yaml                      # search terms, regions, filters
cp profile/master_cv.example.yaml profile/master_cv.yaml  # YOUR CV — fill in everything
```

API keys go in environment variables (never in files):

| Variable | What for | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Rewording CVs per advert | console.anthropic.com |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Job search across SA boards (free tier) | developer.adzuna.com |

Without `ANTHROPIC_API_KEY` the tool still works but only **reorders** your CV (no rewording).

**Your master CV is the most important input.** Put every role, duty, project, tool and number in it.
The tailor can choose and reword, but it cannot add what isn't there.

## 2. Daily use

```bash
python -m jobhunter run                 # search + tailor the 5 best new matches
python -m jobhunter list                # everything found, best fit first
python -m jobhunter list --category learnership
python -m jobhunter tailor <id>         # tailor one specific job
python -m jobhunter status <id> applied # applied | interview | rejected | offer | skipped
python -m jobhunter export              # data/tracker.csv for Excel / Google Sheets
```

Found an advert on **LinkedIn, PNet, CareerJunction, Indeed, a SETA site or a company page**? Those
sites have no open API (and forbid scraping), so add them yourself — paste the advert text:

```bash
python -m jobhunter add --url https://company.co.za/careers/123 --company "Company" --title "Logistics Intern"
python -m jobhunter add --file advert.txt --company "Company"      # or: --file -  then paste, Ctrl-D
```

Each tailored job gets a folder in `output/`:

- `Name_CV_Company.docx` — the CV to submit (single column, no tables, standard headings)
- `report.md` — ATS keyword match before/after, missing keywords, honest **gaps**, integrity warnings
- `advert.txt`, `cv.txt`, `tailored.json` — for reference

## 3. Where jobs come from

| Source | Coverage | Notes |
|---|---|---|
| Adzuna (`za`) | Aggregates many SA job boards | Only a short snippet per advert; the tool fetches the full page at tailor time when it can |
| Company feeds | Employers on Greenhouse, Lever, SmartRecruiters | Full advert text — best tailoring. Add slugs under `sources.companies` |
| Manual `add` | Anything | Use for LinkedIn, PNet, SETA/government programmes, YES, company sites |

Classification rules (in `jobhunter/classify.py`): *learnership* (learnership, SETA, TETA, NQF level,
YES), *internship* (intern, in-service, WIL, experiential), *graduate programme* (graduate, trainee,
management trainee). Senior roles are filtered out by `exclude_title_words`.

## 4. The no-fabrication rule

Every tailored CV is checked against the master CV before it is written:

- every bullet must cite the master bullet it came from — untraceable bullets are dropped
- skills must come from your master skills list — new ones are dropped
- a reworded bullet may not contain numbers absent from the original — it is reverted

Anything the advert wants that you don't have is listed as a **gap** in `report.md`, so you can address
it in a cover letter or by upskilling, rather than claiming it. Always read the CV before you send it.

## 5. Run it automatically

Linux/macOS cron, every weekday at 07:00:

```cron
0 7 * * 1-5 cd /path/to/job-hunter && ANTHROPIC_API_KEY=... ADZUNA_APP_ID=... ADZUNA_APP_KEY=... python -m jobhunter run >> data/run.log 2>&1
```

Windows: Task Scheduler running `python -m jobhunter run` in the `job-hunter` folder.

## Tests

```bash
python -m pytest -q tests
```
