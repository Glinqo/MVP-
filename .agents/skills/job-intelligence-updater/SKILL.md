---
name: job-intelligence-updater
description: Use when collecting public job or industry material, generating teacher-reviewable job ability graph proposals, or scheduling daily job intelligence updates for the mechatronics MVP.
---

# Job Intelligence Updater

## Purpose

This skill supports a lightweight, compliant "job intelligence -> ability graph proposal" workflow for the mechatronics training MVP. It gathers explicitly configured public or local materials about the target role, extracts rough ability evidence, and writes pending job graph update proposals for teacher review.

It is inspired by the engineering structure of MediaCrawler and CrawlerTutorial, but it does not copy their source code and does not implement social-platform login, cookie reuse, proxy pools, CAPTCHA handling, anti-detection, or large-scale crawling.

## When To Use

Use this skill when the user asks to:

- collect current job-role information for the automation-line commissioning and maintenance technician role;
- update the job ability graph from public job descriptions, enterprise materials, industry pages, or teacher-imported text;
- create daily scheduled updates for job ability graph proposals;
- inspect why a job graph update proposal was generated.

Do not use this skill for broad web crawling, social media scraping, account-based scraping, or collecting personal data.

## Workflow

1. Check the source policy and borrowed-pattern map in `references/crawler_source_map.md`.
2. Inspect `knowledge/job_intelligence_sources.json`.
3. For a first pass, run a dry run:

   ```powershell
   python scripts/job_intelligence_update.py --dry-run
   ```

4. If the dry run only uses approved sources and the summary is reasonable, run:

   ```powershell
   python scripts/job_intelligence_update.py
   ```

5. Review pending proposals in `data/job_graph_update_proposals.json` or through the API/UI.
6. Only confirm proposals when the user or teacher explicitly asks. Confirmation changes the formal job graph snapshot.
7. If daily updates are requested, install a Windows scheduled task:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/install_daily_job_intelligence_update.ps1 -Time "07:30"
   ```

## Hard Constraints

- Source URLs must be explicitly listed in `knowledge/job_intelligence_sources.json`.
- Respect robots.txt and site terms. Keep request volume low.
- Do not bypass login, paywalls, CAPTCHA, rate limits, safety controls, or platform restrictions.
- Do not use proxies, browser anti-detection, cookie export, QR login, SMS login, or session hijacking.
- Do not write directly into the confirmed job graph. Generate pending proposals first.
- Keep every proposal source traceable with `source`, `source_type`, `collected_at`, and material excerpts.
- If a source is not clearly allowed, skip it and ask the user to provide an exported document or an approved URL.

## Local Commands

Dry run with default sources:

```powershell
python scripts/job_intelligence_update.py --dry-run
```

Run one configured source:

```powershell
python scripts/job_intelligence_update.py --source-id demo_local_automation_job_seed
```

Run with a custom source file:

```powershell
python scripts/job_intelligence_update.py --sources path\to\sources.json --dry-run
```

Install daily update:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_daily_job_intelligence_update.ps1 -TaskName "MechatronicsJobGraphDaily" -Time "07:30"
```

## Output Contract

`scripts/job_intelligence_update.py` prints a JSON summary:

```json
{
  "ok": true,
  "dry_run": false,
  "collected_count": 1,
  "matched_abilities": [],
  "proposal_batch_id": "JP...",
  "proposal_count": 3,
  "skipped_sources": []
}
```

Normal runs may append `data/job_intelligence_runs.json` and `data/job_graph_update_proposals.json`. Dry runs should not mutate runtime data.

## Validation

After changing this skill or the updater:

```powershell
python tests/job_intelligence_update.test.py
python -m compileall -q scripts app tests
python tests/api_smoke.test.py
```

If JSON source files changed, also run a JSON parse check across the repository.
