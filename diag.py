import sys, requests

url = sys.argv[1].split("#")[0]
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
r = requests.get(url, headers=headers, timeout=30)
print("status:", r.status_code)
for k in ("server", "cf-mitigated", "cf-ray", "content-type"):
    print(f"{k}: {r.headers.get(k)}")
print("--- first 400 chars of body ---")
print(r.text[:400])