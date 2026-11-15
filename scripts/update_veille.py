#!/usr/bin/env python3
"""Récupère les flux RSS/Atom, filtre par mots-clés et écrit veille.json.
Aucune dépendance externe (bibliothèque standard uniquement)."""
import json, re, sys, html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "veille.json"
MAX_ITEMS, MAX_AGE_DAYS, SUMMARY_LEN = 150, 180, 220

# filtre=True : on ne garde que les articles contenant un mot-clé de THEMES
# filtre=False : on garde tout (sources déjà ciblées)
SOURCES = [
    {"name": "CERT-FR · Alertes",   "type": "Source officielle", "url": "https://www.cert.ssi.gouv.fr/alerte/feed/",    "filtre": False, "categorie": "Alertes CERT-FR"},
    {"name": "CERT-FR · Actualités","type": "Source officielle", "url": "https://www.cert.ssi.gouv.fr/actualite/feed/", "filtre": False, "categorie": "Alertes CERT-FR"},
    {"name": "ZATAZ",               "type": "Presse spécialisée","url": "https://www.zataz.com/feed/",                  "filtre": True},
    {"name": "Silicon.fr",          "type": "Presse spécialisée","url": "https://www.silicon.fr/feed",                  "filtre": True},
    {"name": "LeMagIT",             "type": "Presse spécialisée","url": "https://www.lemagit.fr/rss/ContentSyndication.xml", "filtre": True},
    {"name": "The Hacker News",     "type": "Presse internationale","url": "https://feeds.feedburner.com/TheHackersNews","filtre": True},
]

THEMES = {  # ordre = priorité
    "Sauvegardes":    ["sauvegarde", "backup", "restauration", "immuable", "immutable", "veeam", "acronis", "commvault", "synology", "3-2-1", "disaster recovery", "plan de reprise", "pra "],
    "Ransomwares":    ["ransomware", "rançongiciel", "rancongiciel", "raas", "lockbit", "qilin", "akira", "ransomhub", "double extorsion", "extorsion", "play ransomware"],
    "Réglementation": ["nis2", "nis 2", "rgpd", "loi résilience", "loi resilience", "cnil", "anssi", "conformité", "directive"],
}

def clean(txt):
    txt = re.sub(r"<[^>]+>", " ", txt or "")
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()

def local(tag):
    return tag.rsplit("}", 1)[-1]

def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None

def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        t = child(el, "title")
        title = clean(t.text) if t is not None else ""
        link = ""
        for c in el:
            if local(c.tag) == "link":
                link = (c.get("href") or c.text or "").strip()
                if c.get("rel") in (None, "alternate"):
                    break
        d = child(el, "description") or child(el, "summary") or child(el, "encoded") or child(el, "content")
        summary = clean(d.text if d is not None else "")
        when = None
        for n in ("pubDate", "published", "updated", "date"):
            c = child(el, n)
            if c is not None and c.text:
                when = parse_date(c.text)
                if when:
                    break
        if title and link:
            items.append({"title": title, "link": link, "summary": summary, "date": when})
    return items

def classify(text):
    low = " " + text.lower() + " "
    for theme, words in THEMES.items():
        if any(w in low for w in words):
            return theme
    return None

def short(s):
    return s if len(s) <= SUMMARY_LEN else s[:SUMMARY_LEN].rsplit(" ", 1)[0] + "…"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (veille-bot; +https://imad-belhoucine.netlify.app)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

def main():
    now = datetime.now(timezone.utc)
    limit = now - timedelta(days=MAX_AGE_DAYS)
    found, ok_sources = {}, []
    for s in SOURCES:
        try:
            entries = parse_feed(fetch(s["url"]))
        except Exception as e:
            print(f"[ignoré] {s['name']} : {e}", file=sys.stderr)
            continue
        ok_sources.append({"name": s["name"], "type": s["type"]})
        kept = 0
        for e in entries:
            when = e["date"] or now
            if when < limit:
                continue
            theme = classify(e["title"] + " " + e["summary"])
            if s["filtre"] and not theme:
                continue
            category = theme or s.get("categorie", "Autres")
            found[e["link"]] = {"title": e["title"], "link": e["link"], "summary": short(e["summary"]),
                                "date": when.isoformat(), "source": s["name"], "category": category}
            kept += 1
        print(f"[ok] {s['name']} : {kept} article(s)")
    items = sorted(found.values(), key=lambda a: a["date"], reverse=True)[:MAX_ITEMS]
    if not items and OUT.exists():
        print("Aucun article récupéré : veille.json conservé.", file=sys.stderr)
        return
    OUT.write_text(json.dumps({"updated": now.isoformat(), "sources": ok_sources, "items": items},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} article(s) écrits dans {OUT.name}")

if __name__ == "__main__":
    main()
