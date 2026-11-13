#!/usr/bin/env python3
"""Build a cautious, replace-on-success article discovery snapshot."""

import argparse
import html
import json
import os
import random
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CST = timezone(timedelta(hours=8))
KEYWORDS = ("房贷", "贷款", "征信", "经营贷", "公积金", "信用卡", "负债", "逾期")
LARGE_ACCOUNTS = ("人民日报", "新华社", "央视", "新华网", "中国新闻网", "中国日报", "澎湃新闻", "界面新闻", "财联社", "北京日报", "虎嗅", "36氪", "第一财经", "21世纪经济报道")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 18
MAX_AGE_DAYS = 14


def clean(value):
    return re.sub(r"\s+", " ", BeautifulSoup(html.unescape(str(value or "")), "html.parser").get_text(" ", strip=True)).strip()


def image_url(value):
    value = html.unescape(str(value or "")).strip()
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("http://"):
        value = "https://" + value[7:]
    return value if value.startswith("https://") else ""


def is_large(author):
    return any(name in author for name in LARGE_ACCOUNTS)


def fresh(date_value, now):
    try:
        dt = datetime.fromisoformat(date_value).replace(tzinfo=CST)
    except (TypeError, ValueError):
        return False
    return now - timedelta(days=MAX_AGE_DAYS) <= dt <= now + timedelta(days=1)


def parse_sogou(page, keyword, now):
    soup = BeautifulSoup(page, "html.parser")
    if "请输入验证码" in page or "antispider" in page or "访问过于频繁" in page:
        raise ValueError("Sogou anti-bot page")
    result = []
    for li in soup.select("ul.news-list > li"):
        title_link = li.select_one("div.txt-box h3 a")
        author_node = li.select_one("span.all-time-y2")
        if not title_link or not author_node:
            continue
        title = clean(title_link)
        author = clean(author_node)
        if not title or is_large(author):
            continue
        stamp = re.search(r"timeConvert\(['\"](\d{10})['\"]\)", str(li))
        if not stamp:
            continue
        date = datetime.fromtimestamp(int(stamp.group(1)), CST).strftime("%Y-%m-%d %H:%M")
        if not fresh(date, now):
            continue
        link = urljoin("https://weixin.sogou.com", html.unescape(title_link.get("href", "")))
        if not link.startswith("https://weixin.sogou.com/link?"):
            continue
        img = li.select_one("div.img-box img")
        summary = li.select_one("p.txt-info")
        result.append({"source": "微信搜索", "title": title, "author": author,
                       "published_at": date, "url": link, "image": image_url(img.get("src") if img else ""),
                       "summary": clean(summary)[:180] if summary else "", "read_count": None,
                       "keyword": keyword, "followers_verified": False})
    return result


def embedded_cards(page):
    """Toutiao puts each result in a script call with a JSON `data` argument."""
    for script in re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.I | re.S):
        if "article_url" not in script or "data:" not in script:
            continue
        pos = script.find("data:") + len("data:")
        try:
            card, _ = json.JSONDecoder().raw_decode(script[pos:].lstrip())
        except (ValueError, TypeError):
            continue
        if isinstance(card, dict):
            yield card


def parse_toutiao(page, keyword, now):
    result = []
    for card in embedded_cards(page):
        candidates = card.get("display") if isinstance(card.get("display"), list) else [card]
        for item in candidates:
            if not isinstance(item, dict) or item.get("has_video") is not False:
                continue
            url = str(item.get("article_url") or "")
            host = urlparse(url).hostname or ""
            if host not in ("toutiao.com", "www.toutiao.com", "article.zlink.toutiao.com"):
                continue
            title = clean(item.get("title") or card.get("title"))
            author = clean(item.get("media_name") or card.get("media_name"))
            date = str(item.get("datetime") or card.get("datetime") or "")[:16]
            if not title or not author or is_large(author) or not fresh(date, now):
                continue
            try:
                reads = int(item.get("read_count") or 0)
            except (ValueError, TypeError):
                reads = 0
            result.append({"source": "今日头条", "title": title, "author": author,
                           "published_at": date, "url": url, "image": image_url(item.get("image_url")),
                           "summary": clean(item.get("abstract") or item.get("summary") or card.get("summary"))[:180],
                           "read_count": reads, "keyword": keyword, "followers_verified": False})
    return result


def fetch(session, url):
    response = session.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9", "Referer": "https://www.sogou.com/"}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def collect(output, now, sleep=True):
    session = requests.Session()
    by_source = {"微信搜索": [], "今日头条": []}
    success = {"微信搜索": 0, "今日头条": 0}
    errors = []
    for keyword in KEYWORDS:
        for page_no in (1, 2):
            url = f"https://weixin.sogou.com/weixin?type=2&ie=utf8&query={quote(keyword)}&page={page_no}"
            try:
                found = parse_sogou(fetch(session, url), keyword, now)
                by_source["微信搜索"].extend(found)
                success["微信搜索"] += 1
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"微信搜索 {keyword}/{page_no}: {type(exc).__name__}")
            if sleep:
                time.sleep(random.uniform(1.5, 3.5))
        url = f"https://so.toutiao.com/search?keyword={quote(keyword)}"
        try:
            found = parse_toutiao(fetch(session, url), keyword, now)
            by_source["今日头条"].extend(found)
            success["今日头条"] += 1
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"今日头条 {keyword}: {type(exc).__name__}")
    old = {}
    if output.exists():
        try:
            old = json.loads(output.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if not isinstance(old, dict):
        old = {}
    old_items = old.get("articles", [])
    # Keep recent discoveries when some queries are blocked or temporarily empty.
    # New results win during deduplication below; stale records expire after 14 days.
    for source in by_source:
        by_source[source].extend(item for item in old_items
                                 if item.get("source") == source and fresh(item.get("published_at"), now))
    seen = set()
    articles = []
    for item in sorted(sum(by_source.values(), []), key=lambda x: (x["published_at"], x.get("read_count") or 0), reverse=True):
        key = (item["source"], re.sub(r"\W+", "", item["title"]))
        if key in seen:
            continue
        seen.add(key)
        articles.append(item)
    if not articles:
        raise RuntimeError("No fresh articles; existing snapshot preserved")
    articles = articles[:200]
    previous_success = old.get("source_last_success", {})
    source_last_success = {source: (now.isoformat(timespec="seconds") if success[source]
                                    else previous_success.get(source, old.get("generated_at", "")))
                           for source in by_source}
    payload = {"generated_at": now.isoformat(timespec="seconds"), "article_count": len(articles),
               "image_count": sum(bool(item["image"]) for item in articles),
               "source_success": success, "source_last_success": source_last_success,
               "articles": articles}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".lowfan-", suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"saved {len(articles)} articles, {payload['image_count']} images; source requests: {success}; errors: {len(errors)}")
    for error in errors:
        print(error, file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "lowfan.json")
    parser.add_argument("--no-sleep", action="store_true", help="Only for fixture tests")
    args = parser.parse_args()
    collect(args.output, datetime.now(CST), sleep=not args.no_sleep)
