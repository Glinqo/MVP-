# -*- coding: utf-8 -*-
"""Base crawler framework - Scrapling-compatible"""
import hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CrawlerSource:
    def __init__(self, config):
        self.id = config.get("id", "unknown")
        self.name = config.get("name", "")
        self.source_type = config.get("source_type", "unknown")
        self.enabled = config.get("enabled", False)
        self.base_url = config.get("base_url", "")
        self.search_url = config.get("search_url", "")
        self.rate_limit_s = float(config.get("rate_limit_s", 3.0))
        self.max_pages = int(config.get("max_pages", 10))
        self.local_path = config.get("local_path", "")
        self.fields = config.get("fields", [])

class FetchResult:
    def __init__(self, url, html, status_code, fetch_time):
        self.url = url
        self.html = html
        self.status_code = status_code
        self.fetch_time = fetch_time
        self.content_hash = hashlib.md5((html or "").encode("utf-8")).hexdigest()[:16]
        self.url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]

class BaseCrawler:
    def __init__(self, source_config):
        self.source = CrawlerSource(source_config)
        self.last_fetch_time = 0
        self.stats = {"fetched": 0, "failed": 0, "deduplicated": 0}

    def _headers(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        return {"User-Agent": ua, "Accept": "text/html,*/*", "Accept-Language": "zh-CN,zh;q=0.9"}

    def fetch(self, url):
        now = time.time()
        elapsed = now - self.last_fetch_time
        if elapsed < self.source.rate_limit_s:
            time.sleep(self.source.rate_limit_s - elapsed)
        self.last_fetch_time = time.time()
        try:
            import requests
            resp = requests.get(url, headers=self._headers(), timeout=15)
            result = FetchResult(url, resp.text, resp.status_code, datetime.now(timezone.utc).isoformat())
            self.stats["fetched" if resp.status_code == 200 else "failed"] += 1
            return result
        except Exception:
            self.stats["failed"] += 1
            return FetchResult(url, "", 0, datetime.now(timezone.utc).isoformat())

    def parse_list_page(self, html):
        raise NotImplementedError

    def parse_detail_page(self, html):
        raise NotImplementedError

    def crawl(self):
        if not self.source.enabled:
            return []
        events = []
        cur = self.source.search_url
        page = 0
        while cur and page < self.source.max_pages:
            result = self.fetch(cur)
            if result.status_code != 200:
                break
            urls, cur = self.parse_list_page(result.html)
            for u in urls[:10]:
                d = self.fetch(u)
                if d.status_code == 200:
                    events.append(self.parse_detail_page(d.html))
            page += 1
        return events

    def dry_run(self, html=None):
        if html is None and self.source.local_path:
            p = ROOT / self.source.local_path
            if p.exists():
                html = p.read_text(encoding="utf-8")
        if html:
            jobs, _ = self.parse_list_page(html)
            return {"source_id": self.source.id, "jobs_found": len(jobs) if jobs else 0, "sample": (jobs or [])[:3]}
        return {"source_id": self.source.id, "error": "no html provided"}

    def load_local_posts(self):
        if not self.source.local_path:
            return []
        p = ROOT / self.source.local_path
        if not p.exists():
            return []
        raw = p.read_text(encoding="utf-8")
        if raw.strip().startswith("["):
            try:
                return json.loads(raw)[:self.source.max_pages]
            except json.JSONDecodeError:
                pass
        from scripts.pipeline.cleaner import extract_fields_from_text
        posts = []
        for sec in raw.split("---"):
            s = sec.strip()
            if len(s) > 50:
                posts.append(extract_fields_from_text(s))
        return posts[:self.source.max_pages]


def load_sources():
    p = ROOT / "knowledge" / "job_intelligence_sources.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("sources", [])


def get_crawler(source_config):
    st = source_config.get("source_type", "")
    sid = source_config.get("id", "")
    if st == "local_file":
        return BaseCrawler(source_config)
    if "zhilian" in sid or "zhaopin" in sid:
        from scripts.platforms.zhilian_crawler import ZhilianCrawler
        return ZhilianCrawler(source_config)
    if "boss" in sid:
        from scripts.platforms.boss_crawler import BossCrawler
        return BossCrawler(source_config)
    if "qiancheng" in sid:
        from scripts.platforms.qiancheng_crawler import QianchengCrawler
        return QianchengCrawler(source_config)
    if "siemens" in sid or "inovance" in sid or "byd" in sid:
        from scripts.enterprises.typical_manufacturing import EnterpriseCrawler
        return EnterpriseCrawler(source_config)
    return BaseCrawler(source_config)