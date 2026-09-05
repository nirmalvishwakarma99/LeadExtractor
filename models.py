from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any

@dataclass
class BusinessRecord:
    sr_no: int = 0
    business_name: str = ""
    business_address: str = ""
    business_type: str = "Other"
    pincode: str = ""
    state_name: str = ""
    district_name: str = ""
    location_name: str = ""
    mobile_number: str = ""
    mobile_number_2: str = ""
    mobile_number_3: str = ""
    landline_number: str = ""
    std_code: str = ""
    toll_free_number: str = ""
    email: str = ""
    website: str = ""
    category: str = ""
    rating: str = ""
    reviews_count: str = ""
    google_maps_url: str = ""
    business_status: str = "Operational"
    scraping_status: str = "Success"
    raw_extracted_phones: str = ""
    extra_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)