import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("DATA_GOV_KEY", "").strip()
BASE = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
KEEP_DAYS = 30
DATE_FMT = "%d/%m/%Y"


def get_json(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; KrishiMitraBot/1.0)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", attempt + 1, repr(e))
            time.sleep(5)
    return None

def num(v):
    try:
        return int(float(v))
    except Exception:
        return 0


def fetch_all():
    records = []
    offset = 0
    for _ in range(40):
        url = (BASE + "?api-key=" + KEY + "&format=json&limit=500&offset=" + str(offset)
               + "&filters[state.keyword]=Maharashtra")
        data = get_json(url)
        if not data:
            break
        recs = data.get("records") or []
        records.extend(recs)
        total = int(data.get("total", 0) or 0)
        offset += len(recs)
        if not recs or offset >= total:
            break
    return records


def main():
    if not KEY:
        raise SystemExit("DATA_GOV_KEY secret is missing")
    os.makedirs("data", exist_ok=True)

    records = fetch_all()
    print("records fetched:", len(records))
    if not records:
        return

    # district -> market -> crop -> date -> prices
    groups = {}
    for r in records:
        district = (r.get("district") or "").strip()
        market = (r.get("market") or "").strip()
        crop = (r.get("commodity") or "").strip()
        date = (r.get("arrival_date") or "").strip()
        if not (district and market and crop and date):
            continue
        mn = num(r.get("min_price"))
        mx = num(r.get("max_price"))
        md = num(r.get("modal_price"))
        if md <= 0:
            continue
        g = (groups.setdefault(district, {}).setdefault(market, {})
             .setdefault(crop, {}).setdefault(date, {"mn": [], "mx": [], "md": []}))
        if mn > 0:
            g["mn"].append(mn)
        if mx > 0:
            g["mx"].append(mx)
        g["md"].append(md)

    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    cutoff = today - timedelta(days=KEEP_DAYS)

    for district, markets in groups.items():
        fname = "data/" + re.sub(r"[^A-Za-z0-9]+", "_", district) + ".json"
        old = {}
        if os.path.exists(fname):
            try:
                with open(fname, encoding="utf-8") as f:
                    old = json.load(f).get("mandis", {})
            except Exception:
                old = {}

        # add / update (old days are never deleted by a later run)
        for market, crops in markets.items():
            for crop, dates in crops.items():
                for date, g in dates.items():
                    modal = round(sum(g["md"]) / len(g["md"]))
                    mn = min(g["mn"]) if g["mn"] else modal
                    mx = max(g["mx"]) if g["mx"] else modal
                    old.setdefault(market, {}).setdefault(crop, {})[date] = [mn, mx, modal]

        # remove days older than KEEP_DAYS
        for market in list(old.keys()):
            for crop in list(old[market].keys()):
                for date in list(old[market][crop].keys()):
                    try:
                        if datetime.strptime(date, DATE_FMT) < cutoff:
                            del old[market][crop][date]
                    except Exception:
                        del old[market][crop][date]
                if not old[market][crop]:
                    del old[market][crop]
            if not old[market]:
                del old[market]

        out = {
            "district": district,
            "updated": today.strftime("%d/%m/%Y %H:%M") + " IST",
            "mandis": old,
        }
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        print("saved", fname)


if __name__ == "__main__":
    main()
