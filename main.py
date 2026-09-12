import os
import sys
import random
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
from playwright.async_api import Error as PlaywrightError

# Maximum queries to process before proactively recycling browser to free memory
MAX_QUERIES_PER_SESSION = 25
# Maximum times a single query is retried before skipping
MAX_QUERY_RETRIES = 3

active_config = None


def is_driver_crash_error(err: Exception) -> bool:
    """Detects if an exception was caused by Chromium dying or disconnecting."""
    msg = str(err).lower()
    crash_keywords = [
        "connection closed",
        "closed while reading",
        "target closed",
        "driver",
        "socket.send",
        "broken pipe",
        "connection reset",
        "session closed",
        "browser has been closed"
    ]
    return any(k in msg for k in crash_keywords)


class CaptchaTriggeredException(Exception):
    """Raised when Google displays a CAPTCHA or Unusual Traffic interstitial."""
    pass

async def detect_and_handle_captcha(page, logger, output_dir: str) -> bool:
    """Checks whether the current page is a Google CAPTCHA or blocked page."""
    try:
        current_url = page.url.lower()
        title = (await page.title()).lower()

        # 1. URL redirect check (Google always redirects to /sorry/index)
        is_sorry_url = "google.com/sorry" in current_url or "recaptcha" in current_url

        # 2. Text / Title indicator check
        is_blocked_text = False
        if not is_sorry_url:
            content = await page.content()
            content_lower = content.lower()
            if (
                "unusual traffic from your computer network" in content_lower
                or "verify you're a human" in content_lower
                or "recaptcha" in content_lower
                or "g-recaptcha" in content_lower
                or "sorry..." in title
            ):
                is_blocked_text = True

        if is_sorry_url or is_blocked_text:
            # Save screenshot for verification in headless mode
            captcha_img_path = os.path.join(output_dir, "captcha_detected.png")
            await page.screenshot(path=captcha_img_path, full_page=True)
            logger.error(
                f"🚨 [CAPTCHA DETECTED] Google presented a bot verification challenge! "
                f"Evidence saved to: {captcha_img_path}"
            )
            return True

    except Exception:
        pass
    return False


def compile_master_excel(config: ScraperConfig, logger=None):
    """Consolidates Scraped Businesses (Sheet 1) and Zero Results Areas (Sheet 2) into the final Excel file."""
    zero_file = os.path.join(config.output_dir, "zero_results_areas.csv")
    try:
        if not os.path.exists(config.final_output_file) and not os.path.exists(zero_file):
            return

        with pd.ExcelWriter(config.final_excel_file, engine='openpyxl') as xl_writer:
            if os.path.exists(config.final_output_file):
                df_leads = pd.read_csv(config.final_output_file, dtype=str)
                df_leads.to_excel(xl_writer, sheet_name='Scraped Businesses', index=False)

            if os.path.exists(zero_file):
                df_zeros = pd.read_csv(zero_file, dtype=str)
                df_zeros.to_excel(xl_writer, sheet_name='Zero Results Areas', index=False)

        msg = f"🎉 Final multi-sheet Excel workbook compiled: {config.final_excel_file}"
        if logger:
            logger.info(msg)
        else:
            print(msg)
    except Exception as e:
        err_msg = f"Error compiling final Excel workbook: {e}"
        if logger:
            logger.error(err_msg)
        else:
            print(f"[!] {err_msg}")


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

    print("\nSelect Search Target Mode:")
    print("1. Pincode-based (e.g. 'Used Bike Dealers in 411014')")
    print("2. Area & State-based (e.g. 'Used Bike Dealers in Papanpet, Telangana')")
    mode_choice = input("Select [1 or 2] (Default: 1): ").strip()
    search_mode = "area" if mode_choice == "2" else "pincode"

    try:
        cfg = ScraperConfig(
            keyword=keyword,
            headless=headless,
            workers=workers,
            checkpoint_size=checkpoint_size,
            rest_interval=rest_interval,
            search_mode=search_mode
        )
    except TypeError:
        cfg = ScraperConfig(
            keyword=keyword,
            headless=headless,
            workers=workers,
            checkpoint_size=checkpoint_size,
            rest_interval=rest_interval
        )
        setattr(cfg, 'search_mode', search_mode)

    return cfg


