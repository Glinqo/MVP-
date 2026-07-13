# -*- coding: utf-8 -*-
"Enterprise official JD crawler"
from scripts.crawler_framework import BaseCrawler
from bs4 import BeautifulSoup

class EnterpriseCrawler(BaseCrawler):
    def parse_list_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select("a[href*=job], a[href*=career], a[href*=position], a[href*=recruit]"):
            h = a.get("href", "")
            if h and h not in urls:
                if h.startswith("/"):
                    h = self.source.base_url.rstrip("/") + h
                urls.append(h)
        return urls[:15], None

    def parse_detail_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1, .position-title, .job-title, .title")
        body = soup.get_text(separator="\n", strip=True)
        from scripts.pipeline.cleaner import extract_fields_from_text
        fields = extract_fields_from_text(body)
        if title:
            fields["title"] = title.get_text(strip=True)
        return fields
