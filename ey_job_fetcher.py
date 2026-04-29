import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

BASE_URL = "https://careers.ey.com/search/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Referer": "https://careers.ey.com/",
}

def fetch_ey_india_jobs():
    all_jobs = []
    start_row = 0
    records_per_page = 25
    page = 1

    print("🔍 EY India Jobs Fetching...")
    print("─" * 50)

    while True:
        params = {
            "createNewAlert": "false",
            "q": "",                          # ✅ BLANK — no double filter
            "optionsFacetsDD_customfield1": "",
            "optionsFacetsDD_country": "India",  # ✅ Only country filter
            "startrow": start_row,
        }

        try:
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ Error on page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Check for no results message
        no_results = soup.find("div", id="noresults")
        if no_results and page == 1:
            msg = no_results.get_text(strip=True)
            print(f"⚠️  Page says: {msg[:100]}")

        # Job rows are <tr class="data-row">
        job_rows = soup.find_all("tr", class_="data-row")

        if not job_rows:
            print(f"\n✅ No more jobs. Total collected: {len(all_jobs)}")
            if page == 1:
                with open("ey_page_debug.html", "w", encoding="utf-8") as f:
                    f.write(resp.text)
                print("💾 Saved ey_page_debug.html for inspection")
            break

        for row in job_rows:
            job = {}

            # Title + URL
            title_tag = row.find("a", class_="jobTitle-link")
            if title_tag:
                job["title"] = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                job["url"] = ("https://careers.ey.com" + href) if href.startswith("/") else href

            # Location
            loc_tag = row.find("span", class_="jobLocation") or row.find("td", class_="colLocation")
            if loc_tag:
                job["location"] = loc_tag.get_text(strip=True)

            # All <td> cells for extra info
            tds = row.find_all("td")
            if len(tds) >= 2 and "location" not in job:
                job["location"] = tds[1].get_text(strip=True)

            if job:
                all_jobs.append(job)

        print(f"  Page {page}: +{len(job_rows)} jobs | Total: {len(all_jobs)}")

        # Next page check
        next_btn = (
            soup.find("a", string=lambda t: t and "next" in t.lower()) or
            soup.find("a", attrs={"aria-label": lambda x: x and "next" in x.lower()}) or
            soup.find("a", class_=lambda c: c and "next" in c.lower())
        )

        if not next_btn:
            print(f"\n✅ Last page reached.")
            break

        start_row += records_per_page
        page += 1
        time.sleep(1)

    return all_jobs


def save_to_csv(jobs, filename="ey_india_jobs.csv"):
    if not jobs:
        print("\n⚠️  No jobs to save.")
        return None
    df = pd.DataFrame(jobs)
    df.drop_duplicates(inplace=True)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\n💾 Saved {len(df)} jobs → {filename}")
    print(f"📋 Columns: {list(df.columns)}")
    return df


if __name__ == "__main__":
    jobs = fetch_ey_india_jobs()
    df = save_to_csv(jobs, "ey_india_jobs.csv")

    if df is not None and not df.empty:
        print("\n🔎 Sample (first 5):")
        print(df.head().to_string())