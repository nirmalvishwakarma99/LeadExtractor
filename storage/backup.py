import os
import shutil
from datetime import datetime

def create_timestamped_backup(source_csv: str, backup_dir: str):
    if not os.path.exists(source_csv):
        return
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(source_csv).replace(".csv", "")
    dest_path = os.path.join(backup_dir, f"{base_name}_{ts}.csv")
    shutil.copy2(source_csv, dest_path)