import os
os.system("playwright install chromium")

import time
import pandas as pd
import streamlit as st
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="AURA Lead Studio", page_icon="⚡", layout="wide")

st.title("⚡ AURA LEAD INTELLIGENCE STUDIO")
st.caption("Universal Maps Scraper & Lead Verification Engine")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    category = st.text_input("Target Industry / Category", value="Software Company")
with col2:
    city = st.text_input("Target Location / City / Country", value="Pakistan")
with col3:
    limit = st.number_input("Quantity", min_value=1, max_value=100, value=20)

def verify_lead(lead: dict) -> str:
    score = 0
    if lead["Phone"] != "N/A" and len(lead["Phone"].replace(" ", "")) >= 7:
        score += 1
    if lead["Address"] != "N/A" and any(c.isdigit() for c in lead["Address"]):
        score += 1
    if lead["Website"] != "N/A" and lead["Website"].startswith("http"):
        score += 1
    
    if score >= 3:
        return "Official"
    elif score == 2:
        return "Unverified"
    else:
        return "Likely Fake / Incomplete"

def scrape_google_maps(category: str, city: str, max_results: int):
    query = f"{category} in {city}"
    leads = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        page.goto(search_url, timeout=60000)
        time.sleep(3)

        feed_selector = 'div[role="feed"]'
        try:
            page.wait_for_selector(feed_selector, timeout=10000)
        except Exception:
            browser.close()
            return []

        scroll_attempts = max(2, max_results // 5)
        for _ in range(scroll_attempts):
            page.hover(feed_selector)
            page.mouse.wheel(0, 3000)
            time.sleep(2)

        cards = page.query_selector_all('div[role="article"]')
        for idx, card in enumerate(cards[:max_results]):
            try:
                name = card.get_attribute("aria-label")
                if not name:
                    title_el = card.query_selector('div.qBF1Pd') or card.query_selector('span.OSrL2e')
                    name = title_el.inner_text().strip() if title_el else "N/A"

                card.click()
                time.sleep(2)

                address_el = page.query_selector('button[data-item-id*="address"]')
                address = address_el.inner_text().replace("\n", ", ").strip() if address_el else f"{city} Region"

                phone_el = page.query_selector('button[data-item-id*="phone"]')
                phone = phone_el.inner_text().replace("\n", " ").strip() if phone_el else "N/A"

                website_el = page.query_selector('a[data-item-id="authority"]')
                website = website_el.get_attribute("href") if website_el else "N/A"

                rating_el = page.query_selector('div.F7L3fd span[aria-hidden="true"]')
                rating = rating_el.inner_text().strip() if rating_el else "N/A"

                lead = {
                    "Business Name": name,
                    "Phone": phone,
                    "Rating": rating,
                    "Website": website,
                    "Address": address,
                }
                lead["Verification Status"] = verify_lead(lead)
                leads.append(lead)

            except Exception:
                continue

        browser.close()
    return leads

if st.button("EXTRACT GOOGLE MAPS LEADS", type="primary"):
    if not category or not city:
        st.error("Please provide both Industry and Location.")
    else:
        with st.spinner("Extracting and verifying leads from Google Maps..."):
            leads_data = scrape_google_maps(category, city, int(limit))

        if leads_data:
            df = pd.DataFrame(leads_data)
            st.success(f"Successfully extracted {len(df)} leads!")

            st.dataframe(df, use_container_width=True)

            excel_filename = f"{category}_{city}_leads.xlsx".replace(" ", "_").lower()
            df.to_excel("temp_leads.xlsx", index=False, engine="openpyxl")
            
            with open("temp_leads.xlsx", "rb") as f:
                st.download_button(
                    label="📥 DOWNLOAD EXCEL (.XLSX)",
                    data=f,
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No listings found. Try adjusting your search query.")
