import os
os.system("playwright install chromium")

import logging
import os
import threading
import time
import urllib.request
from typing import List, Dict, Any, Optional

import pandas as pd
import customtkinter as ctk
from tkinter import ttk, filedialog
from playwright.sync_api import sync_playwright

# Optional Google Sheets Integration
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class GoogleMapsScraperEngine:
    """Enterprise Direct Browser Automation for Google Maps Lead Intelligence."""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message: str) -> None:
        if self.status_callback:
            self.status_callback(message)
        logging.info(message)

    def _verify_lead_authenticity(self, lead: Dict[str, Any]) -> str:
        """Determines if a lead is Official or potentially Fake/Incomplete."""
        score = 0
        website = lead.get("Website", "N/A")
        phone = lead.get("Phone", "N/A")
        address = lead.get("Address", "N/A")

        if phone != "N/A" and len(phone.replace(" ", "")) >= 7:
            score += 1

        if address != "N/A" and any(char.isdigit() for char in address):
            score += 1

        if website != "N/A" and website.startswith("http"):
            score += 1

        if score >= 3:
            return "Official"
        elif score == 2:
            return "Unverified"
        else:
            return "Likely Fake / Incomplete"

    def search_leads(self, category: str, city: str, max_results: int = 20) -> List[Dict[str, Any]]:
        query = f"{category} in {city}"
        self._update_status(f"Initializing Chromium Engine for query: '{query}'...")

        leads = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            page.goto(search_url, timeout=60000)
            time.sleep(3)

            # Accept Google consent prompts if visible
            try:
                accept_btn = page.query_selector('button[aria-label*="Accept all"]') or page.query_selector('form button')
                if accept_btn:
                    accept_btn.click()
                    time.sleep(1)
            except Exception:
                pass

            feed_selector = 'div[role="feed"]'
            try:
                page.wait_for_selector(feed_selector, timeout=12000)
            except Exception:
                self._update_status("Error: Unable to locate result feed. Retry with different keywords.")
                browser.close()
                return []

            self._update_status("Scrolling feed to load maximum listings...")

            scroll_attempts = max(3, max_results // 4)
            for _ in range(scroll_attempts):
                page.hover(feed_selector)
                page.mouse.wheel(0, 3500)
                time.sleep(2)

            cards = page.query_selector_all('div[role="article"]')
            total_found = len(cards)
            self._update_status(f"Discovered {total_found} listings. Extracting detailed lead cards...")

            for idx, card in enumerate(cards[:max_results]):
                try:
                    name = card.get_attribute("aria-label")
                    if not name:
                        title_el = card.query_selector('div.qBF1Pd') or card.query_selector('span.OSrL2e') or card.query_selector('div.fontHeadlineSmall')
                        name = title_el.inner_text().strip() if title_el else "N/A"

                    card.click()
                    time.sleep(2.2)

                    address_el = page.query_selector('button[data-item-id*="address"]')
                    address = address_el.inner_text().replace("\n", ", ").strip() if address_el else f"{city} Region"

                    phone_el = page.query_selector('button[data-item-id*="phone"]')
                    phone = phone_el.inner_text().replace("\n", " ").strip() if phone_el else "N/A"

                    website_el = page.query_selector('a[data-item-id="authority"]')
                    website = website_el.get_attribute("href") if website_el else "N/A"

                    rating_el = page.query_selector('div.F7L3fd span[aria-hidden="true"]')
                    rating = rating_el.inner_text().strip() if rating_el else "N/A"

                    reviews_el = page.query_selector('button[data-tab-index="0"] span[aria-label*="reviews"]')
                    reviews = reviews_el.inner_text().replace("(", "").replace(")", "").strip() if reviews_el else "0"

                    maps_url = page.url

                    raw_lead = {
                        "Business Name": name,
                        "Category": category.title(),
                        "City/Location": city.title(),
                        "Phone": phone,
                        "Website": website,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Address": address,
                        "Google Maps Link": maps_url
                    }

                    # Authenticity Check
                    raw_lead["Verification Status"] = self._verify_lead_authenticity(raw_lead)

                    leads.append(raw_lead)
                    self._update_status(f"[{idx+1}/{min(total_found, max_results)}] Extracted: {name} ({raw_lead['Verification Status']})")

                except Exception as e:
                    logging.warning(f"Failed parsing listing index {idx}: {e}")
                    continue

            browser.close()

        return leads


class GoogleSheetsFormatter:
    """Applies executive formatting, headers, dark navy & gold styles to Google Sheets."""

    @staticmethod
    def export_and_format(df: pd.DataFrame, sheet_title: str, json_key_file: str = "service_account.json") -> Optional[str]:
        if not GSPREAD_AVAILABLE:
            logging.warning("gspread library not installed.")
            return None

        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_file, scope)
            client = gspread.authorize(creds)

            try:
                sheet = client.create(sheet_title)
            except Exception:
                sheet = client.open(sheet_title)

            worksheet = sheet.get_worksheet(0)
            worksheet.clear()

            worksheet.append_row(df.columns.tolist())
            worksheet.append_rows(df.values.tolist())

            sheet_id = worksheet.id

            header_format = {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.08, "green": 0.12, "blue": 0.25},
                            "textFormat": {
                                "foregroundColor": {"red": 1.0, "green": 0.84, "blue": 0.0},
                                "fontSize": 11,
                                "bold": True,
                                "fontFamily": "Proxima Nova"
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                }
            }

            sheet.batch_update({"requests": [header_format]})
            return sheet.url

        except Exception as e:
            logging.error(f"Google Sheets Sync failed: {e}")
            return None


