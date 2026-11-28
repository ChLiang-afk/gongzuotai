import os
import sys
import re
import json
import argparse
from datetime import datetime, timezone, timedelta

# User requested: pip install requests
try:
    import requests
except ImportError:
    print("requests not installed. Please run: pip install requests")
    sys.exit(1)

CST = timezone(timedelta(hours=8))

class MappingHistoryStore:
    def __init__(self, filepath="data/history_state.json"):
        self.filepath = filepath
        self.history = []
        self._load()
        
    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"Error loading history: {e}")
                
    def get_last_pinned(self):
        if self.history and len(self.history) > 0:
            return self.history[-1].get("pinned", [])
        return []
        
    def get_last_fin(self):
        if self.history and len(self.history) > 0:
            return self.history[-1].get("fin", [])
        return []

    def get_last_timestamp(self):
        if self.history and len(self.history) > 0:
            return self.history[-1].get("timestamp")
        return None

    def save_round(self, pinned_items, fin_groups):
        state = {
            "timestamp": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
            "pinned": pinned_items,
            "fin": fin_groups
        }
        self.history.append(state)
        self.history = self.history[-2:]
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

def categorize_fin_title(title):
    title = title.lower()
    if any(k in title for k in ["罚单", "罚款", "监管", "证监会", "银保监", "金管局", "违规", "禁止", "处分", "警告"]):
        return "监管处罚"
    if any(k in title for k in ["经营贷", "企业贷", "小微", "个体户", "续贷", "无还本", "延期"]):
        return "经营贷实操"
    if any(k in title for k in ["公积金", "个税", "税务", "养老金"]):
        return "公积金个税"
    if any(k in title for k in ["征信", "风控", "黑名单", "逾期", "老赖", "限高", "法拍", "不良"]):
        return "征信风控"
    if any(k in title for k in ["房抵", "抵押", "按揭", "房贷", "首付", "楼市", "二手房", "房地产"]):
        return "房抵贷"
    if any(k in title for k in ["贷款", "lpr", "利率", "央行", "降息", "准备金", "信贷", "银行", "放款", "降准"]):
        return "信贷政策"
    return None

def parse_fin_title(title):
    title = re.sub(r'<[^>]+>', '', title).strip()
    match = re.search(r'【(.*?)】', title)
    if match and len(match.group(1)) <= 40:
        return match.group(1).strip()
        
    title = title.split('。')[0]
    if len(title) > 40:
        title = title[:37] + "..."
    return title.strip()

