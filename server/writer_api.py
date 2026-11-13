#!/usr/bin/env python3
"""Small authenticated OpenAI-compatible writer API for the static workbench."""

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = int(os.getenv("WRITER_PORT", "18799"))
BASE_URL = os.getenv("AI_BASE_URL", "").rstrip("/")
MODEL = os.getenv("AI_MODEL", "")
API_KEY = os.getenv("AI_API_KEY", "")
DB_PATH = Path(os.getenv("WRITER_USAGE_DB", "/var/lib/gongzuotai-writer/usage.sqlite"))
PUBLIC_ORIGIN = "https://jjhbsai.com"
AUTH_URL = "http://127.0.0.1:18080/geo_admin/dashboard"
MAX_BODY = 18_000
MAX_DAILY = 30
MAX_HOURLY_PER_IP = 6


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def admin_authorized(cookie_header):
    match = re.search(r"(?:^|;\s*)geoflow-session=([^;]+)", cookie_header or "")
    if not match:
        return False
    request = urllib.request.Request(AUTH_URL, headers={
        "Host": "jjhbsai.com", "Cookie": "geoflow-session=" + match.group(1),
        "X-Forwarded-Proto": "https", "User-Agent": "gongzuotai-writer/1",
    }, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
            return response.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False


def configured():
    parsed = urlparse(BASE_URL)
    return bool(API_KEY and MODEL and parsed.scheme == "https" and parsed.hostname)


def reserve_quota(ip):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        db.execute("CREATE TABLE IF NOT EXISTS requests (at INTEGER NOT NULL, ip TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM requests WHERE at < ?", (now - 86400,))
        daily = db.execute("SELECT COUNT(*) FROM requests WHERE at >= ?", (now - 86400,)).fetchone()[0]
        hourly = db.execute("SELECT COUNT(*) FROM requests WHERE at >= ? AND ip = ?", (now - 3600, ip)).fetchone()[0]
        if daily >= MAX_DAILY or hourly >= MAX_HOURLY_PER_IP:
            return False
        db.execute("INSERT INTO requests(at, ip) VALUES(?, ?)", (now, ip))
        db.commit()
    return True


def strip_fence(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    return text


def generate(payload):
    topic = payload["topic"].strip()
    audience = payload.get("audience", "").strip()
    facts = payload.get("facts", "").strip()
    instruction = payload.get("instruction", "").strip()
    existing = payload.get("existing", "").strip()
    length = max(300, min(2000, int(payload.get("length") or 1000)))
    task = "根据用户要求改写现有文章，输出完整新版正文。" if existing else "根据用户主题写一篇完整的中文公众号文章。"
    system = (
        "你是严谨的中文公众号编辑。" + task +
        "文章要有具体开头、清晰小标题、实用结尾，不要空泛套话。"
        "只把用户提供的材料当作已知事实；不要编造政策条款、利率、贷款额度、机构名称、真实案例或数据。"
        "缺少关键依据时用【待核实：…】标记，不要把推测写成事实。"
        "只返回 JSON 对象，包含 title 和 body 两个字符串字段；body 使用 Markdown。"
    )
    user = (f"主题：{topic}\n目标读者：{audience or '普通读者'}\n目标正文字数：约{length}字\n"
            f"可核实的事实或素材：{facts or '暂无，请用待核实标记处理具体事实'}\n"
            f"修改要求：{instruction or '语言自然，讲清问题和可执行的判断步骤'}\n"
            f"现有文章：{existing or '暂无'}")
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.5, "max_tokens": 4096}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE_URL + "/chat/completions", data=body, headers={
        "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "gongzuotai-writer/1",
    }, method="POST")
    with urllib.request.urlopen(request, timeout=100) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("provider response too large")
    result = json.loads(raw)
    content = result["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("provider returned empty content")
    try:
        article = json.loads(strip_fence(content))
        title = str(article.get("title") or topic).strip()
        text = str(article.get("body") or "").strip()
    except (ValueError, TypeError, AttributeError):
        title, text = topic, content.strip()
    if not text:
        raise ValueError("provider returned empty article")
    return {"title": title[:500], "body": text[:30_000]}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/status":
            return self.send_json(404, {"error": "not_found"})
        self.send_json(200, {"configured": configured(),
                             "authorized": admin_authorized(self.headers.get("Cookie", ""))})

    def do_POST(self):
        if self.path != "/generate":
            return self.send_json(404, {"error": "not_found"})
        if self.headers.get("Origin") != PUBLIC_ORIGIN:
            return self.send_json(403, {"error": "invalid_origin"})
        if not admin_authorized(self.headers.get("Cookie", "")):
            return self.send_json(401, {"error": "login_required"})
        if not configured():
            return self.send_json(503, {"error": "model_not_configured"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                return self.send_json(413, {"error": "invalid_request_size"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or not isinstance(payload.get("topic"), str) or not payload["topic"].strip():
                return self.send_json(400, {"error": "topic_required"})
            for key, limit in (("topic", 240), ("audience", 300), ("facts", 6000), ("instruction", 1500), ("existing", 10000)):
                if not isinstance(payload.get(key, ""), str) or len(payload.get(key, "")) > limit:
                    return self.send_json(400, {"error": "invalid_" + key})
            if not reserve_quota(self.client_address[0]):
                return self.send_json(429, {"error": "daily_or_hourly_limit"})
            article = generate(payload)
            return self.send_json(200, article)
        except (ValueError, KeyError, TypeError):
            return self.send_json(502, {"error": "invalid_model_response"})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return self.send_json(502, {"error": "model_unavailable"})

    def log_message(self, format_string, *args):
        # Never log the user's article or any provider credentials.
        print("writer-api", self.address_string(), format_string % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