class ProfessionalLeadStudioGUI(ctk.CTk):
    """Modern Desktop Interface with Verification Logic and Excel Downloader."""

    def __init__(self):
        super().__init__()

        self.title("AURA LEAD STUDIO v2.5 — Universal Lead Engine")
        self.geometry("1020x760")
        self.resizable(True, True)
        self.configure(fg_color="#090A0F")

        self.current_df = pd.DataFrame()
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="#12151E", corner_radius=12)
        header.pack(fill="x", padx=20, pady=(20, 10))

        title = ctk.CTkLabel(
            header,
            text="⚡ AURA LEAD INTELLIGENCE STUDIO",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#D4AF37"
        )
        title.pack(anchor="w", padx=20, pady=(14, 2))

        subtitle = ctk.CTkLabel(
            header,
            text="Universal Maps Scraper & Lead Verification Engine",
            font=ctk.CTkFont(size=11),
            text_color="#888E9E"
        )
        subtitle.pack(anchor="w", padx=20, pady=(0, 14))

        # Controls Container
        controls = ctk.CTkFrame(self, fg_color="#12151E", corner_radius=12)
        controls.pack(fill="x", padx=20, pady=5)

        # 1. Custom Editable Category Input
        ctk.CTkLabel(controls, text="TARGET INDUSTRY / CATEGORY", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A8B0C0").grid(row=0, column=0, sticky="w", padx=15, pady=(12, 2))
        
        self.category_entry = ctk.CTkComboBox(
            controls,
            values=["Software Company", "IT Support", "Digital Marketing Agency", "Dental Clinic", "Real Estate Agency", "Law Firm"],
            fg_color="#090A0F", border_color="#2A3042", text_color="#E5E8F0", dropdown_fg_color="#12151E", width=300, height=38
        )
        self.category_entry.grid(row=1, column=0, padx=15, pady=(0, 12), sticky="w")
        self.category_entry.set("Software Company")

        # 2. Custom Editable Location Input
        ctk.CTkLabel(controls, text="LOCATION / CITY", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A8B0C0").grid(row=0, column=1, sticky="w", padx=10, pady=(12, 2))
        
        self.city_entry = ctk.CTkComboBox(
            controls,
            values=["London, UK", "New York, USA", "Dubai, UAE", "Pakistan", "Toronto, Canada", "Singapore"],
            fg_color="#090A0F", border_color="#2A3042", text_color="#E5E8F0", dropdown_fg_color="#12151E", width=250, height=38
        )
        self.city_entry.grid(row=1, column=1, padx=10, pady=(0, 12), sticky="w")
        self.city_entry.set("Pakistan")

        # 3. Quantity Limit
        ctk.CTkLabel(controls, text="QUANTITY", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A8B0C0").grid(row=0, column=2, sticky="w", padx=10, pady=(12, 2))
        self.limit_entry = ctk.CTkEntry(controls, fg_color="#090A0F", border_color="#2A3042", text_color="#E5E8F0", width=80, height=38)
        self.limit_entry.grid(row=1, column=2, padx=10, pady=(0, 12), sticky="w")
        self.limit_entry.insert(0, "20")

        # Buttons Container
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 8))

        # Extract Button
        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="EXTRACT GOOGLE MAPS LEADS",
            command=self._on_start,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#D4AF37", hover_color="#B89628", text_color="#090A0F", height=44, corner_radius=10
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))

        # Download Excel Button
        self.download_excel_btn = ctk.CTkButton(
            btn_frame,
            text="📥 DOWNLOAD EXCEL (.XLSX)",
            command=self._download_excel,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1F7244", hover_color="#155231", text_color="#FFFFFF", height=44, corner_radius=10, state="disabled"
        )
        self.download_excel_btn.pack(side="right", expand=True, fill="x", padx=(10, 0))

        # Status & Progress
        self.progress_bar = ctk.CTkProgressBar(self, fg_color="#12151E", progress_color="#D4AF37", height=4)
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 6))
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="System Status: Ready • Start extraction to fetch verified leads.")
        self.status_label = ctk.CTkLabel(self, textvariable=self.status_var, font=ctk.CTkFont(size=11, slant="italic"), text_color="#7A8194")
        self.status_label.pack(pady=(0, 8))

        # Data Table View
        table_frame = ctk.CTkFrame(self, fg_color="#12151E", corner_radius=10)
        table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#090A0F", foreground="#E5E8F0", rowheight=26, fieldbackground="#090A0F", borderwidth=0)
        style.configure("Treeview.Heading", background="#1A2030", foreground="#D4AF37", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#2A3550")])

        cols = ("Business Name", "Phone", "Rating", "Website", "Verification Status", "Address")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")

        self.tree.heading("Business Name", text="Business Name")
        self.tree.heading("Phone", text="Phone Number")
        self.tree.heading("Rating", text="Rating")
        self.tree.heading("Website", text="Website")
        self.tree.heading("Verification Status", text="Verification Status")
        self.tree.heading("Address", text="Address")

        self.tree.column("Business Name", width=180)
        self.tree.column("Phone", width=120)
        self.tree.column("Rating", width=50, anchor="center")
        self.tree.column("Website", width=160)
        self.tree.column("Verification Status", width=130, anchor="center")
        self.tree.column("Address", width=220)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

    def _update_status_ui(self, message: str) -> None:
        self.after(0, lambda: self.status_var.set(f"System Status: {message}"))

    def _on_start(self) -> None:
        category = self.category_entry.get().strip()
        city = self.city_entry.get().strip()

        try:
            limit = int(self.limit_entry.get().strip())
        except ValueError:
            limit = 20

        if not category or not city:
            self._update_status_ui("Validation Error: Category and Location cannot be empty.")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.start_btn.configure(state="disabled", fg_color="#303545")
        self.download_excel_btn.configure(state="disabled")
        self.progress_bar.start()

        threading.Thread(
            target=self._run_pipeline,
            args=(category, city, limit),
            daemon=True
        ).start()

    def _run_pipeline(self, category: str, city: str, limit: int) -> None:
        engine = GoogleMapsScraperEngine(self._update_status_ui)
        leads = engine.search_leads(category, city, limit)

        if leads:
            self.current_df = pd.DataFrame(leads)
            file_name = f"{category}_{city}_leads.csv".replace(" ", "_").replace(",", "").lower()
            self.current_df.to_csv(file_name, index=False)

            for lead in leads:
                self.after(0, lambda l=lead: self.tree.insert("", "end", values=(
                    l["Business Name"], l["Phone"], l["Rating"], l["Website"], l["Verification Status"], l["Address"]
                )))

            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self.download_excel_btn.configure(state="normal"))
            self._update_status_ui(f"Done! Extracted {len(leads)} leads with verification flags.")
        else:
            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.set(0))
            self._update_status_ui("Extraction completed with 0 results.")

        self.after(0, lambda: self.start_btn.configure(state="normal", fg_color="#D4AF37"))

    def _download_excel(self) -> None:
        """Exports the current extracted DataFrame into an formatted .xlsx Excel file."""
        if self.current_df.empty:
            self._update_status_ui("No data available to export to Excel.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")],
            title="Save Leads as Excel Spreadsheet"
        )

        if file_path:
            try:
                # Requires openpyxl installed
                self.current_df.to_excel(file_path, index=False, engine="openpyxl")
                self._update_status_ui(f"Successfully downloaded Excel file: {os.path.basename(file_path)}")
            except Exception as e:
                self._update_status_ui(f"Excel export error (Ensure openpyxl is installed): {e}")


if __name__ == "__main__":
    app = ProfessionalLeadStudioGUI()
    app.mainloop()