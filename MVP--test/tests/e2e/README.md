# Browser E2E Tests (Playwright)

## Install

```bash
pnpm install
pnpm exec playwright install chromium
```

## Run

```bash
pnpm exec playwright test          # headless
pnpm exec playwright test --headed # show browser
pnpm exec playwright test --ui     # UI mode
pnpm exec playwright show-report   # view HTML report
```

## Configuration

- `baseURL`: http://127.0.0.1:8765
- `workers`: 1 (intentional — tests share SQLite data)
- `webServer`: auto-starts `python -m app.server --port 8765`
- `trace`: retain-on-failure
- `screenshot`: only-on-failure

## Files

- `helpers/auth.js` — login helpers + error collectors
- `smoke.spec.js` — health check
- `teacher-login.spec.js` — teacher login smoke
