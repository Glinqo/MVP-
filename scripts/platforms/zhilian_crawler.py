# -*- coding: utf-8 -*-
"Zhilian Zhaopin crawler"
from scripts.crawler_framework import BaseCrawler
from bs4 import BeautifulSoup

class ZhilianCrawler(BaseCrawler):
    def parse_list_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select("a[href*=job]"):
            h = a.get("href", "")
            if h and h not in urls:
                urls.append(h)
        next_btn = soup.select_one("a.next, .pagination-next")
        next_url = next_btn.get("href") if next_btn else None
        return urls[:20], next_url

    def parse_detail_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1, .job-title, [class*=title]")
        company = soup.select_one(".company-name, [class*=company]")
        body = soup.get_text(separator="\n", strip=True)
        from scripts.pipeline.cleaner import extract_fields_from_text
        fields = extract_fields_from_text(body)
        if title:
            fields["title"] = title.get_text(strip=True)
        if company:
            fields["company"] = company.get_text(strip=True)
        return fields
