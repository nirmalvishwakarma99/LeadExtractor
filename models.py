from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any




@dataclass
class BusinessRecord:
    sr_no: int = 0
    business_name: str = ""
    business_address: str = ""
    business_type: str = ""
    pincode: str = ""
    district_name: str = ""
    state_name: str = ""
    location_name: str = ""
    
    # Phone number slots
    mobile_number: str = ""
    mobile_number_2: str = ""
    mobile_number_3: str = ""
    extra_mobile_number: str = ""    # Separated by ' / '

    # Email slots
    email: str = ""
    email_2: str = ""
    email_3: str = ""
    extra_email: str = ""            # Separated by ', '

    landline_number: str = ""
    std_code: str = ""
    toll_free_number: str = ""
    website: str = ""
    category: str = ""
    rating: str = ""
    reviews_count: str = ""
    google_maps_url: str = ""
    business_status: str = ""
    scraping_status: str = "Success"
    raw_extracted_phones: str = ""
    extra_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)