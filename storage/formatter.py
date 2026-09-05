import os
import pandas as pd
from typing import Dict, Any, List
from models import BusinessRecord

class DataFormatter:
    def __init__(self, template_file: str, pincode_db_file: str):
        self.template_file = template_file
        self.pincode_dict: Dict[str, tuple] = {}
        self.target_columns: List[str] = []
        self._load_pincodes(pincode_db_file)
        self._load_template_columns()

    def _load_pincodes(self, pincode_file: str):
        if os.path.exists(pincode_file):
            try:
                df = pd.read_csv(pincode_file, dtype=str)
                for _, row in df.iterrows():
                    pin = str(row.get('pincode', '')).strip()
                    dist = str(row.get('district', '')).strip()
                    state = str(row.get('state', '')).strip()
                    if pin:
                        self.pincode_dict[pin] = (dist, state)
            except Exception:
                pass

    def _load_template_columns(self):
        if os.path.exists(self.template_file):
            try:
                xls = pd.ExcelFile(self.template_file)
                df = pd.read_excel(self.template_file, sheet_name=xls.sheet_names[0])
                self.target_columns = df.columns.tolist()
            except Exception:
                self._fallback_columns()
        else:
            self._fallback_columns()

    def _fallback_columns(self):
        self.target_columns = [
            'Sr. no.', 'Business/Company Name', 'Business/Company Address', 'Bussiness/Company Type',
            'Pincode ', 'State Name ', 'District Name ', 'Location Name ', 'Mobile number',
            'Mobile number 2', 'Mobile number 3', 'Landline number', 'Std code ', 'Toll free number ',
            'Email', 'Website', 'Category', 'Rating', 'Reviews Count', 'Location Link',
            'Business Status', 'Scraping Status'
        ]

    def format_row(self, record: BusinessRecord) -> Dict[str, Any]:
        # Reconcile geographic details from verified pincode database
        final_dist = record.district_name
        final_state = record.state_name
        if record.pincode in self.pincode_dict:
            db_dist, db_state = self.pincode_dict[record.pincode]
            if db_dist: final_dist = db_dist.title()
            if db_state: final_state = db_state.title()

        row: Dict[str, Any] = {}
        for col in self.target_columns:
            row[col] = ""

        # Map explicitly maintaining template compatibility (including trailing spaces)
        # Base mapping
        # Base mapping
        mapping = {
            'Sr. no.': record.sr_no,
            'Business/Company Name': record.business_name,
            'Business/Company Address': record.business_address,
            'Bussiness/Company Type': record.business_type,
            'Pincode ': record.pincode,
            'Pincode': record.pincode,
            'State Name ': final_state,
            'District Name ': final_dist,
            'Location Name ': record.location_name,
            'Mobile number': record.mobile_number,
            'Mobile number 2': record.mobile_number_2,
            'Mobile number 3': record.mobile_number_3,
            'Landline number': record.landline_number,
            'Std code ': record.std_code,
            'Toll free number ': record.toll_free_number,
            'Email': record.email,
            'Website': record.website,
            'Category': record.category,
            'Rating': record.rating,
            'Reviews Count': record.reviews_count,
            
            # --- GOOGLE MAPS LINK MAPPINGS ---
            'Location Link': record.google_maps_url,
            'Location Link ': record.google_maps_url,
            'Location link': record.google_maps_url,
            'Google Maps Profile URL': record.google_maps_url,
            'Gmap_link': record.google_maps_url,

            'Business Status': record.business_status,
            'Scraping Status': record.scraping_status,
            'Site Email 1': record.extra_attributes.get('Site Email 1', ''),
            'Site Email 2': record.extra_attributes.get('Site Email 2', ''),
            'Site Mobile Number': record.extra_attributes.get('Site Mobile Number', ''),
            'Site Mobile Number 2': record.extra_attributes.get('Site Mobile Number 2', ''),
            'Site Toll Free': record.extra_attributes.get('Site Toll Free', ''),
            'Site Landline': record.extra_attributes.get('Site Landline', ''),
            'Owner Name (scraped)': record.extra_attributes.get('Owner Name (scraped)', ''),
            'Address (scraped)': record.extra_attributes.get('Address (scraped)', ''),
            'Pincodes (scraped)': record.extra_attributes.get('Pincodes (scraped)', ''),
            'RERA No (scraped)': record.extra_attributes.get('RERA No (scraped)', '')
        }

        for k, v in mapping.items():
            if k in row:
                row[k] = v

        return row