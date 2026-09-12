import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ScraperConfig:
    keyword: str = ""
    headless: bool = False
    workers: int = 2
    checkpoint_size: int = 50
    rest_interval: int = 30
    
    # Path configuration
    base_dir: str = os.path.dirname(os.path.abspath(__file__))
    # input_pincode_file: str = os.path.join(base_dir, "input", "pincode_areas_output.csv")
    input_pincode_file: str = r"E:\Projects\google_maps_scraper\input\Areas_Name_All_india.xlsx"
    template_file: str = os.path.join(base_dir, "template", "Formate_for_genral.xlsx")
    
    output_dir: str = os.path.join(base_dir, "output")
    final_output_file: str = os.path.join(output_dir, "final", "scraped_businesses.csv")
    final_excel_file: str = os.path.join(output_dir, "final", "scraped_businesses.xlsx")
    checkpoint_dir: str = os.path.join(output_dir, "checkpoints")
    backup_dir: str = os.path.join(output_dir, "backup")
    progress_file: str = os.path.join(output_dir, "progress.json")
    log_dir: str = os.path.join(base_dir, "logs")

    # Anti-bot and timeouts
    page_timeout: int = 30000
    navigation_timeout: int = 35000
    max_scroll_attempts: int = 40