# import os
# import pandas as pd
# from typing import List, Dict, Any
# from storage.backup import create_timestamped_backup

# class SafeDataWriter:
#     def __init__(self, final_csv: str, final_excel: str, backup_dir: str):
#         self.final_csv = final_csv
#         self.final_excel = final_excel
#         self.backup_dir = backup_dir
#         os.makedirs(os.path.dirname(final_csv), exist_ok=True)

#     def write_checkpoint(self, checkpoint_filepath: str, rows: List[Dict[str, Any]], columns: List[str]):
#         if not rows:
#             return
#         os.makedirs(os.path.dirname(checkpoint_filepath), exist_ok=True)
#         df = pd.DataFrame(rows, columns=columns)
#         temp_file = f"{checkpoint_filepath}.tmp"
#         df.to_csv(temp_file, index=False, encoding='utf-8-sig')
#         os.replace(temp_file, checkpoint_filepath)

#     def append_or_write_final(self, rows: List[Dict[str, Any]], columns: List[str]):
#         if not rows:
#             return
#         new_df = pd.DataFrame(rows, columns=columns)
#         if os.path.exists(self.final_csv):
#             # Backup prior to modifying
#             create_timestamped_backup(self.final_csv, self.backup_dir)
#             existing_df = pd.read_csv(self.final_csv, dtype=str)
#             combined_df = pd.concat([existing_df, new_df], ignore_index=True)
#         else:
#             combined_df = new_df

#         # Atomic CSV replacement
#         temp_csv = f"{self.final_csv}.tmp"
#         combined_df.to_csv(temp_csv, index=False, encoding='utf-8-sig')
#         os.replace(temp_csv, self.final_csv)

#         # Export Excel safely
#         try:
#             temp_xlsx = f"{self.final_excel}.tmp"
#             combined_df.to_excel(temp_xlsx, index=False)
#             os.replace(temp_xlsx, self.final_excel)
#         except Exception:
#             pass


import os
import glob
import pandas as pd
from typing import List, Dict, Any
from storage.backup import create_timestamped_backup

PART_FILE_PATTERN = "output/checkpoints/worker_results_part_{}.csv"

class SafeDataWriter:
    def __init__(self, final_csv: str, final_excel: str, backup_dir: str):
        self.final_csv = final_csv
        self.final_excel = final_excel
        self.backup_dir = backup_dir
        os.makedirs(os.path.dirname(final_csv), exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

    def write_worker_part(self, worker_id: int, row_dict: Dict[str, Any]):
        """Writes immediately to worker-specific CSV partition with direct disk flush."""
        part_path = PART_FILE_PATTERN.format(worker_id)
        file_exists = os.path.exists(part_path)
        
        with open(part_path, "a", encoding="utf-8-sig") as f:
            df_row = pd.DataFrame([row_dict])
            df_row.to_csv(f, header=not file_exists and f.tell() == 0, index=False)
            f.flush()
            os.fsync(f.fileno())

    def append_checkpoint_csv(self, checkpoint_filepath: str, rows: List[Dict[str, Any]], columns: List[str]):
        """Writes batch checkpoints strictly as plain CSV (zero Excel locks)."""
        if not rows:
            return
        os.makedirs(os.path.dirname(checkpoint_filepath), exist_ok=True)
        df = pd.DataFrame(rows, columns=columns)
        temp_file = f"{checkpoint_filepath}.tmp"
        df.to_csv(temp_file, index=False, encoding="utf-8-sig")
        os.replace(temp_file, checkpoint_filepath)

        # Append to running master CSV safely
        combined_df = df
        if os.path.exists(self.final_csv) and os.path.getsize(self.final_csv) > 0:
            create_timestamped_backup(self.final_csv, self.backup_dir)
            try:
                existing_df = pd.read_csv(self.final_csv, dtype=str)
                if not existing_df.empty:
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
            except (pd.errors.EmptyDataError, Exception):
                combined_df = df

        temp_final_csv = f"{self.final_csv}.tmp"
        combined_df.to_csv(temp_final_csv, index=False, encoding="utf-8-sig")
        os.replace(temp_final_csv, self.final_csv)

    def export_final_excel(self):
        """Builds the final Excel workbook only once after all scrapers have exited."""
        df = None
        if os.path.exists(self.final_csv) and os.path.getsize(self.final_csv) > 0:
            try:
                df = pd.read_csv(self.final_csv, dtype=str)
            except (pd.errors.EmptyDataError, Exception):
                df = None

        if df is None or df.empty:
            part_files = glob.glob("output/checkpoints/worker_results_part_*.csv")
            if not part_files:
                return
            dfs = []
            for p in part_files:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    try:
                        dfs.append(pd.read_csv(p, dtype=str))
                    except Exception:
                        pass
            if not dfs:
                return
            df = pd.concat(dfs, ignore_index=True)

        # Remove duplicate records
        # Remove duplicate records
        possible_url_cols = ["Location Link", "Location Link ", "Google Maps Profile URL", "Gmap_link"]
        url_col = next((c for c in possible_url_cols if c in df.columns), df.columns[0])
        df = df.drop_duplicates(subset=[url_col], keep="last")

        base, ext = os.path.splitext(self.final_excel)
        temp_xlsx = f"{base}_temp{ext}"
        df.to_excel(temp_xlsx, index=False, engine="openpyxl")
        os.replace(temp_xlsx, self.final_excel)