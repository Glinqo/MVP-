# Crawler Source Map

This repository uses the two NanmiCoder crawler projects only as architecture references. No source files were copied.

## MediaCrawler

- Repository: `https://github.com/NanmiCoder/MediaCrawler`
- Inspected commit: `076dcba978b102bb12ff69ba226d1d39158481e5`
- License observed locally: `NON-COMMERCIAL LEARNING LICENSE 1.1`
- Usable ideas:
  - factory-style separation of platform/source handlers;
  - explicit command-line options and config-driven crawling;
  - save targets separated from collection logic;
  - low request count and clear crawl type boundaries;
  - run cleanup and error handling.
- Not reused:
  - source code;
  - login, QR code, cookie state, browser CDP, proxy pool, anti-detection, social media platform flows;
  - large-scale scraping patterns.

## CrawlerTutorial

- Repository: `https://github.com/NanmiCoder/CrawlerTutorial`
- Inspected commit: `43cc58cf48b6d070d48cc8525a481588e7b94fd7`
- License observed locally: no LICENSE file found; tutorial disclaimer says learning/reference use.
- Usable ideas:
  - engineering discipline: config, logging, retry, exception handling, storage, data cleaning;
  - small examples before complex collection;
  - maintenance-oriented project layout.
- Not reused:
  - code snippets;
  - anti-crawler evasion, CAPTCHA, login/session/cookie handling, proxy management.

## MVP Adaptation

The local updater is intentionally narrower than a crawler platform:

```text
approved source config
-> low-volume fetch or local file read
-> text cleanup
-> keyword and ability evidence extraction
-> pending graph proposals
-> teacher confirmation
-> optional daily schedule
```

This keeps the job graph current enough for a competition demo without turning the MVP into a scraping platform.
