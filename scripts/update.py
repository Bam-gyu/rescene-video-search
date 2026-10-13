"""매일 리센느 관련 유튜브 영상을 검색해서 data/videos.json 을 갱신한다.

실행: YOUTUBE_API_KEY=... python scripts/update.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state.json"
OUTPUT_PATH = ROOT / "data" / "videos.json"
BLOCKLIST_PATH = ROOT / "blocklist.txt"

QUERIES = ["#리센느", "리센느", "RESCENE"]
LONG_MIN_VIEWS = 50_000
SHORT_MIN_VIEWS = 100_000
SEARCH_SINCE = "2024-01-01T00:00:00Z"  # 리센느 공식 채널 개설 시점
RECENT_DAYS = 7  # 최신순 검색 범위
RECHECK_DAYS = 60  # 기준 미달 영상을 다시 확인하는 기간
FAN_SAMPLE = 20  # 팬 채널 판정에 쓰는 최근 업로드 수
FAN_RATIO = 0.5  # 이 비율을 넘게 리센느 영상이면 팬 채널
FAN_MAX_SUBSCRIBERS = 100_000  # 이 이상이면 방송사 등으로 보고 팬 채널 판정에서 제외
CHANNEL_RECHECK_DAYS = 30
SHORT_MAX_SECONDS = 180  # 이보다 길면 쇼츠가 될 수 없음

OFFICIAL_CHANNELS = {
    "UCtKtCiaWRz-d3EZn2xd1mdA",  # RESCENE (@rescene_official)
    "UChYBqDyMT6Oak2dPIujxHwg",  # THE MUZE Entertainment (@themuze_ent)
}

KEYWORD = re.compile(r"리센느|rescene", re.IGNORECASE)


# ---------- 순수 함수 (tests/test_update.py 에서 검증) ----------

def parse_duration(iso):
    """'PT1H2M3S' -> 3723"""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def mentions_rescene(*texts):
    return any(KEYWORD.search(t or "") for t in texts)


def is_fan_channel(channel_id, upload_texts, subscribers=0):
    """최근 업로드 대부분이 리센느 영상인 비공식 소규모 채널이면 팬 채널로 본다."""
    if channel_id in OFFICIAL_CHANNELS or not upload_texts or subscribers >= FAN_MAX_SUBSCRIBERS:
        return False
    hits = sum(1 for t in upload_texts if mentions_rescene(t))
    return hits / len(upload_texts) > FAN_RATIO


def parse_blocklist(text):
    ids = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(line)
    return ids


def is_short_video(duration_seconds, embed_width, embed_height):
    """3분 이하 세로(또는 정사각형) 영상이면 쇼츠."""
    return duration_seconds <= SHORT_MAX_SECONDS and embed_height >= embed_width > 0


def passes_threshold(video):
    return video["views"] >= (SHORT_MIN_VIEWS if video["isShort"] else LONG_MIN_VIEWS)


def parse_time(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def is_recent(video, now):
    return now - parse_time(video["publishedAt"]) <= timedelta(days=RECHECK_DAYS)


def prune(videos, now):
    """기준을 넘었거나 아직 재확인 기간 안인 영상만 남긴다."""
    return {vid: v for vid, v in videos.items() if passes_threshold(v) or is_recent(v, now)}


def build_output(videos, channels, blocklist, now):
    long_list, shorts = [], []
    for vid, v in videos.items():
        if v["channelId"] in blocklist or not passes_threshold(v):
            continue
        item = {"id": vid, **{k: v[k] for k in ("title", "channelId", "channelTitle", "publishedAt", "views", "thumbnail")},
                "listedAt": v.get("listedAt")}
        if v["isShort"]:
            shorts.append(item)
        elif not channels.get(v["channelId"], {}).get("fan"):
            long_list.append(item)
    newest_first = lambda x: x["publishedAt"]
    return {
        "updatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "long": sorted(long_list, key=newest_first, reverse=True),
        "shorts": sorted(shorts, key=newest_first, reverse=True),
    }


# ---------- 네트워크 ----------

def api(endpoint, **params):
    params["key"] = os.environ["YOUTUBE_API_KEY"]
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def search(query, order, published_after, pages):
    ids, token = set(), None
    for _ in range(pages):
        params = dict(part="id", type="video", q=query, order=order, maxResults=50, publishedAfter=published_after)
        if token:
            params["pageToken"] = token
        res = api("search", **params)
        ids.update(item["id"]["videoId"] for item in res.get("items", []))
        token = res.get("nextPageToken")
        if not token:
            break
    return ids


def fetch_videos(ids):
    ids = list(ids)
    for i in range(0, len(ids), 50):
        # maxWidth 를 주면 player.embedWidth/Height 가 원본 화면비대로 온다 (쇼츠 판별용)
        res = api("videos", part="snippet,statistics,contentDetails,player", id=",".join(ids[i:i + 50]),
                  maxResults=50, maxWidth=480)
        yield from res.get("items", [])


def subscriber_counts(channel_ids):
    ids, counts = list(channel_ids), {}
    for i in range(0, len(ids), 50):
        for c in api("channels", part="statistics", id=",".join(ids[i:i + 50]), maxResults=50).get("items", []):
            counts[c["id"]] = int(c["statistics"].get("subscriberCount", 0))
    return counts


def recent_upload_texts(channel_id):
    playlist = "UU" + channel_id[2:]  # 채널의 업로드 재생목록 ID 규칙
    try:
        res = api("playlistItems", part="snippet", playlistId=playlist, maxResults=FAN_SAMPLE)
    except urllib.error.HTTPError:
        return []
    return [f'{i["snippet"]["title"]} {i["snippet"].get("description", "")}' for i in res.get("items", [])]


# ---------- 메인 ----------

def write_output(videos, channels, blocklist, now):
    output = build_output(videos, channels, blocklist, now)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=1))
    print(f"롱폼 {len(output['long'])}개, 쇼츠 {len(output['shorts'])}개 (추적 중 {len(videos)}개)")


def rebuild_only():
    """검색 없이 blocklist.txt 변경만 반영한다 (갱신 시각은 유지)."""
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"videos": {}, "channels": {}}
    blocklist = parse_blocklist(BLOCKLIST_PATH.read_text()) if BLOCKLIST_PATH.exists() else set()
    old = json.loads(OUTPUT_PATH.read_text())
    if not old.get("updatedAt"):
        return
    write_output(state["videos"], state["channels"], blocklist, parse_time(old["updatedAt"]))


def main(search_new=True):
    now = datetime.now(timezone.utc)
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"videos": {}, "channels": {}}
    videos, channels = state["videos"], state["channels"]
    blocklist = parse_blocklist(BLOCKLIST_PATH.read_text()) if BLOCKLIST_PATH.exists() else set()

    recent_after = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    view_pages = 2 if videos else 10  # 첫 실행은 과거 영상까지 넉넉히
    found = set()
    for q in (QUERIES if search_new else []):
        found |= search(q, "date", recent_after, pages=4)
        found |= search(q, "viewCount", SEARCH_SINCE, pages=view_pages)

    # 새로 찾은 영상 + 기존 영상의 조회수를 함께 갱신 (삭제·비공개된 영상은 결과에 없음)
    print(f"검색 결과 {len(found)}개, 기존 {len(videos)}개 조회수 확인", flush=True)
    items = [it for it in fetch_videos(found | set(videos))
             if mentions_rescene(it["snippet"]["title"], it["snippet"].get("description"),
                                 " ".join(it["snippet"].get("tags", [])))]

    refreshed = {}
    for item in items:
        sn = item["snippet"]
        vid = item["id"]
        old = videos.get(vid, {})
        player = item.get("player", {})
        is_short = is_short_video(parse_duration(item["contentDetails"].get("duration")),
                                  int(player.get("embedWidth", 0)), int(player.get("embedHeight", 0)))
        thumbs = sn.get("thumbnails", {})
        refreshed[vid] = {
            "title": sn["title"],
            "channelId": sn["channelId"],
            "channelTitle": sn["channelTitle"],
            "publishedAt": sn["publishedAt"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
            "isShort": is_short,
            "listedAt": old.get("listedAt"),
        }
    videos = prune(refreshed, now)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for v in videos.values():
        if passes_threshold(v) and not v["listedAt"]:
            v["listedAt"] = stamp  # 처음 목록에 오른 시각 (페이지의 NEW 표시용)

    # 롱폼 기준을 넘은 영상의 채널만 팬 채널 여부 확인
    to_check = {}
    for v in videos.values():
        if v["isShort"] or not passes_threshold(v):
            continue
        checked = channels.get(v["channelId"], {}).get("checkedAt")
        if not checked or now - parse_time(checked) >= timedelta(days=CHANNEL_RECHECK_DAYS):
            to_check[v["channelId"]] = v["channelTitle"]
    print(f"팬 채널 확인 {len(to_check)}개", flush=True)
    subscribers = subscriber_counts(to_check)
    for cid, title in to_check.items():
        channels[cid] = {"title": title, "fan": is_fan_channel(cid, recent_upload_texts(cid), subscribers.get(cid, 0)),
                         "checkedAt": stamp}

    STATE_PATH.write_text(json.dumps({"videos": videos, "channels": channels}, ensure_ascii=False, indent=1))
    write_output(videos, channels, blocklist, now)


if __name__ == "__main__":
    if "--rebuild-only" in sys.argv:
        rebuild_only()
    elif not os.environ.get("YOUTUBE_API_KEY"):
        sys.exit("YOUTUBE_API_KEY 환경변수가 필요합니다.")
    else:
        main(search_new="--no-search" not in sys.argv)
