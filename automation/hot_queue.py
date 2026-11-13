#!/usr/bin/env python3
"""Turn the hourly hotspot snapshot into reviewable, source-linked story briefs.

This job never generates or publishes financial claims. A headline from a trend
list is a lead, not evidence; matched articles are reading material, not proof.
"""

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

CST = timezone(timedelta(hours=8))
TERMS = ("房贷", "贷款", "征信", "经营贷", "公积金", "信用卡", "负债", "逾期", "利率", "LPR", "担保", "税贷", "消费贷")
EXCLUDE = ("彩票", "赌博", "代孕", "明星", "演员", "去世", "死亡", "感染", "脱发")
PLATFORM_SEARCH = {
    "微博": "https://s.weibo.com/weibo?q=", "知乎": "https://www.zhihu.com/search?type=content&q=",
    "抖音": "https://www.douyin.com/search/", "今日头条": "https://www.toutiao.com/search/?keyword=",
    "百度": "https://www.baidu.com/s?wd=", "小红书": "https://www.xiaohongshu.com/search_result?keyword=",
    "哔哩哔哩": "https://search.bilibili.com/all?keyword=", "快手": "https://www.kuaishou.com/search/video?searchKey=",
    "微信": "https://weixin.sogou.com/weixin?type=2&query=", "雪球": "https://xueqiu.com/k?q=",
}


def relevant(title):
    text = title.lower()
    return any(term.lower() in text for term in TERMS) and not any(term in text for term in EXCLUDE)


def hot_items(page):
    match = re.search(r"var HOT_PLATFORMS\s*=\s*\[(.*?)\n\s*\];", page, re.S)
    if not match:
        raise ValueError("HOT_PLATFORMS snapshot not found")
    for platform, raw in re.findall(r'\{ name: "([^"]+)", rank: "[^"]+", color: "[^"]+", items: (\[.*?\])\}', match.group(1)):
        if platform not in PLATFORM_SEARCH:
            continue
        for rank, title in enumerate(json.loads(raw), 1):
            if relevant(title):
                yield {"platform": platform, "rank": rank, "hot_title": title,
                       "search_url": PLATFORM_SEARCH[platform] + quote(title)}


def article_candidates(snapshot, now):
    for item in snapshot.get("articles", []):
        if not relevant(str(item.get("title", ""))):
            continue
        try:
            when = datetime.fromisoformat(str(item.get("published_at", "")).replace(" ", "T")).replace(tzinfo=CST)
        except ValueError:
            continue
        if not now - timedelta(days=14) <= when <= now + timedelta(days=1):
            continue
        url = str(item.get("url", ""))
        if not url.startswith("https://"):
            continue
        yield {"title": item["title"], "publisher": item.get("author", ""),
               "published_at": item["published_at"], "url": url}


def build(index_text, snapshot, now):
    articles = list(article_candidates(snapshot, now))
    seen = set()
    briefs = []
    for hot in hot_items(index_text):
        title = hot["hot_title"]
        key = re.sub(r"\W+", "", title.lower())
        if key in seen:
            continue
        seen.add(key)
        terms = [term for term in TERMS if term.lower() in title.lower()]
        related = [a for a in articles if any(term.lower() in a["title"].lower() for term in terms)][:3]
        briefs.append({"topic": title, "platform": hot["platform"], "rank": hot["rank"],
                       "trend_search_url": hot["search_url"], "reading": related,
                       "writing_angle": "解释该话题与借款人或小微企业主的关系；先核实原始消息、日期和适用地区。",
                       "status": "needs_fact_check", "auto_publish_eligible": False})
    briefs.sort(key=lambda x: (not bool(x["reading"]), x["rank"], x["platform"]))
    return {"generated_at": now.isoformat(timespec="seconds"), "count": len(briefs),
            "policy": "热点和搜索结果仅作选题线索；未经官方原始资料核实，不得自动生成事实性结论或发布。",
            "briefs": briefs[:30]}


def write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".editorial-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--index", type=Path, default=root / "index.html")
    parser.add_argument("--articles", type=Path, default=root / "lowfan.json")
    parser.add_argument("--output", type=Path, default=root / "editorial_queue.json")
    args = parser.parse_args()
    result = build(args.index.read_text(encoding="utf-8"),
                   json.loads(args.articles.read_text(encoding="utf-8")), datetime.now(CST))
    if not result["briefs"]:
        raise SystemExit("no relevant topics; existing queue preserved")
    write_atomic(args.output, result)
    print("saved", result["count"], "relevant topics; showing", len(result["briefs"]))

