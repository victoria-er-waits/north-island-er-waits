#!/usr/bin/env python3
"""Rebuild index.html for the North Island ER waits page.
Live source: https://www.islandhealth.ca/find-care (posted wait + "Open today" hours per site)
and https://www.islandhealth.ca/health-alerts (official alerts; blank when none).
Static: sites.json (phones, hours, coordinates, OSRM drive from Port Hardy Hospital), alerts.json (Island Health X posts).
Never invents a wait: if a site is not listed or unreadable, shows "No live wait data".
Prints CHANGED=true|false. Exit 1 if the source could not be read (page left unchanged)."""
import datetime as dt, html, json, os, re, sys, urllib.request
from zoneinfo import ZoneInfo
PT=ZoneInfo("America/Vancouver"); ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def fetch(u):
    for _ in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA,"Cache-Control":"no-cache"}),timeout=30).read().decode("utf-8","replace")
        except Exception as e: err=e
    raise RuntimeError(err)
def txt(f): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",f)).replace("\xa0"," ")).strip()
def parse(page):
    out={}
    for c in page.split('class="emergency-departments')[1:]:
        n=re.search(r'class="token-name">\s*(?:<a[^>]*>)?([^<]+)',c); w=re.search(r'class="inner">\s*(.*?)\s*</div>',c,re.S)
        h=re.search(r'(Open today from[^<]+|Closed today[^<]*)',c)
        if n: out[txt(n.group(1))]=dict(wait=txt(w.group(1)) if w else "",hours=txt(h.group(1)) if h else "")
    return out
def alerts_page(p):
    p=re.sub(r"<(script|style|nav|header|footer).*?</\1>","",p,flags=re.S)
    m=re.search(r"This page is blank when there are no active alerts\.(.*?)Back to Top",txt(p.replace(">","> ")),re.S)
    return (m.group(1).strip() if m else None)
def stamp(n): return f"{n.hour%12 or 12}:{n.minute:02d} {'a.m.' if n.hour<12 else 'p.m.'} PT, {n:%B} {n.day}, {n.year}"
def fm(m): h,mm=divmod(m,60); return (f"{h} h {mm} min" if h and mm else f"{h} h" if h else f"{mm} min")
E=lambda s: html.escape(s or "")
def card(s,live,read):
    d=live.get(s["ih"]) if s["ih"] else None
    if d is None:
        wait='<p class="wait nodata">No live wait data</p>'; src="Not on Island Health's live wait list."
    else:
        w=d["wait"]; up=w.strip().upper()
        if re.search(r"\d+ (hour|minute)",w): wait=f'<p class="wait">{E(w)}</p>'
        elif "CLOSED" in up: wait='<p class="wait closed">Closed</p>'
        elif up=="OPEN": wait='<p class="wait">Open <span class="sub">(no wait posted)</span></p>'
        else: wait=f'<p class="wait nodata">{E(w) or "No live wait data"}</p>'
        src=f"Island Health, read {read}."
    hrs=f'<p class="hours"><b>Island Health today:</b> {E(d["hours"])}</p>' if d and d["hours"] else ""
    drive=f'<p class="drive">From Port Hardy Hospital: {s["km"]} km, about {fm(s["min"])}{" (approx. town location)" if s.get("approx") else ""}.</p>' if "km" in s else ""
    ph=f'<p class="hours">Call <a href="tel:{re.sub(r"[^0-9]","",s["phone"].split(" ext")[0])}">{E(s["phone"])}</a></p>' if s["phone"] else ""
    return f'''  <article id="{s["id"]}">
    <h2>{E(s["name"])}</h2>
    <p class="city">{E(s["city"])}</p>
    {wait}
    {hrs}
    <p class="drive" id="{s["id"]}-drive"></p>
    {drive}
    <p class="hours">{E(s["note"])}</p>
    {ph}
    <p class="read">{src} <a href="{s["url"]}">Site info</a></p>
  </article>'''
def main():
    sites=json.load(open(f"{ROOT}/sites.json")); al=json.load(open(f"{ROOT}/alerts.json"))
    try: page=fetch("https://www.islandhealth.ca/find-care")
    except Exception as e: print("ERROR",e,file=sys.stderr); return 1
    live=parse(page)
    if not any(s["ih"] in live for s in sites if s["ih"]): print("ERROR: no site parsed",file=sys.stderr); return 1
    try: ap=alerts_page(fetch("https://www.islandhealth.ca/health-alerts"))
    except Exception: ap=None
    now=dt.datetime.now(PT); read=stamp(now)
    ab="".join(f'<li><b>{E(a["pt"])}</b>: {E(a["text"])} <a href="{a["url"]}">Island Health on X</a></li>' for a in al)
    apl=("Island Health alerts page: no active alerts posted." if ap=="" else f"Island Health alerts page: {E(ap[:600])}" if ap else "Island Health alerts page could not be read.")
    groups=[("er","Emergency departments"),("uc","Urgent care centres (Island Health live list)"),("upcc","Same-day / urgent and primary care (appointment)")]
    body="\n".join(f'  <h2 class="section">{t}</h2>\n'+"\n".join(card(s,live,read) for s in sites if s["kind"]==k) for k,t in groups)
    tpl=open(f"{ROOT}/template.html",encoding="utf-8").read()
    pts=json.dumps({s["id"]:{"lat":s["lat"],"lon":s["lon"]} for s in sites})
    new=tpl.replace("{{UPDATED}}",read).replace("{{ALERTS}}",ab).replace("{{ALERTPAGE}}",apl).replace("{{BODY}}",body).replace("{{PTS}}",pts)
    old=open(f"{ROOT}/index.html",encoding="utf-8").read() if os.path.exists(f"{ROOT}/index.html") else ""
    strip=lambda s: re.sub(r"\d{1,2}:\d{2} [ap]\.m\. PT, \w+ \d+, \d{4}","",s)
    if strip(old)==strip(new) and old:
        m=re.search(r'id="updated">Last updated ([^<]+)<',old)
        try: age=(now-dt.datetime.strptime(m.group(1).replace("a.m.","AM").replace("p.m.","PM").replace(" PT",""),"%I:%M %p, %B %d, %Y").replace(tzinfo=PT)).total_seconds()
        except Exception: age=1e9
        if age<1800: print("CHANGED=false"); return 0
    open(f"{ROOT}/index.html","w",encoding="utf-8").write(new)
    for s in sites: print(s["id"],live.get(s["ih"]) if s["ih"] else "(not listed)",file=sys.stderr)
    print("CHANGED=true"); print(f"COMMIT_MSG=Refresh North Island ER waits ({read})"); return 0
if __name__=="__main__": sys.exit(main())
