#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陈安叙工作台 · 每日数据刷新脚本（部署版）
========================================
本脚本放在仓库根目录，自动定位同目录下的 index.html：
  - 本地双击运行：刷新你电脑上的工作台
  - GitHub Actions 运行：刷新仓库里的数据并提交，Pages 自动生效
仅使用 Python 标准库，无需 pip 安装任何依赖。
"""

import os
import re
import json
import ssl
import urllib.request
import urllib.parse
import urllib.error
import datetime
import hashlib

# 自动定位：脚本所在目录的 index.html（兼容本地与 GitHub Actions）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATHS = [os.path.join(SCRIPT_DIR, "index.html")]
OUT_DIR = SCRIPT_DIR

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

DOUYIN_SOURCES = [
    "https://api.vvhan.com/api/hotlist/douyin",
    "https://api.oioweb.cn/api/common/DouYinHot",
    "https://tenapi.cn/v2/douyinhot",
    "https://api.pearktrue.cn/api/douyinhot/",
]
HOT_SOURCES = [
    ("https://api.vvhan.com/api/hotlist/wbHot", "微博热搜"),
    ("https://api.vvhan.com/api/hotlist/baidu", "百度热搜"),
    ("https://api.vvhan.com/api/hotlist/zhihu", "知乎热榜"),
    ("https://api.oioweb.cn/api/common/HotList?type=wbHot", "微博热搜"),
]
FINANCE_SOURCES = [
    "https://api.vvhan.com/api/hotlist/finance",
    "https://tenapi.cn/v2/caijing",
    "https://api.oioweb.cn/api/common/EastMoney",
    "https://newsapi.eastmoney.com/kuaixun/v1/get?type=1&page_size=20&page_index=1",
]

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def now_date_weekday():
    d = datetime.datetime.now()
    return f"{d.month:02d}月{d.day:02d}日", WEEKDAYS[d.weekday()]


def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def try_sources_json(urls):
    last_err = None
    for u in urls:
        try:
            return fetch_json(u)
        except Exception as e:  # noqa
            last_err = e
            continue
    raise last_err or RuntimeError("all sources failed")


def dig_list(raw):
    data = raw
    if isinstance(raw, dict):
        for k in ("data", "result", "list", "items", "news", "rows"):
            v = raw.get(k)
            if isinstance(v, list):
                data = v
                break
        else:
            for v in raw.values():
                if isinstance(v, list):
                    data = v
                    break
    if isinstance(data, dict):
        for k in ("list", "items", "data", "news", "rows"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list):
        return []
    return data


def pick_text(it, *keys):
    for k in keys:
        v = it.get(k) if isinstance(it, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def pick_int(it, *keys):
    for k in keys:
        v = it.get(k) if isinstance(it, dict) else None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    return 0


def short_id(prefix, s):
    return prefix + hashlib.md5(s.encode("utf-8")).hexdigest()[:8]


def douyin_search(topic):
    return "https://www.douyin.com/search/" + urllib.parse.quote(topic) + "?type=general"


def build_ideas(live):
    items = []
    for i, it in enumerate(live[:30], 1):
        it = it if isinstance(it, dict) else {"title": str(it)}
        topic = pick_text(it, "title", "word", "name", "topic", "query")
        if not topic:
            continue
        items.append({
            "rank": i,
            "topic": topic,
            "heat": pick_int(it, "hot", "heat", "num", "hotScore"),
            "videos": pick_int(it, "videos", "video_count"),
            "type": pick_text(it, "type", "category") or "实时上升热点",
            "insight": pick_text(it, "insight", "desc", "description")
                       or "热点事件，从你的视角解读能快速涨粉",
            "link": douyin_search(topic),
            "scheme": "snssdk1128://search/" + topic,
        })
    return items


def build_hot(live, source_name):
    items = []
    for i, it in enumerate(live[:30], 1):
        it = it if isinstance(it, dict) else {"title": str(it)}
        title = pick_text(it, "title", "word", "name", "topic", "query")
        if not title:
            continue
        hv = pick_int(it, "hot", "heat", "num", "hotScore", "heatValue")
        items.append({
            "id": short_id("h", title),
            "title": title,
            "category": pick_text(it, "category", "tag") or "热门话题",
            "heat": ("热搜 %d万热度" % (hv // 10000)) if hv else "热搜",
            "heatValue": hv,
            "why": pick_text(it, "why", "reason") or "话题自带搜索流量，及时跟进能抢占先机",
            "angle": "结合你的赛道特色，对「%s」做差异化改编" % title,
            "source": pick_text(it, "source") or source_name,
            "desc": "热点视频：围绕「%s」的创意内容，互动量和讨论度高，适合参考其表现形式。" % title,
            "link": douyin_search(title),
            "scheme": "snssdk1128://search/" + title,
        })
    return items


def build_finance(live):
    items = []
    for i, it in enumerate(live[:30], 1):
        it = it if isinstance(it, dict) else {"title": str(it)}
        title = pick_text(it, "title", "word", "name", "topic", "content", "summary")
        if not title:
            continue
        items.append({
            "id": short_id("ff", title),
            "source": pick_text(it, "source", "src", "from") or "东方财富",
            "tag": pick_text(it, "tag", "category") or "财经热点",
            "time": "今日",
            "title": title,
            "insight": pick_text(it, "insight", "desc")
                       or "市场波动中保持理性——不追涨杀跌，关注长期价值。",
            "link": "https://so.eastmoney.com/news/s?keyword=" + urllib.parse.quote(title),
        })
    return items


def load_inline_fallback():
    for p in HTML_PATHS:
        if not os.path.exists(p):
            continue
        html = open(p, encoding="utf-8").read()
        m = re.search(r'window\.ANXU_DATA\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    return {"ideas": {}, "hot": {}, "finance": {}}


def main():
    date_s, weekday = now_date_weekday()
    ts = now_str()
    fb = load_inline_fallback()

    print("== 陈安叙工作台 数据刷新 ==  时间：", ts)

    # 1) 抖音灵感
    try:
        ideas_raw = try_sources_json(DOUYIN_SOURCES)
        ideas_items = build_ideas(dig_list(ideas_raw))
        print(f"  [实时] ideas：成功获取 {len(ideas_items)} 条")
    except Exception:
        ideas_items = json.loads(json.dumps(fb.get("ideas", {}).get("ideas") or [], ensure_ascii=False))
        print(f"  [回退] ideas：接口不可用，保留原有 {len(ideas_items)} 条")

    # 2) 热点二创
    hot_items = []
    for url, name in HOT_SOURCES:
        try:
            hot_items = build_hot(dig_list(fetch_json(url)), name)
            if hot_items:
                print(f"  [实时] hot：成功获取 {len(hot_items)} 条（{name}）")
                break
        except Exception:
            continue
    if not hot_items:
        hot_items = json.loads(json.dumps(fb.get("hot", {}).get("items") or [], ensure_ascii=False))
        print(f"  [回退] hot：接口不可用，保留原有 {len(hot_items)} 条")

    # 3) 财经资讯
    try:
        fin_raw = try_sources_json(FINANCE_SOURCES)
        fin_items = build_finance(dig_list(fin_raw))
        print(f"  [实时] finance：成功获取 {len(fin_items)} 条")
    except Exception:
        fin_items = json.loads(json.dumps(fb.get("finance", {}).get("news") or [], ensure_ascii=False))
        print(f"  [回退] finance：接口不可用，保留原有 {len(fin_items)} 条")

    new_data = {
        "ideas": {
            "updateTime": ts, "date": date_s, "weekday": weekday,
            "activeTime": ts, "total": len(ideas_items), "ideas": ideas_items,
        },
        "hot": {
            "updateTime": ts, "date": date_s, "activeTime": ts,
            "categories": ["全部", "热门话题"], "total": len(hot_items),
            "items": hot_items,
        },
        "finance": {
            "updateTime": ts, "date": date_s, "weekday": weekday,
            "news": fin_items,
        },
    }

    new_inline = "window.ANXU_DATA = " + json.dumps(new_data, ensure_ascii=False) + ";"
    written = 0
    for p in HTML_PATHS:
        if not os.path.exists(p):
            continue
        html = open(p, encoding="utf-8").read()
        if "window.ANXU_DATA" not in html:
            continue
        new_html = re.sub(r'window\.ANXU_DATA\s*=\s*[^\n]*', new_inline, html, count=1)
        open(p, "w", encoding="utf-8").write(new_html)
        written += 1
    print(f"已重写 {written} 个 HTML 文件的内联数据")

    os.makedirs(OUT_DIR, exist_ok=True)
    if ideas_items:
        json.dump({"ideas": ideas_items, "updateTime": ts},
                  open(os.path.join(OUT_DIR, "ideas_data.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    if hot_items:
        json.dump({"items": hot_items, "categories": ["全部", "热门话题"], "updateTime": ts},
                  open(os.path.join(OUT_DIR, "hot_data.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    if fin_items:
        json.dump({"news": fin_items, "updateTime": ts},
                  open(os.path.join(OUT_DIR, "finance_data.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    print("完成。")


if __name__ == "__main__":
    main()
