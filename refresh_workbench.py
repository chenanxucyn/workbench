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

# 选题灵感：全网热榜聚合（抖音/微博/百度/知乎/B站实时热点），再按赛道自动分类打标签
# uapis.cn 实测 5 个平台均可用、免费免 Key、返回真实热榜（标题/热度/视频数/播放量）
IDEAS_SOURCES = [
    "https://uapis.cn/api/v1/misc/hotboard?type=douyin",
    "https://uapis.cn/api/v1/misc/hotboard?type=weibo",
    "https://uapis.cn/api/v1/misc/hotboard?type=baidu",
    "https://uapis.cn/api/v1/misc/hotboard?type=zhihu",
    "https://uapis.cn/api/v1/misc/hotboard?type=bilibili",
]

# 选题灵感 赛道分类：根据标题关键词自动归类（搞笑 / 情感共鸣 / 搞钱吐槽 / 母婴萌娃 / 热门爆款）
CATEGORY_RULES = [
    ("母婴萌娃", ["萌娃", "宝宝", "母婴", "育儿", "亲子", "小孩", "儿子", "女儿", "娃", "宝妈", "奶爸",
                  "幼儿园", "早教", "怀孕", "二胎", "儿童", "小学生", "孩子", "妈妈", "爸爸", "婴儿",
                  "带娃", "奶粉", "辅食", "尿不湿", "婆婆", "儿媳", "新生儿", "家长会"]),
    ("搞钱/吐槽", ["赚钱", "副业", "搞钱", "吐槽", "口播", "职场", "工资", "老板", "打工人", "摸鱼", "理财",
                  "暴富", "存款", "裁员", "失业", "创业", "房贷", "公积金", "社保", "穷", "同事", "上班",
                  "借款", "还债", "韭菜", "消费", "省钱", "攒钱", "退休", "养老金", "穷人", "负债", "工资条"]),
    ("情感共鸣", ["情感", "泪目", "感人", "暖心", "泪奔", "共鸣", "爱情", "结婚", "分手", "亲情", "友情",
                  "治愈", "遗憾", "青春", "回忆", "异地", "暗恋", "前任", "婚姻", "妻子", "老公", "家庭",
                  "父母", "家人", "初恋", "告白", "催泪", "心酸", "扎心", "委屈", "孤独", "想念", "重逢",
                  "婆婆", "儿媳", "暗恋", "婚礼", "求婚", "分手", "出轨", "背叛", "陪伴"]),
    ("搞笑", ["搞笑", "笑话", "沙雕", "整活", "搞怪", "喜剧", "表情包", "段子", "幽默", "翻车", "名场面",
              "整蛊", "笑死", "神操作", "社死", "逗", "搞笑", "名场面", "翻车", "整活", "搞怪", "囧",
              "离谱", "迷惑", "尴尬", "名场面", "翻车", "整活"]),
]

INSIGHT_BY_CAT = {
    "母婴萌娃": "萌娃/亲子天然高互动，主打真实带娃日常与情绪共鸣，容易出爆款。",
    "搞钱/吐槽": "职场/搞钱/吐槽类口播完播率高，借热点宣泄情绪+给方法，涨粉快。",
    "情感共鸣": "情感类靠共鸣转发，文案戳中一类人的心事，评论区自然热。",
    "搞笑": "搞笑整活最易破圈，节奏快门槛低，适合二创或 Reaction。",
    "热门爆款": "热点事件，从你的视角解读能快速涨粉。",
}

def classify_category(text):
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in text:
                return cat
    return "热门爆款"
HOT_SOURCES = [
    ("https://uapis.cn/api/v1/misc/hotboard?type=douyin", "抖音热搜榜"),
    ("https://api.vvhan.com/api/hotlist/douyin", "抖音热搜榜"),
    ("https://api.oioweb.cn/api/common/DouYinHot", "抖音热搜榜"),
    ("https://tenapi.cn/v2/douyinhot", "抖音热搜榜"),
]
FINANCE_SOURCES = [
    "https://api.vvhan.com/api/hotlist/finance",
    "https://tenapi.cn/v2/caijing",
    "https://api.oioweb.cn/api/common/EastMoney",
    "https://newsapi.eastmoney.com/kuaixun/v1/get?type=1&page_size=20&page_index=1",
]

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# 统一使用北京时间（UTC+8），避免云端 Runner（UTC）与本地（北京时间）不一致
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))


def now_str():
    return datetime.datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")


def now_date_weekday():
    d = datetime.datetime.now(BEIJING_TZ)
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
        cat = classify_category(topic)
        items.append({
            "rank": i,
            "topic": topic,
            "heat": pick_int(it, "hot", "heat", "num", "hotScore", "hot_value"),
            "videos": pick_int(it, "videos", "video_count"),
            "type": cat,
            "insight": INSIGHT_BY_CAT.get(cat, "热点事件，从你的视角解读能快速涨粉"),
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
        hv = pick_int(it, "hot", "heat", "num", "hotScore", "heatValue", "hot_value")
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

    # 1) 选题灵感（全网聚合：抖音/微博/百度/知乎/B站，按赛道分类）
    try:
        merged = []
        seen = set()
        for u in IDEAS_SOURCES:
            try:
                raw = fetch_json(u)
            except Exception:
                continue
            for it in dig_list(raw):
                it = it if isinstance(it, dict) else {"title": str(it)}
                t = pick_text(it, "title", "word", "name", "topic", "query")
                if not t or t in seen:
                    continue
                seen.add(t)
                merged.append(it)
        if not merged:
            raise RuntimeError("所有选题源均不可用")
        ideas_items = build_ideas(merged)
        print(f"  [实时] ideas：全网聚合成功 {len(ideas_items)} 条（已按赛道分类）")
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
