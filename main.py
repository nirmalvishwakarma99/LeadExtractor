import os
import sys
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from config import ScraperConfig
from models import BusinessRecord
from monitoring.logger import setup_logger
from processing.translator import MultilingualHandler
from processing.validator import DataValidator
from processing.deduplicator import Deduplicator
from storage.formatter import DataFormatter
from storage.progress import ProgressManager
from storage.csv_writer import SafeDataWriter
from google_maps.browser import create_stealth_browser, create_stealth_context
from google_maps.search import GoogleMapsSearcher
from variants.non_image.scraper import NonImageScraper

def prompt_user_configuration() -> ScraperConfig:
    print("=" * 65)
    print("  GOOGLE MAPS INTELLIGENT SCRAPER — NON-IMAGE VARIANT A")
    print("=" * 65)

    keyword = ""
    while not keyword.strip():
        keyword = input("Enter search keyword (e.g. Used Bike Dealers): ").strip()

    print("\nRun browser in headless mode?")
    print("1. Yes (Invisible / Faster)")
    print("2. No  (Visible / Recommended for CAPTCHA monitoring)")
    raw_choice = input("Select [1 or 2] (Default: 2): ").strip().lower()
    headless = raw_choice in ("1", "yes", "y", "true")

    workers = 2
    try:
        w_input = input("\nEnter number of concurrent workers [1-6] (Default: 2): ").strip()
        if w_input:
            workers = max(1, min(int(w_input), 6))
    except ValueError:
        workers = 2

    checkpoint_size = 50
    try:
        cp_input = input("\nEnter checkpoint size in records (Default: 50): ").strip()
        if cp_input:
            checkpoint_size = max(5, int(cp_input))
    except ValueError:
        checkpoint_size = 50

    rest_interval = 30
    try:
        rst_input = input("\nEnter rest cooldown after checkpoint in seconds (Default: 30): ").strip()
        if rst_input:
            rest_interval = max(1, int(rst_input))
    except ValueError:
        rest_interval = 30

    return ScraperConfig(
        keyword=keyword,
        headless=headless,
        workers=workers,
        checkpoint_size=checkpoint_size,
        rest_interval=rest_interval
    )

async def worker_task(
    worker_id: int,
    queue: asyncio.Queue,
    scraper: NonImageScraper,
    data_receiver_queue: asyncio.Queue,
    circuit_breaker: asyncio.Event,
    pause_event: asyncio.Event,
    logger
):
    logger.info(f"Worker {worker_id} online.")
    try:
        while True:
            # Respect both CAPTCHA blocks and Checkpoint Rest cooldowns
            await circuit_breaker.wait()
            await pause_event.wait()

            place_url = await queue.get()

            try:
                logger.info(f"[Worker {worker_id}] Scraping: {place_url[:60]}...")
                record = await scraper.process_place(place_url)
                await data_receiver_queue.put(record)
            except Exception as e:
                logger.error(f"[Worker {worker_id}] Error on {place_url}: {e}")
            finally:
                queue.task_done()
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass

