# -*- coding: utf-8 -*-
"Qiancheng 51job crawler"
from scripts.crawler_framework import BaseCrawler
from bs4 import BeautifulSoup

class QianchengCrawler(BaseCrawler):
    def parse_list_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select("a[href*=job], a[href*=position], .job-list a"):
            h = a.get("href", "")
            if h and h not in urls:
                urls.append(h)
        return urls[:20], None

    def parse_detail_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1, .job-title, .title")
        company = soup.select_one(".company_name, .company, .cname")
        body = soup.get_text(separator="\n", strip=True)
        from scripts.pipeline.cleaner import extract_fields_from_text
        fields = extract_fields_from_text(body)
        if title:
            fields["title"] = title.get_text(strip=True)
        if company:
            fields["company"] = company.get_text(strip=True)
        return fields