async def worker_task(
    worker_id: int,
    queue: asyncio.Queue,
    scraper: NonImageScraper,
    data_receiver_queue: asyncio.Queue,
    circuit_breaker: asyncio.Event,
    pause_event: asyncio.Event,
    crash_event: asyncio.Event,
    logger
):
    logger.info(f"Worker {worker_id} online.")
    try:
        while not crash_event.is_set():
            await circuit_breaker.wait()
            await pause_event.wait()

            try:
                place_url = await asyncio.wait_for(queue.get(), timeout=1.5)
            except asyncio.TimeoutError:
                continue

            try:
                logger.info(f"[Worker {worker_id}] Scraping: {place_url[:60]}...")
                record = await scraper.process_place(place_url)
                await data_receiver_queue.put(record)
            except Exception as e:
                if is_driver_crash_error(e):
                    logger.warning(f"[Worker {worker_id}] Browser disconnected while scraping: {place_url[:60]}")
                    crash_event.set()
                else:
                    logger.error(f"[Worker {worker_id}] Error on {place_url}: {e}")
            finally:
                queue.task_done()
                # Anti-bot human jitter to prevent rate-limiting
                await asyncio.sleep(random.uniform(1.2, 2.5))
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
            # 1. Filtered Out by Keyword / Relevance
            if record.scraping_status.startswith("Filtered:"):
                logger.warning(
                    f"[DISCARDED] URL: {record.google_maps_url} | "
                    f"Name: '{record.business_name or 'EMPTY'}' | "
                    f"Reason: {record.scraping_status}"
                )

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

            # 2. Filtered Out by Google Anti-Bot Rate Limit ("BLOCKED")
            if record.business_status == "BLOCKED" or record.location_name == "BLOCKED":
                logger.warning(
                    f"[BLOCKED / RATE-LIMITED] Google Maps blocked profile card: {record.google_maps_url} | "
                    f"Name: '{record.business_name or 'EMPTY'}'"
                )
                discard_file = os.path.join(config.output_dir, "discarded_records.csv")
                discard_row = pd.DataFrame([{
                    "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Business Name": record.business_name,
                    "Google Maps URL": record.google_maps_url,
                    "Reason": "Anti-bot Rate Limit (BLOCKED)"
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
    compile_master_excel(config, logger)


async def run_session(
    config: ScraperConfig,
    search_queries: list,
    progress: ProgressManager,
    writer: SafeDataWriter,
    formatter: DataFormatter,
    translator: MultilingualHandler,
    validator: DataValidator,
    deduplicator: Deduplicator,
    logger,
    query_failure_counts: dict
) -> bool:
    remaining_queries = [q for q in search_queries if not progress.is_query_done(q)]
    if not remaining_queries:
        return True

    logger.info(f"Launching browser session ({len(remaining_queries)} queries remaining)...")

    circuit_breaker = asyncio.Event()
    circuit_breaker.set()

    pause_event = asyncio.Event()
    pause_event.set()

    crash_event = asyncio.Event()
    queued_urls = set(progress.completed_urls_set)

    browser = None
    search_context = None
    scrape_context = None
    worker_tasks = []
    data_receiver_queue = asyncio.Queue()
    stop_writer_event = asyncio.Event()

    async with async_playwright() as playwright:
        try:
            browser = await create_stealth_browser(playwright, config.headless)

            search_context = await create_stealth_context(browser)
            search_page = await search_context.new_page()
            searcher = GoogleMapsSearcher(search_page, logger, circuit_breaker)

            scrape_context = await create_stealth_context(browser)
            scraper = NonImageScraper(scrape_context, translator, validator, deduplicator, logger)

            place_queue = asyncio.Queue()

            writer_task_coro = asyncio.create_task(
                central_writer_task(
                    data_receiver_queue, config, formatter, writer, progress, deduplicator, pause_event, logger, stop_writer_event
                )
            )

            worker_tasks = [
                asyncio.create_task(
                    worker_task(i + 1, place_queue, scraper, data_receiver_queue, circuit_breaker, pause_event, crash_event, logger)
                )
                for i in range(config.workers)
            ]

            queries_processed_in_session = 0

            for query in remaining_queries:
                await circuit_breaker.wait()
                await pause_event.wait()

                # Proactive session recycling to release RAM before leaks occur
                if queries_processed_in_session >= MAX_QUERIES_PER_SESSION:
                    logger.info(f"🔄 Memory checkpoint: Processed {queries_processed_in_session} queries. Cycling browser session...")
                    break

                if crash_event.is_set():
                    break

                try:
                    if not browser.is_connected() or search_page.is_closed():
                        raise RuntimeError("Chromium process is disconnected.")

                    # --- 90-SECOND STRICT WATCHDOG TIMEOUT ---
                    try:
                        listings = await asyncio.wait_for(
                            searcher.search_and_scroll_feed(query),
                            timeout=90.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"⏱️ [90s TIMEOUT] Query '{query}' stalled for 90 seconds. "
                            "Breaking stuck feed and recycling session..."
                        )
                        try:
                            timeout_snap = os.path.join(config.output_dir, "timeout_debug.png")
                            await search_page.screenshot(path=timeout_snap)
                        except Exception:
                            pass

                        crash_event.set()
                        break

                    # --- ACTIVE CAPTCHA / BOT-WALL INTERCEPTION ---
                    if await detect_and_handle_captcha(search_page, logger, config.output_dir):
                        raise CaptchaTriggeredException(f"Google served bot challenge during '{query}'")

                    current_url = search_page.url.lower()
                    if "google.com/sorry" in current_url or "recaptcha" in current_url:
                        try:
                            captcha_snap = os.path.join(config.output_dir, "captcha_detected.png")
                            await search_page.screenshot(path=captcha_snap)
                            logger.info(f"📸 CAPTCHA screenshot saved to: {captcha_snap}")
                        except Exception:
                            pass
                        raise CaptchaTriggeredException(f"Google redirected to sorry/captcha on '{query}'")

                    # --- ZERO RESULTS HANDLING ---
                    if not listings:
                        logger.warning(f"⚠️ [0 RESULTS] No listings found for: '{query}'")

                        query_meta = getattr(config, 'query_meta', {})
                        if query in query_meta:
                            meta = query_meta[query]
                        else:
                            loc_part = query.split(" in ")[-1] if " in " in query else ""
                            parts = [p.strip() for p in loc_part.split(",")]
                            area_part = parts[0] if len(parts) > 0 else ""
                            state_part = parts[1] if len(parts) > 1 else ""

                            meta = {
                                "Keyword": config.keyword,
                                "Office Name": "" if area_part.isdigit() else area_part,
                                "Pincode": area_part if area_part.isdigit() else "",
                                "District": "",
                                "State Name": state_part,
                                "Query": query,
                                "Status": "0 Brokers Found",
                                "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                            }

                        zero_file = os.path.join(config.output_dir, "zero_results_areas.csv")
                        file_exists = os.path.exists(zero_file)
                        pd.DataFrame([meta]).to_csv(
                            zero_file, mode="a", header=not file_exists, index=False, encoding="utf-8-sig"
                        )

                    # 1. Enqueue all unique scraped links
                    for link in listings:
                        if link not in queued_urls:
                            queued_urls.add(link)
                            await place_queue.put(link)

                    # 2. Deadlock-free queue wait with 120s safety ceiling
                    wait_start = asyncio.get_event_loop().time()
                    while not place_queue.empty() or place_queue._unfinished_tasks > 0:
                        if crash_event.is_set() or not browser.is_connected():
                            raise RuntimeError("Browser disconnected while processing listings.")

                        if (asyncio.get_event_loop().time() - wait_start) > 120.0:
                            logger.warning(f"⚠️ Workers stalled on place queue for '{query}'. Forcing advance...")
                            break

                        await asyncio.sleep(1.0)

                    progress.mark_query_done(query)
                    queries_processed_in_session += 1

                except CaptchaTriggeredException as ce:
                    logger.error(f"🛑 [BOT BARRIER] {ce}")
                    return False, True

                except Exception as e:
                    if is_driver_crash_error(e) or crash_event.is_set():
                        query_failure_counts[query] = query_failure_counts.get(query, 0) + 1
                        logger.warning(
                            f"⚠️ Browser crash during '{query}' "
                            f"(Attempt {query_failure_counts[query]}/{MAX_QUERY_RETRIES}): {e}"
                        )
                        if query_failure_counts[query] >= MAX_QUERY_RETRIES:
                            logger.error(f"❌ Skipping '{query}' after {MAX_QUERY_RETRIES} crash attempts.")
                            progress.mark_query_done(query)

                        while not place_queue.empty():
                            try:
                                place_queue.get_nowait()
                                place_queue.task_done()
                            except Exception:
                                break

                        crash_event.set()
                        break
                    else:
                        logger.error(f"Error handling query {query}: {e}")
                        progress.mark_query_done(query)

        finally:
            # Cancel all workers immediately
            for t in worker_tasks:
                t.cancel()

            # Drain data queue safely to writer
            try:
                await asyncio.wait_for(data_receiver_queue.join(), timeout=10.0)
            except Exception:
                pass

            stop_writer_event.set()
            try:
                await writer_task_coro
            except Exception as e:
                logger.error(f"Writer flush error: {e}")

            # Safe cleanup
            try:
                if search_context: await search_context.close()
            except Exception: pass

            try:
                if scrape_context: await scrape_context.close()
            except Exception: pass

            try:
                if browser and browser.is_connected(): await browser.close()
            except Exception: pass

    still_remaining = [q for q in search_queries if not progress.is_query_done(q)]
    return len(still_remaining) == 0


def build_pincode_queries(df: pd.DataFrame, keyword: str):
    """Strategy A: High-speed O(1) Pincode-targeted query generation."""
    cols = {str(c).strip().lower(): c for c in df.columns}

    def get_val(row, candidate_keys):
        for key in candidate_keys:
            if key in cols:
                val = str(row.get(cols[key], '')).strip()
                if val and val.lower() not in ('nan', 'none', 'null'):
                    return val
        return ""

    search_queries = []
    seen_queries = set()
    query_meta = {}

    for r in df.to_dict(orient="records"):
        pin = get_val(r, ['pincode', 'pin code', 'pin', 'postal code', 'postal_code'])
        area = get_val(r, ['office name', 'office_name', 'officename', 'area', 'locality'])
        dist = get_val(r, ['district', 'district_name', 'division', 'division name'])
        state = get_val(r, ['state name', 'statename', 'state_name', 'state', 'circle name', 'circle'])

        if state.endswith(" Circle"):
            state = state[:-7].strip()
        if state and state.isupper():
            state = state.title()

        if pin:
            q = f"{keyword} in {pin}"
        elif area and dist:
            q = f"{keyword} in {area.title()} {dist.title()}"
        else:
            continue

        if q not in seen_queries:
            seen_queries.add(q)
            search_queries.append(q)
            query_meta[q] = {
                "Keyword": keyword,
                "Office Name": area.title() if area else "",
                "Pincode": pin if pin else "",
                "District": dist.title() if dist else "",
                "State Name": state,
                "Query": q,
                "Status": "0 Brokers Found",
                "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    return search_queries, query_meta


def build_area_queries(df: pd.DataFrame, keyword: str):
    """Strategy B: High-speed O(1) Area & State targeted query generation."""
    cols = {str(c).strip().lower(): c for c in df.columns}

    def get_val(row, candidate_keys):
        for key in candidate_keys:
            if key in cols:
                val = str(row.get(cols[key], '')).strip()
                if val and val.lower() not in ('nan', 'none', 'null'):
                    return val
        return ""

    search_queries = []
    seen_queries = set()
    query_meta = {}

    for r in df.to_dict(orient="records"):
        area = get_val(r, ['office name', 'office_name', 'officename', 'area', 'locality', 'sub_district'])
        state = get_val(r, ['state name', 'statename', 'state_name', 'state', 'circle name', 'circle'])

        if state.endswith(" Circle"):
            state = state[:-7].strip()
        if state and state.isupper():
            state = state.title()

        district = get_val(r, ['district', 'district_name', 'division', 'division name'])
        pincode = get_val(r, ['pincode', 'pin code', 'pin', 'postal code'])

        if area and state:
            q = f"{keyword} in {area.title()}, {state}"
        elif area and district:
            q = f"{keyword} in {area.title()}, {district.title()}"
        elif area:
            q = f"{keyword} in {area.title()}"
        elif pincode:
            q = f"{keyword} in {pincode}"
        else:
            continue

        if q not in seen_queries:
            seen_queries.add(q)
            search_queries.append(q)
            query_meta[q] = {
                "Keyword": keyword,
                "Office Name": area.title() if area else "",
                "Pincode": pincode,
                "District": district.title() if district else "",
                "State Name": state,
                "Query": q,
                "Status": "0 Brokers Found",
                "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    return search_queries, query_meta


async def main():
    global active_config
    config = prompt_user_configuration()
    active_config = config
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

    # Load dataset dynamically (handles both CSV and Excel)
    if config.input_pincode_file.endswith(('.xlsx', '.xls')):
        pincode_df = pd.read_excel(config.input_pincode_file, dtype=str)
    else:
        pincode_df = pd.read_csv(config.input_pincode_file, dtype=str)

    # Route dynamically based on user mode selection
    search_mode = getattr(config, 'search_mode', 'pincode')
    if search_mode == "area":
        logger.info("Executing Strategy: Area & State Targeted Extraction ('{Keyword} in {Area}, {State}')")
        res = build_area_queries(pincode_df, config.keyword)
    else:
        logger.info("Executing Strategy: Pincode Targeted Extraction ('{Keyword} in {Pincode}')")
        res = build_pincode_queries(pincode_df, config.keyword)

    # Safe tuple unpacking: guarantees search_queries is list[str] and query_meta is dict
    if isinstance(res, tuple):
        search_queries, query_meta = res
    else:
        search_queries, query_meta = res, {}

    config.query_meta = query_meta

    total_queries = len(search_queries)
    remaining_queries = [q for q in search_queries if not progress.is_query_done(q)]
    logger.info(f"Loaded {total_queries} search targets. {len(remaining_queries)} remaining to process.")

    query_failure_counts = {}

    CAPTCHA_COOLDOWN_SECONDS = 300  # 5 minutes cooldown (adjust to 600 for 10 minutes if needed)

    # Master Execution Loop: Automatically handles crashes and CAPTCHA cooling
    while True:
        session_result = await run_session(
            config=config,
            search_queries=search_queries,
            progress=progress,
            writer=writer,
            formatter=formatter,
            translator=translator,
            validator=validator,
            deduplicator=deduplicator,
            logger=logger,
            query_failure_counts=query_failure_counts
        )

        # Handle tuple or boolean return
        if isinstance(session_result, tuple):
            is_all_complete, captcha_triggered = session_result
        else:
            is_all_complete, captcha_triggered = session_result, False

        if is_all_complete:
            break

        if captcha_triggered:
            logger.warning(
                f"⏸️ [CAPTCHA COOLING] Browser closed. Sleeping for {CAPTCHA_COOLDOWN_SECONDS // 60} "
                f"minutes ({CAPTCHA_COOLDOWN_SECONDS}s) to reset Google IP reputation..."
            )
            await asyncio.sleep(CAPTCHA_COOLDOWN_SECONDS)
            logger.info("🔄 Cooldown complete. Launching a fresh Chromium browser session...")
        else:
            logger.info("Restarting clean browser engine in 3 seconds...")
            await asyncio.sleep(3.0)

    logger.info("Extraction pipeline finished.")
    compile_master_excel(config, logger)
    print(f"\n Master CSV output:   {config.final_output_file}")
    print(f" Master Excel output: {config.final_excel_file}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + "=" * 65)
        print("[!] Scraper manually paused by user.")
        print("[!] Consolidating progress into master Excel workbook...")
        try:
            cfg = active_config or ScraperConfig(keyword="", headless=True)
            compile_master_excel(cfg)
        except Exception as e:
            print(f"[!] Consolidation note: {e}")
        print("[✓] All progress and checkpoints are preserved safely. Resume anytime!")
        print("=" * 65)