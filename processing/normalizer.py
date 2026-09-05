import re
from typing import Tuple, List, Dict, Any

STATE_MAP = {
    'Abohar': 'Punjab', 'Adampur': 'Punjab', 'Agartala': 'Tripura', 'Agra': 'Uttar Pradesh',
    'Ahmednagar': 'Maharashtra', 'Ahmedabad': 'Gujarat', 'Akola': 'Maharashtra', 'Ajmer': 'Rajasthan',
    'Alwar': 'Rajasthan', 'Aligarh': 'Uttar Pradesh', 'Allahabad': 'Uttar Pradesh', 'Amravati': 'Maharashtra',
    'Ambala': 'Haryana', 'Amritsar': 'Punjab', 'Anand': 'Gujarat', 'Anantnag': 'Jammu and Kashmir',
    'Anjar': 'Gujarat', 'Asansol': 'West Bengal', 'Aurangabad': 'Maharashtra', 'Bangalore': 'Karnataka',
    'Chennai': 'Tamil Nadu', 'Delhi': 'Delhi', 'Hyderabad': 'Telangana', 'Kolkata': 'West Bengal',
    'Mumbai': 'Maharashtra', 'Pune': 'Maharashtra', 'Surat': 'Gujarat', 'Vadodara': 'Gujarat',
    'Jaipur': 'Rajasthan', 'Lucknow': 'Uttar Pradesh', 'Kanpur': 'Uttar Pradesh', 'Nagpur': 'Maharashtra',
    'Indore': 'Madhya Pradesh', 'Thane': 'Maharashtra', 'Bhopal': 'Madhya Pradesh', 'Visakhapatnam': 'Andhra Pradesh',
    'Pimpri-Chinchwad': 'Maharashtra', 'Patna': 'Bihar', 'Ghaziabad': 'Uttar Pradesh', 'Ludhiana': 'Punjab'
}

def extract_pincode(address: str) -> str:
    if not address:
        return ""
    address = str(address).replace(".0", "")
    match = re.search(r'(?:Pin Code[-\s:]*|[^a-zA-Z0-9])(\d{6})\b', address, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'\b(\d{6})\b', address)
    return match.group(1) if match else ""

def get_company_type(name: str) -> str:
    if not name:
        return "Other"
    name_lower = str(name).lower()
    if any(x in name_lower for x in ['pvt ltd', 'pvt. ltd.', 'private limited']):
        return 'Pvt Ltd'
    elif any(x in name_lower for x in [' ltd', 'ltd.', 'limited']):
        return 'Public Ltd'
    elif any(x in name_lower for x in ['motors', 'auto', 'enterprises', 'agency', 'traders', 'store', 'shop', 'dealer']):
        return 'Other'
    return 'Individual'

def extract_city(address: str) -> str:
    if not address:
        return ""
    parts = str(address).split(',')
    if len(parts) > 1:
        last = parts[-1].strip()
        last_clean = re.sub(r'\d{6}(\.0)?', '', last).strip()
        if not last_clean or any(s.lower() in last_clean.lower() for s in STATE_MAP.values()):
            return parts[-2].strip() if len(parts) > 2 else last_clean
        return last_clean
    return ""

def parse_phone_robust(phone_str: str) -> Tuple[List[str], List[str], List[str], List[str]]:
    if not phone_str or str(phone_str).strip().lower() in ['nan', 'none', 'n/a']:
        return [], [], [], []
    
    mobiles, landlines, std_codes, toll_frees = [], [], [], []
    clean_str = str(phone_str).replace('.0', '')
    phones = re.split(r'[,/|]+', clean_str)

    for p in phones:
        p_clean = re.sub(r'\D', '', p)
        if not p_clean:
            continue
        if p_clean.startswith('1') and len(p_clean) == 11 and (p_clean.startswith('1800') or p_clean.startswith('1860')):
            toll_frees.append(p_clean)
        elif len(p_clean) == 10 and p_clean[0] in '6789':
            mobiles.append(p_clean)
        elif len(p_clean) == 11 and p_clean.startswith('0') and p_clean[1] in '6789':
            mobiles.append(p_clean[1:])
        elif len(p_clean) == 12 and p_clean.startswith('91') and p_clean[2] in '6789':
            mobiles.append(p_clean[2:])
        elif p_clean.startswith('0'):
            if len(p_clean) >= 10:
                if p_clean.startswith(('011', '022', '033', '044', '040', '080', '020', '079')):
                    std_codes.append(p_clean[:3])
                    landlines.append(p_clean[3:])
                elif len(p_clean) == 10:
                    std_codes.append(p_clean[:4])
                    landlines.append(p_clean[4:])
                else:
                    std_codes.append(p_clean[:5])
                    landlines.append(p_clean[5:])
            else:
                std_codes.append(p_clean)
                landlines.append('')
        elif 6 <= len(p_clean) <= 8 and p_clean[0] not in '6789':
            landlines.append(p_clean)
            std_codes.append('')
        else:
            if len(p_clean) == 10:
                mobiles.append(p_clean)

    return (
        list(dict.fromkeys(mobiles)),
        list(dict.fromkeys(landlines)),
        list(dict.fromkeys(std_codes)),
        list(dict.fromkeys(toll_frees))
    )

def extract_location_smart(address: str, city: str) -> str:
    if not address:
        return ""
    parts = [p.strip() for p in str(address).split(',') if p.strip()]
    if len(parts) <= 1:
        return ""

    clean_parts = []
    for p in parts:
        if re.search(r'(Pin|Iin)\s*Code|^\d{6}(\.0)?$|Code No-', p, re.IGNORECASE):
            continue
        if city and isinstance(city, str) and p.lower() == city.lower():
            continue
        if any(s.lower() in p.lower() for s in STATE_MAP.values()):
            continue
        clean_parts.append(p)

    if not clean_parts:
        return ""

    for p in clean_parts:
        if re.search(r'\b(Near|Opposite|Opp\.|Opp|Behind|Beside|Nr\.|Landmark)\b', p, re.IGNORECASE):
            return p

    return clean_parts[0] if len(clean_parts[0]) > 2 else ""