def fetch_tunbang_platform(name, rank, color, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"Failed to fetch {name}: {e}")
        return None
        
    m_time = re.search(r'数据更新于\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', html)
    if m_time:
        updated = m_time.group(1)
    else:
        updated = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
        
    items = []
    m_list = re.search(r'<ol[^>]*id="list"[^>]*>(.*?)</ol>', html, re.DOTALL)
    if m_list:
        list_html = m_list.group(1)
        lis = re.findall(r'<li[^>]*class="row"[^>]*>(.*?)</li>', list_html, re.DOTALL)
        for li in lis:
            t_match = re.search(r'<a[^>]*class="row-title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.DOTALL)
            h_match = re.search(r'<span[^>]*class="hot"[^>]*>(.*?)</span>', li, re.DOTALL)
            
            if t_match:
                u = t_match.group(1).replace('&amp;', '&').strip()
                t = re.sub(r'<[^>]+>', '', t_match.group(2)).strip()
                h = re.sub(r'<[^>]+>', '', h_match.group(1)).strip() if h_match else ""
                
                if t and u:
                    items.append({"t": t, "h": h, "u": u})
                    
    if items:
        return {
            "name": name,
            "rank": rank,
            "color": color,
            "live": True,
            "updated": updated,
            "items": items
        }
    return None

def fetch_tunbang(old_by_name=None):
    # Order / rank / color aligned to the live page (2026-11-15 08:00 version)
    platforms_def = [
        ("微博", "热搜", "#c0452f", "https://www.tunbang.com/hot/weibo/"),
        ("知乎", "热榜", "#1772d6", "https://www.tunbang.com/hot/zhihu/"),
        ("抖音", "热榜", "#3a3f4a", "https://www.tunbang.com/hot/douyin/"),
        ("今日头条", "热榜", "#d43a2f", "https://www.tunbang.com/hot/toutiao/"),
        ("百度", "热搜", "#315efb", "https://www.tunbang.com/hot/baidu/"),
        ("哔哩哔哩", "热门", "#e56a9a", "https://www.tunbang.com/hot/bilibili/"),
        ("豆瓣", "热议", "#4a9e4d", "https://www.tunbang.com/hot/douban-group/"),
        ("虎扑", "热帖", "#b03a2e", "https://www.tunbang.com/hot/hupu/"),
        ("快手", "热议", "#e07b24", "https://www.tunbang.com/hot/kuaishou/"),
    ]
    
    results = []
    for p in platforms_def:
        data = fetch_tunbang_platform(*p)
        if data:
            results.append(data)
        elif old_by_name and p[0] in old_by_name:
            # Fetch failed: keep the previous round's group instead of
            # writing an empty one, so the page never shows an empty card.
            print(f"Warning: {p[0]} fetch failed, keeping previous round")
            results.append(old_by_name[p[0]])
        else:
            print(f"Warning: {p[0]} fetch failed, no previous data, skipping")
    return results

def fetch_fin_cls(seen):
    items = []
    pinned = []
    try:
        r = requests.get("https://m.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&rn=50", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        for item in data.get('data', {}).get('roll_data', []):
            title = item.get('title') or item.get('content')
            if not title: continue
            title = parse_fin_title(title)
            url = f"https://www.cls.cn/detail/{item.get('id')}"
            
            cat = categorize_fin_title(title)
            if cat and title not in seen:
                seen.add(title)
                is_pinned = str(item.get('level', '0')) == '1'
                if is_pinned and len(pinned) < 3:
                    ctime = item.get('ctime')
                    if ctime:
                        pub = datetime.fromtimestamp(int(ctime), CST).strftime("%Y-%m-%d %H:%M")
                    else:
                        pub = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
                    pinned.append({"t": title, "c": cat, "u": url, "pin": True, "pub": pub})
                else:
                    items.append({"t": title, "c": cat, "u": url})
        return items, pinned
    except Exception as e:
        print(f"CLS fetch error: {e}")
        return None, None

def fetch_fin_sina(seen):
    items = []
    try:
        r = requests.get("https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=50&zhibo_id=152", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        for item in data.get('result', {}).get('data', {}).get('feed', {}).get('list', []):
            title = item.get('rich_text') or item.get('docurl')
            if not title: continue
            
            # Top-level docurl is now the sina.cn mobile detail page
            # (finance.sina.cn/7x24/detail-....d.html), which the hot-plaza
            # rules forbid: on phones it jumps to the bank channel page.
            # The desktop article address lives inside ext as docurl:
            # finance.sina.com.cn/7x24/<date>/doc-<id>.shtml (verified
            # 2026-11-27 12:27 CST: opens as its own page, title matches).
            # /roll/ is kept as a fallback for older items.
            url = item.get('docurl', '')
            try:
                ext_url = (json.loads(item.get('ext') or '{}') or {}).get('docurl', '')
            except Exception:
                ext_url = ''
            if ext_url:
                url = ext_url
            if not url or 'finance.sina.com.cn/' not in url or not re.search(r'/(roll|7x24)/\d{4}-\d{2}-\d{2}/doc-[a-zA-Z0-9_-]+\.shtml', url):
                continue
                
            title = parse_fin_title(title)
            cat = categorize_fin_title(title)
            if cat and title not in seen:
                seen.add(title)
                items.append({"t": title, "c": cat, "u": url})
        return items if items else None
    except Exception as e:
        print(f"Sina fetch error: {e}")
        return None

def fetch_fin_tunbang(url, seen):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        html = r.text
        items = []
        m_list = re.search(r'<ol[^>]*id="list"[^>]*>(.*?)</ol>', html, re.DOTALL)
        if m_list:
            list_html = m_list.group(1)
            lis = re.findall(r'<li[^>]*class="row"[^>]*>(.*?)</li>', list_html, re.DOTALL)
            for li in lis:
                t_match = re.search(r'<a[^>]*class="row-title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.DOTALL)
                if t_match:
                    u = t_match.group(1).replace('&amp;', '&').strip()
                    t = re.sub(r'<[^>]+>', '', t_match.group(2)).strip()
                    t = parse_fin_title(t)
                    cat = categorize_fin_title(t)
                    if cat and t not in seen:
                        seen.add(t)
                        items.append({"t": t, "c": cat, "u": u})
        return items
    except Exception as e:
        print(f"Tunbang Fin fetch error {url}: {e}")
        return None

def fetch_finance(store):
    # Group name / rank / color aligned to the live page (2026-11-15 08:00).
    # NOTE: /hot/tencent/, /hot/eastmoney/, /hot/jin10/ do not exist on
    # Tunbang (HTTP 404, verified 2026-11-15). Those three sources fall
    # back to history until a real endpoint is found; do not invent one.
    # The CLS telegraph API is also dead (HTTP 404 as of 2026-11-15).
    sources = [
        {"name": "财联社", "rank": "电报", "color": "#c0392b"},
        {"name": "腾讯新闻", "rank": "热点榜", "color": "#0052d9", "tb_url": "https://www.tunbang.com/hot/tencent/"},
        {"name": "新浪财经", "rank": "7×24快讯", "color": "#f26522"},
        {"name": "36氪热榜", "rank": "热榜", "color": "#0056ff", "tb_url": "https://www.tunbang.com/hot/36kr/"},
        {"name": "虎嗅", "rank": "热榜", "color": "#b8860b", "tb_url": "https://www.tunbang.com/hot/huxiu/"},
        {"name": "东方财富", "rank": "快讯", "color": "#d81e06", "tb_url": "https://www.tunbang.com/hot/eastmoney/"},
        {"name": "金十数据快讯", "rank": "快讯", "color": "#0a45b8", "tb_url": "https://www.tunbang.com/hot/jin10/"}
    ]
    
    last_fin = store.get_last_fin()
    last_pinned = store.get_last_pinned()
    last_fin_dict = {g["name"]: g for g in last_fin if "name" in g}
    
    new_fin_groups = []
    seen = set()
    pinned = []
    pinned_fresh = False
    
    for s in sources:
        name = s["name"]
        items = None
        
        if name == "财联社":
            items, p = fetch_fin_cls(seen)
            if p is not None and len(p) > 0:
                pinned = p
                pinned_fresh = True
            elif not pinned and last_pinned:
                pinned = last_pinned
                print("Warning: CLS pinned empty, using history")
        elif name == "新浪财经":
            items = fetch_fin_sina(seen)
        else:
            items = fetch_fin_tunbang(s["tb_url"], seen)
            
        if items is None or len(items) == 0:
            print(f"Warning: {name} fetch empty or failed, using history")
            if name in last_fin_dict:
                new_fin_groups.append(last_fin_dict[name])
            else:
                # No data and no history: skip the group entirely.
                # Never write an empty finance group to the page.
                print(f"Warning: {name} has no history, skipping group")
        else:
            new_fin_groups.append({
                "name": name,
                "rank": s["rank"],
                "color": s["color"],
                "live": True,
                "fin": True,
                "updated": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
                "items": items
            })
            
    if not pinned and last_pinned:
        pinned = last_pinned
        print("Warning: CLS pinned overall empty, using history")
        
    return pinned, new_fin_groups, pinned_fresh

def _find_balanced_json_span(text, start_idx):
    stack = []
    in_string = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
        elif ch == '"' or ch == "'":
            if not in_string:
                in_string = ch
            elif in_string == ch:
                in_string = False
        elif not in_string:
            if ch in ['[', '{']:
                stack.append(ch)
            elif ch in [']', '}']:
                if not stack: return -1
                last = stack.pop()
                if (ch == ']' and last != '[') or (ch == '}' and last != '{'):
                    return -1
                if not stack:
                    return i + 1
    return -1

def _load_existing_platforms(html):
    """Parse the current HOT_PLATFORMS array (JS literal, unquoted keys
    allowed) into {name: group}. Used as fallback when a fetch fails."""
    start_idx = html.find('var HOT_PLATFORMS')
    if start_idx == -1:
        return {}
    bracket_start = html.find('[', start_idx)
    end_idx = _find_balanced_json_span(html, bracket_start)
    if end_idx == -1:
        return {}
    try:
        import subprocess
        js = "const a=" + html[bracket_start:end_idx] + ";console.log(JSON.stringify(a));"
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            groups = json.loads(out.stdout)
            return {g["name"]: g for g in groups if "name" in g}
    except Exception as e:
        print(f"Warning: could not parse existing HOT_PLATFORMS: {e}")
    return {}

def update_document(repo_root):
    index_path = os.path.join(repo_root, "index.html")
    if not os.path.exists(index_path):
        print(f"Error: {index_path} not found")
        sys.exit(1)
        
    store = MappingHistoryStore(os.path.join(repo_root, "data", "history_state.json"))
    # Capture the previous round's timestamp BEFORE save_round() appends
    # the new one; it is what the pinned strip shows when pinned items
    # come from history.
    prev_timestamp = store.get_last_timestamp()

    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()
    old_by_name = _load_existing_platforms(html)
    
    print("Fetching Tunbang...")
    tb_data = fetch_tunbang(old_by_name)
    
    print("Fetching Finance...")
    pinned, fin_groups, pinned_fresh = fetch_finance(store)
    
    store.save_round(pinned, fin_groups)

    now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    final_fin_groups = []
    if pinned:
        if pinned_fresh:
            pinned_updated = now_str
        else:
            # Pinned came from history: show when that data was fetched,
            # not "now", so the strip never pretends old items are fresh.
            pinned_updated = prev_timestamp or now_str
        final_fin_groups.append({
            "name": "财联社置顶",
            "rank": "置顶",
            "color": "#c8102e",
            "live": True,
            "fin": True,
            "pinned": True,
            "updated": pinned_updated,
            "items": pinned[:3]
        })
        
    final_fin_groups.extend(fin_groups)
    
    final_platforms = final_fin_groups + tb_data
    
    start_idx = html.find('var HOT_PLATFORMS')
    if start_idx == -1:
        print("Could not find var HOT_PLATFORMS")
        sys.exit(1)
        
    bracket_start = html.find('[', start_idx)
    end_idx = _find_balanced_json_span(html, bracket_start)
    
    if end_idx == -1:
        print("Could not find balanced JSON span for HOT_PLATFORMS")
        sys.exit(1)
        
    json_str = json.dumps(final_platforms, ensure_ascii=False, indent=2)
    new_js = "[\n" + json_str[1:-1] + "\n]"
    html = html[:bracket_start] + new_js + html[end_idx:]
    
    pattern = r'(\bHOT_UPDATED\s*=\s*)(["\'])(.*?)\2'
    html = re.sub(pattern, rf'\g<1>\g<2>{now_str}\g<2>', html)
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print("Successfully updated index.html")
    print(f"Tunbang platforms fetched: {len(tb_data)}")
    for d in tb_data:
        items = d.get('items', [])
        count = len(items)
        if count > 0:
            first = items[0]['t'][:10]
            last = items[-1]['t'][:10]
            print(f" - {d['name']}: {count} items. First: {first}... Last: {last}...")
        else:
            print(f" - {d['name']}: 0 items.")
            
    print(f"Finance groups: {len(fin_groups)}")
    for g in fin_groups:
        print(f" - {g['name']}: {len(g.get('items', []))} items")
        
    print(f"Pinned items: {len(pinned)}")
    for p in pinned:
        print(f" - Pinned: {p['t']} (pub: {p.get('pub', '')})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".", help="Root directory of the repo")
    args = parser.parse_args()
    update_document(args.repo_root)