async def central_writer_task(
    data_receiver_queue: asyncio.Queue,
    config: ScraperConfig,
    formatter: DataFormatter,
    writer: SafeDataWriter,
    progress: ProgressManager,
    deduplicator: Deduplicator,
    pause_event: asyncio.Event,
    logger,
    stop_event: asyncio.Event
):
    records_buffer = []
    checkpoint_counter = progress.state.get("last_checkpoint_index", 0)
    current_sr_no = progress.state.get("total_records_saved", 0)

    while not stop_event.is_set() or not data_receiver_queue.empty():
        try:
            record: BusinessRecord = await asyncio.wait_for(data_receiver_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        try:
            if record.scraping_status.startswith("Filtered:"):
                # 1. Print full URL and details to console and log file
                logger.warning(
                    f"[DISCARDED] URL: {record.google_maps_url} | "
                    f"Name: '{record.business_name or 'EMPTY'}' | "
                    f"Reason: {record.scraping_status}"
                )

                # 2. Append to a dedicated inspection file
                discard_file = os.path.join(config.output_dir, "discarded_records.csv")
                discard_row = pd.DataFrame([{
                    "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Business Name": record.business_name,
                    "Google Maps URL": record.google_maps_url,
                    "Reason": record.scraping_status
                }])
                file_exists = os.path.exists(discard_file)
                discard_row.to_csv(discard_file, mode="a", header=not file_exists, index=False, encoding="utf-8-sig")
                continue

            deduplicator.register(record)
            current_sr_no += 1
            record.sr_no = current_sr_no

            formatted_dict = formatter.format_row(record)
            records_buffer.append(formatted_dict)
            progress.mark_url_done(record.google_maps_url)
            
            contact_info = record.mobile_number or record.email or "No direct phone/email"
            logger.info(f"[SUCCESS] #{current_sr_no}: {record.business_name} | {contact_info}")

            # --- CHECKPOINT & ACTIVE WORKER COOLDOWN ---
            if len(records_buffer) >= config.checkpoint_size:
                checkpoint_counter += 1
                cp_name = f"checkpoint_{checkpoint_counter:04d}.csv"
                cp_path = os.path.join(config.checkpoint_dir, cp_name)

                # 1. Flush data safely to disk
                writer.append_checkpoint_csv(cp_path, records_buffer, formatter.target_columns)
                progress.state["total_records_saved"] = current_sr_no
                progress.state["last_checkpoint_index"] = checkpoint_counter
                progress.save_atomic()

                logger.info(f"[CHECKPOINT] {len(records_buffer)} records secured -> {cp_name}")
                records_buffer.clear()

                # 2. Genuine worker cooldown: pause workers during rest
                if config.rest_interval > 0:
                    logger.info(f"[REST] Pausing all workers for {config.rest_interval}s cooldown...")
                    pause_event.clear()
                    await asyncio.sleep(config.rest_interval)
                    pause_event.set()
                    logger.info("[REST] Cooldown complete. Resuming scraping.")

        except Exception as e:
            logger.error(f"[WRITER ERROR] Failed processing record: {e}")
        finally:
            data_receiver_queue.task_done()

    # --- FLUSH REMAINING BUFFER ---
    if records_buffer:
        checkpoint_counter += 1
        cp_name = f"checkpoint_{checkpoint_counter:04d}.csv"
        cp_path = os.path.join(config.checkpoint_dir, cp_name)

        writer.append_checkpoint_csv(cp_path, records_buffer, formatter.target_columns)
        progress.state["total_records_saved"] = current_sr_no
        progress.state["last_checkpoint_index"] = checkpoint_counter
        progress.save_atomic()
        logger.info(f"[FINAL CHECKPOINT] Flushed remaining {len(records_buffer)} records to CSV.")

    # --- FINAL EXCEL EXPORT ---
    logger.info("📦 Consolidating final Excel workbook...")
    try:
        writer.export_final_excel()
        logger.info("🎉 Excel exported successfully.")
    except Exception as e:
        logger.error(f"Error compiling Excel: {e}")

async def main():
    config = prompt_user_configuration()
    logger = setup_logger(config.log_dir)

    progress = ProgressManager(config.progress_file)
    writer = SafeDataWriter(config.final_output_file, config.final_excel_file, config.backup_dir)
    formatter = DataFormatter(config.template_file, config.input_pincode_file)
    translator = MultilingualHandler()
    validator = DataValidator()
    deduplicator = Deduplicator()

    # Session Recovery
    completed_urls = list(progress.completed_urls_set)
    if completed_urls:
        print(f"\n[RESUME DETECTED] Found {len(completed_urls)} previously scraped records.")
        print("1. Resume previous session")
        print("2. Overwrite and start new session")
        res_choice = input("Select [1 or 2] (Default: 1): ").strip()
        if res_choice == "2":
            progress.state = {
                "completed_queries": [],
                "completed_urls": [],
                "total_records_saved": 0,
                "last_checkpoint_index": 0
            }
            progress.completed_urls_set.clear()
            progress.completed_queries_set.clear()
            progress.save_atomic()
        else:
            for u in completed_urls:
                deduplicator.seen_urls.add(u)

    if not os.path.exists(config.input_pincode_file):
        logger.error(f"Input file not found at: {config.input_pincode_file}")
        return

    pincode_df = pd.read_csv(config.input_pincode_file, dtype=str)
    search_queries = []
    for _, r in pincode_df.iterrows():
        pin = str(r.get('pincode', '')).strip()
        area = str(r.get('area', r.get('office_name', ''))).strip()
        dist = str(r.get('district', '')).strip()

        if pin:
            q = f"{config.keyword} in {pin}"
            if q not in search_queries:
                search_queries.append(q)
        elif area and dist:
            q = f"{config.keyword} in {area} {dist}"
            if q not in search_queries:
                search_queries.append(q)

    remaining_queries = [q for q in search_queries if not progress.is_query_done(q)]
    logger.info(f"Loaded {len(search_queries)} search targets. {len(remaining_queries)} remaining to process.")

    circuit_breaker = asyncio.Event()
    circuit_breaker.set()

    pause_event = asyncio.Event()
    pause_event.set()

    queued_urls = set(progress.completed_urls_set)

    async with async_playwright() as playwright:
        browser = await create_stealth_browser(playwright, config.headless)
        
        search_context = await create_stealth_context(browser)
        search_page = await search_context.new_page()
        searcher = GoogleMapsSearcher(search_page, logger, circuit_breaker)

        scrape_context = await create_stealth_context(browser)
        scraper = NonImageScraper(scrape_context, translator, validator, deduplicator, logger)

        place_queue = asyncio.Queue()
        data_receiver_queue = asyncio.Queue()
        stop_writer_event = asyncio.Event()

        writer_task_coro = asyncio.create_task(
            central_writer_task(
                data_receiver_queue, config, formatter, writer, progress, deduplicator, pause_event, logger, stop_writer_event
            )
        )

        worker_tasks = [
            asyncio.create_task(
                worker_task(i + 1, place_queue, scraper, data_receiver_queue, circuit_breaker, pause_event, logger)
            )
            for i in range(config.workers)
        ]

        try:
            for query in remaining_queries:
                await circuit_breaker.wait()
                await pause_event.wait()
                try:
                    listings = await searcher.search_and_scroll_feed(query)
                    for link in listings:
                        if link not in queued_urls:
                            queued_urls.add(link)
                            await place_queue.put(link)

                    await place_queue.join()
                    progress.mark_query_done(query)
                except Exception as e:
                    logger.error(f"Error handling query {query}: {e}")

        finally:
            for t in worker_tasks:
                t.cancel()

            await data_receiver_queue.join()
            stop_writer_event.set()
            await writer_task_coro

            await search_context.close()
            await scrape_context.close()
            await browser.close()

    logger.info("Extraction pipeline finished.")
    print(f"\n Master CSV output:   {config.final_output_file}")
    print(f" Master Excel output: {config.final_excel_file}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Scraper paused by user. All progress and checkpoints are preserved safely.")