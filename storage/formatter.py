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

    # def _load_pincodes(self, pincode_file: str):
    #     """Loads pincode lookup matrix to reconcile state and district names."""
    #     if os.path.exists(pincode_file):
    #         try:
    #             df = pd.read_csv(pincode_file, dtype=str)
    #             for _, row in df.iterrows():
    #                 pin = str(row.get('pincode', '')).strip()
    #                 dist = str(row.get('district', '')).strip()
    #                 state = str(row.get('state', '')).strip()
    #                 if pin:
    #                     self.pincode_dict[pin] = (dist, state)
    #         except Exception:
    #             pass


    def _load_pincodes(self, pincode_file: str):
        """Loads pincode lookup matrix to reconcile state and district names."""
        if os.path.exists(pincode_file):
            try:
                # 1. Support both Excel and CSV formats
                if pincode_file.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(pincode_file, dtype=str)
                else:
                    df = pd.read_csv(pincode_file, dtype=str)

                # Normalize column names for flexible matching
                cols = {str(c).strip().lower(): c for c in df.columns}

                def get_val(r, candidates):
                    for k in candidates:
                        if k in cols:
                            val = str(r.get(cols[k], '')).strip()
                            if val and val.lower() not in ('nan', 'none', 'null'):
                                return val
                    return ""

                for _, row in df.iterrows():
                    pin = get_val(row, ['pincode', 'pincode ', 'pin code', 'pin', 'postal code'])
                    dist = get_val(row, ['district', 'district name', 'division name'])
                    state = get_val(row, ['state name', 'statename', 'state', 'circle name', 'circle'])

                    if state.endswith(" Circle"):
                        state = state[:-7].strip()

                    # Fix uppercase or truncated state names
                    if state.upper() == "TELANGAN":
                        state = "Telangana"
                    elif state.isupper():
                        state = state.title()

                    if pin and pin not in self.pincode_dict:
                        self.pincode_dict[pin] = (dist.title() if dist else "", state)
            except Exception:
                pass

    def _load_template_columns(self):
        """
        Loads the reference template columns first.
        Any extra extracted columns are appended strictly at the end.
        """
        if os.path.exists(self.template_file):
            try:
                xls = pd.ExcelFile(self.template_file)
                df = pd.read_excel(self.template_file, sheet_name=xls.sheet_names[0])
                # Keep exact reference columns and their order
                self.target_columns = df.columns.tolist()
            except Exception:
                self._fallback_columns()
        else:
            self._fallback_columns()

        # Extra columns appended strictly at the end without altering template structure
        additional_columns = [
            'Business Status',
            'Mobile number 2',
            'Mobile number 3',
            'Extra Mobile Number',
            'Email 2',
            'Email 3',
            'Extra Email',
            'Category',
            'Rating',
            'Reviews Count',
            'Scraping Status',
            'Owner Name (scraped)',
            'Address (scraped)',
            'Pincodes (scraped)',
            'RERA No (scraped)'
        ]

        for col in additional_columns:
            # Check if column or whitespace alias already exists
            if col not in self.target_columns and f"{col} " not in self.target_columns:
                self.target_columns.append(col)

    def _fallback_columns(self):
        """Default master layout used if the Excel template cannot be loaded."""
        self.target_columns = [
            'Sr. no.', 'Business/Company Name', 'Bussiness/Company Type', 'State Name ',
            'District Name ', 'Location Name ', 'Pincode ', 'Business/Company Address',
            'Contact Person Name', 'Std code ', 'Landline number', 'Mobile number',
            'Toll free number ', 'Contact Person Email Address', 'Invalid Length Mobile',
            'Email', 'Website', 'URL(Link)', 'Location Link',
            # Appended extra columns
            'Business Status', 'Mobile number 2', 'Mobile number 3', 'Extra Mobile Number',
            'Email 2', 'Email 3', 'Extra Email', 'Category', 'Rating', 'Reviews Count',
            'Scraping Status', 'Owner Name (scraped)', 'Address (scraped)',
            'Pincodes (scraped)', 'RERA No (scraped)'
        ]

    def format_row(self, record: BusinessRecord) -> Dict[str, Any]:
        """Reconciles geo-metadata and maps record properties to template headers."""
        final_dist = record.district_name
        final_state = record.state_name
        if record.pincode in self.pincode_dict:
            db_dist, db_state = self.pincode_dict[record.pincode]
            if db_dist:
                final_dist = db_dist.title()
            if db_state:
                final_state = db_state.title()

        # Initialize blank values for every column in the exact target sequence
        row: Dict[str, Any] = {col: "" for col in self.target_columns}

        mapping = {
            # --- BASE REFERENCE TEMPLATE COLUMNS (1-19) ---
            'Sr. no.': record.sr_no,
            'Business/Company Name': record.business_name,
            'Bussiness/Company Type': record.business_type,
            'State Name ': final_state,
            'State Name': final_state,
            'District Name ': final_dist,
            'District Name': final_dist,
            'Location Name ': record.location_name,
            'Location Name': record.location_name,
            'Pincode ': record.pincode,
            'Pincode': record.pincode,
            'Business/Company Address': record.business_address,
            'Contact Person Name': record.extra_attributes.get('Owner Name (scraped)', ''),
            'Std code ': record.std_code,
            'Std code': record.std_code,
            'Landline number': record.landline_number,
            'Mobile number': record.mobile_number,
            'Toll free number ': record.toll_free_number,
            'Toll free number': record.toll_free_number,
            'Contact Person Email Address': record.email_2 if record.email_2 else "",
            'Invalid Length Mobile': "",
            'Email': record.email,
            'Website': record.website,
            'URL(Link)': record.google_maps_url,
            'Location Link': record.google_maps_url,
            'Location Link ': record.google_maps_url,

            # --- EXTRA APPENDED COLUMNS (20+) ---
            'Business Status': record.business_status,
            'Business Status ': record.business_status,
            'Operational Status': record.business_status,
            'Status': record.business_status,
            'Mobile number 2': record.mobile_number_2,
            'Mobile number 3': record.mobile_number_3,
            'Extra Mobile Number': record.extra_mobile_number,
            'Email 2': record.email_2,
            'Email 3': record.email_3,
            'Extra Email': record.extra_email,
            'Category': record.category,
            'Rating': record.rating,
            'Reviews Count': record.reviews_count,
            'Scraping Status': record.scraping_status,
            'Owner Name (scraped)': record.extra_attributes.get('Owner Name (scraped)', ''),
            'Address (scraped)': record.extra_attributes.get('Address (scraped)', ''),
            'Pincodes (scraped)': record.extra_attributes.get('Pincodes (scraped)', ''),
            'RERA No (scraped)': record.extra_attributes.get('RERA No (scraped)', '')
        }

        # Populate mapped keys while preserving column order
        for k, v in mapping.items():
            if k in row and v:
                row[k] = v

        return row