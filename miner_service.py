# Main application logic for the IPFS miner service
import asyncio
import logging
import json
import os
import time
import binascii # Added for hex decoding
import coloredlogs # Import coloredlogs

import db_manager
import ipfs_utils
import substrate_interface
import config_manager # Import the whole module to access its pre-defined config variables

# Configuration values are now accessed via config_manager.VARIABLE_NAME
# POLLING_INTERVAL_SECONDS = int(os.environ.get("POLLING_INTERVAL_SECONDS", 60))
# MAX_PIN_RETRIES = int(os.environ.get("MAX_PIN_RETRIES", 5))
# UNPINNABLE_CIDS_REPORT_FILE = os.environ.get("UNPINNABLE_CIDS_REPORT_FILE", "unpinnable_cids_report.json")

# Get own IPFS Node ID - this is crucial for querying the correct profile
MY_IPFS_NODE_ID = None # Will be fetched at startup

HIPPIUS_ASCII_ART = """
HHHHHHHHH     HHHHHHHHHIIIIIIIIII PPPPPPPPPPPPPPPPP   PPPPPPPPPPPPPPPPP   IIIIIIIIIIUUUUUUUU     UUUUUUUU   SSSSSSSSSSSSSSS 
 H:::::::H     H:::::::HI::::::::IP::::::::::::::::P  P::::::::::::::::P  I::::::::IU::::::U     U::::::U SS:::::::::::::::S
 H:::::::H     H:::::::HI::::::::IP::::::PPPPPPPPP::P P::::::PPPPPPPPP::P I::::::::IU::::::U     U::::::US:::::SSSSSS::::::S
 HH::::::H     H::::::HHII::::::II P:::::P     P:::::P P:::::P     P:::::PII::::::IIUU:::::U     U:::::UUS:::::S     SSSSSSS
   H:::::H     H:::::H   I::::I   P:::::P     P:::::P P:::::P     P:::::P  I::::I   U:::::U     U:::::UUS:::::S            
   H:::::H     H:::::H   I::::I   P:::::P     P:::::P P:::::P     P:::::P  I::::I   U:::::D     D:::::UUS:::::S            
   H::::::HHHHH::::::H   I::::I   P:::::PPPPPPPP:::::P P:::::PPPPPPPP:::::P  I::::I   U:::::D     D:::::UU S::::SSSS         
   H:::::::::::::::::H   I::::I   P:::::::::::::PPI  P:::::::::::::PPI   I::::I   U:::::D     D:::::UU  SS::::::SSSSS    
   H:::::::::::::::::H   I::::I   P:::::PPPPPPPPP    P:::::PPPPPPPPP     I::::I   U:::::D     D:::::UU   SSS::::::::SS  
   H::::::HHHHH::::::H   I::::I   P:::::P            P:::::P             I::::I   U:::::D     D:::::UU      SSSSSS::::S 
   H:::::H     H:::::H   I::::I   P:::::P            P:::::P             I::::I   U:::::D     D:::::UU           S:::::S
   H:::::H     H:::::H   I::::I   P:::::P            P:::::P             I::::I   U::::::U   U::::::U            S:::::S
 HH::::::H     H::::::HHII::::::II P:::::P            P:::::P           II::::::IIUU:::::::UUU:::::::UUSSSSSSS     S:::::S
 H:::::::H     H:::::::HI::::::::IP:::::P            P:::::P           I::::::::I UUU:::::::::::::UU S::::::SSSSSS:::::S
 H:::::::H     H:::::::HI::::::::IP:::::P            P:::::P           I::::::::I   UU:::::::::UU  S:::::::::::::::SS 
 HHHHHHHHH     HHHHHHHHHIIIIIIIIII PTTTTTTP            PTTTTTTP          IIIIIIIIII     UUUUUUUUU     SSSSSSSSSSSSSSS   
""" 

def decode_profile_file_hash_to_cid(file_hash_array: list[int]) -> str | None:
    """Decodes the file_hash array (list of ASCII values for a hex string) from the profile into a CID string."""
    if not file_hash_array:
        return None
    try:
        # Convert list of ASCII values to a hex string
        hex_string = "".join(chr(val) for val in file_hash_array)
        
        # Now, this hex_string is assumed to be what substrate_interface.decode_hex_bytes_to_cid_string expects
        # or it might be a direct base16 CID string. Let's reuse that logic carefully.
        # For now, let's assume it's the hex of a UTF-8 encoded CID string, or a direct base16 CID.

        if not hex_string:
            logging.warning("File_hash_array decoded to an empty hex string.")
            return None

        # Attempt to decode as hex of UTF-8 string first
        try:
            cid_bytes = binascii.unhexlify(hex_string)
            cid_candidate = cid_bytes.decode('utf-8')
            # Basic validation for typical CID patterns
            if (cid_candidate.startswith('Qm') and len(cid_candidate) == 46) or \
               (cid_candidate.startswith('bafy') and len(cid_candidate) > 50) or \
               (cid_candidate.startswith('k') and len(cid_candidate) > 50):
                logging.debug(f"Decoded file_hash (as hex of UTF-8) '{hex_string}' to CID: {cid_candidate}")
                return cid_candidate
            else:
                logging.warning(f"String from file_hash_array '{cid_candidate}' (from hex '{hex_string}') doesn't look like a standard CID. Returning it as is.")
                return cid_candidate # Fallback, could be an odd CID or different encoding
        except (binascii.Error, UnicodeDecodeError):
            # If unhexlify or UTF-8 decode fails, it might be a direct base16 CID string (without 0x)
            # or some other direct representation the IPFS client can handle.
            # Basic check if it looks like a hex string that could be a base16 CID
            is_likely_hex = all(c in '0123456789abcdefABCDEF' for c in hex_string)
            if is_likely_hex and (hex_string.lower().startswith('f0') or hex_string.lower().startswith('01') or len(hex_string) > 40):
                logging.warning(f"Could not decode file_hash '{hex_string}' as hex of UTF-8. Assuming it is a direct base16 CID or similar.")
                return hex_string # Return the cleaned hex string
            else:
                logging.warning(f"File_hash '{hex_string}' is not valid hex for UTF-8 decode and doesn't look like a direct base16 CID. Returning as is.")
                return hex_string # Fallback: return the derived string as is.
        
    except Exception as e:
        logging.error(f"Error decoding file_hash_array {file_hash_array}: {e}", exc_info=True)
        return None

async def get_self_ipfs_node_id():
    """Fetches and returns the node ID from the Substrate node instead of the IPFS daemon."""
    global MY_IPFS_NODE_ID
    if MY_IPFS_NODE_ID:
        return MY_IPFS_NODE_ID
    try:
        # Get node ID from the Substrate node instead of IPFS
        node_id = await substrate_interface.get_substrate_node_id()
        if node_id:
            MY_IPFS_NODE_ID = node_id
            logging.info(f"Successfully fetched node ID from Substrate: {MY_IPFS_NODE_ID}")
            return MY_IPFS_NODE_ID
        else:
            logging.error("Could not determine node ID from Substrate node.")
            return None
    except Exception as e:
        logging.error(f"Error fetching node ID from Substrate: {e}", exc_info=True)
        return None

async def fetch_and_process_profile(is_startup: bool = False):
    """Fetches the miner's profile CID from chain, parses profile, and updates DB for pinning/unpinning."""
    log_prefix = "[Startup Profile]" if is_startup else "[Periodic Profile]"
    logging.info(f"{log_prefix} Fetching miner profile CID from chain for node ID: {MY_IPFS_NODE_ID}")
    
    if not MY_IPFS_NODE_ID:
        logging.error(f"{log_prefix} Cannot fetch profile, MY_IPFS_NODE_ID is not set.")
        return

    on_chain_profile_cid = await substrate_interface.get_miner_profile_cid(MY_IPFS_NODE_ID)

    current_db_profile_info = await db_manager.get_active_miner_profile()
    current_db_profile_cid = current_db_profile_info[0] if current_db_profile_info else None

    if not on_chain_profile_cid:
        logging.warning(f"{log_prefix} No profile CID found on chain for node {MY_IPFS_NODE_ID}.")
        if current_db_profile_cid: # If a profile was active, and now it's gone from chain
            logging.info(f"{log_prefix} Chain profile cleared. Deactivating local profile {current_db_profile_cid} and marking its content for unpinning.")
            await db_manager.set_active_miner_profile(None) # Deactivate
            # Mark all CIDs from the old (now cleared) profile for unpinning
            db_managed_cids_tuples = await db_manager.get_cids_by_status('pinned') + \
                                     await db_manager.get_cids_by_status('pending_pin') + \
                                     await db_manager.get_cids_by_status('failed_pin')
            for cid_to_remove, _, _ in db_managed_cids_tuples:
                # This includes the old profile document CID itself if it was in pinned_cids
                logging.info(f"{log_prefix} Marking CID {cid_to_remove} (from cleared profile) for unpinning.")
                await db_manager.update_cid_status(cid_to_remove, 'unpin_requested')
        return # Nothing further to do if no profile on chain

    # A profile CID exists on chain
    if on_chain_profile_cid == current_db_profile_cid and not is_startup:
        logging.info(f"{log_prefix} On-chain CID {on_chain_profile_cid} is same as current. Verifying local pin state of profile doc.")
        if current_db_profile_info and not current_db_profile_info[1]: # not pinned_locally
             if await ipfs_utils.pin_cid(on_chain_profile_cid):
                await db_manager.update_miner_profile_pinned_status(on_chain_profile_cid, True)
                await db_manager.update_cid_status(on_chain_profile_cid, 'pinned')
        # No need to re-process content if CID unchanged and it's not startup check
        return

    logging.info(f"{log_prefix} Profile CID is '{on_chain_profile_cid}' (DB was '{current_db_profile_cid}'). Processing.")
    await db_manager.set_active_miner_profile(on_chain_profile_cid)
    
    if await ipfs_utils.pin_cid(on_chain_profile_cid):
        await db_manager.update_miner_profile_pinned_status(on_chain_profile_cid, True)
        await db_manager.update_cid_status(on_chain_profile_cid, 'pinned')
        logging.info(f"{log_prefix} Successfully pinned profile document {on_chain_profile_cid}.")

        profile_content = await ipfs_utils.get_json_from_cid(on_chain_profile_cid)
        if not profile_content or not isinstance(profile_content, list):
            logging.error(f"{log_prefix} Failed to fetch/parse valid list content from profile {on_chain_profile_cid}. Pin list not updated from content.")
            return

        cids_from_profile = set()
        for item in profile_content:
            if isinstance(item, dict) and 'file_hash' in item:
                target_cid = decode_profile_file_hash_to_cid(item['file_hash'])
                if target_cid:
                    cids_from_profile.add(target_cid)
                else:
                    logging.warning(f"{log_prefix} Could not decode file_hash from profile item: {item}")
        logging.info(f"{log_prefix} Found {len(cids_from_profile)} CIDs to manage from profile content.")

        db_managed_cids_tuples = await db_manager.get_cids_by_status('pinned') + \
                                 await db_manager.get_cids_by_status('pending_pin') + \
                                 await db_manager.get_cids_by_status('failed_pin')
        current_managed_cids_in_db = {t[0] for t in db_managed_cids_tuples if t[0] != on_chain_profile_cid}
        if current_db_profile_cid and current_db_profile_cid != on_chain_profile_cid:
            current_managed_cids_in_db.discard(current_db_profile_cid)

        for cid_to_add in (cids_from_profile - current_managed_cids_in_db):
            logging.info(f"{log_prefix} Adding/marking CID {cid_to_add} for pinning.")
            await db_manager.add_cid_to_pin(cid_to_add)

        for cid_to_remove in (current_managed_cids_in_db - cids_from_profile):
            logging.info(f"{log_prefix} Marking CID {cid_to_remove} for unpinning.")
            await db_manager.update_cid_status(cid_to_remove, 'unpin_requested')
    else:
        await db_manager.update_miner_profile_pinned_status(on_chain_profile_cid, False)
        await db_manager.update_cid_status(on_chain_profile_cid, 'failed_pin', 1)
        logging.error(f"{log_prefix} CRITICAL: Failed to pin profile document {on_chain_profile_cid}. Cannot process its content.")
    logging.info(f"{log_prefix} Profile processing finished.")

async def process_pending_pins():
    """Processes CIDs in the 'pending_pin' state."""
    pending_cids = await db_manager.get_cids_by_status('pending_pin')
    if not pending_cids:
        logging.debug("No CIDs in pending_pin state.")
        return
    
    logging.info(f"Found {len(pending_cids)} CIDs to attempt pinning.")
    for cid, retry_count in pending_cids:
        logging.info(f"Attempting to pin CID: {cid} (Retry: {retry_count})")
        success = await ipfs_utils.pin_cid(cid)
        if success:
            await db_manager.update_cid_status(cid, 'pinned')
            logging.info(f"Successfully pinned {cid}.")
        else:
            new_retry_count = retry_count + 1
            if new_retry_count >= config_manager.MAX_PIN_RETRIES:
                logging.warning(f"CID {cid} failed pinning after {new_retry_count} retries. Marking as unpinnable.")
                await db_manager.remove_cid_from_pinning(cid) # Remove from pinned_cids
                await db_manager.add_unpinnable_cid(cid, f"Failed after {new_retry_count} retries.")
            else:
                await db_manager.update_cid_status(cid, 'failed_pin', new_retry_count)
                logging.info(f"Failed to pin {cid}. Will retry. New count: {new_retry_count}")

async def process_failed_pins():
    """Retries CIDs in the 'failed_pin' state if they haven't reached max retries."""
    # This is largely covered by process_pending_pins if failed pins are reset to pending_pin on add_cid_to_pin.
    # However, this function can specifically target those that remained in failed_pin.
    failed_cids = await db_manager.get_cids_by_status('failed_pin')
    if not failed_cids:
        logging.debug("No CIDs in failed_pin state to retry.")
        return

    logging.info(f"Found {len(failed_cids)} CIDs in failed_pin state to re-attempt pinning.")
    for cid, retry_count in failed_cids:
        if retry_count >= config_manager.MAX_PIN_RETRIES:
            logging.warning(f"CID {cid} already at max retries ({retry_count}). Marking as unpinnable without further retry.")
            await db_manager.remove_cid_from_pinning(cid)
            await db_manager.add_unpinnable_cid(cid, f"Reached max retries ({retry_count}) in failed_pin state.")
            continue

        logging.info(f"Re-attempting to pin CID: {cid} (Retry: {retry_count})")
        success = await ipfs_utils.pin_cid(cid)
        if success:
            await db_manager.update_cid_status(cid, 'pinned')
            logging.info(f"Successfully pinned {cid} from failed_pin state.")
        else:
            new_retry_count = retry_count + 1
            if new_retry_count >= config_manager.MAX_PIN_RETRIES:
                logging.warning(f"CID {cid} failed pinning again, total {new_retry_count} retries. Marking as unpinnable.")
                await db_manager.remove_cid_from_pinning(cid)
                await db_manager.add_unpinnable_cid(cid, f"Failed after {new_retry_count} retries.")
            else:
                await db_manager.update_cid_status(cid, 'failed_pin', new_retry_count)
                logging.info(f"Still failed to pin {cid}. Will retry. New count: {new_retry_count}")

async def process_unpin_requests():
    """Processes CIDs in the 'unpin_requested' state."""
    unpin_requests = await db_manager.get_cids_by_status('unpin_requested')
    if not unpin_requests:
        logging.debug("No CIDs in unpin_requested state.")
        return

    logging.info(f"Found {len(unpin_requests)} CIDs to attempt unpinning.")
    for cid, _ in unpin_requests: # retry_count not typically used for unpinning
        logging.info(f"Attempting to unpin CID: {cid}")
        success = await ipfs_utils.unpin_cid(cid)
        if success:
            # Mark as 'unpinned' or remove from pinned_cids table entirely
            await db_manager.remove_cid_from_pinning(cid)
            # Or: await db_manager.update_cid_status(cid, 'unpinned') 
            logging.info(f"Successfully unpinned {cid} and removed from DB tracking.")
        else:
            # Unpinning failures are less common unless CID was never pinned or IPFS error
            # For now, just log. Could add retries if needed.
            logging.error(f"Failed to unpin {cid}. It might not have been pinned or an IPFS error occurred.")
            # Optionally, remove from DB or mark as failed_unpin if retries are desired.
            await db_manager.update_cid_status(cid, 'failed_pin') # Or a new status like 'failed_unpin'

async def reconcile_ipfs_pins():
    """Compares pins in IPFS with the local database and corrects discrepancies."""
    logging.info("Starting IPFS pins reconciliation.")
    try:
        ipfs_pinned_cids = set(await ipfs_utils.list_pinned_cids())
        db_should_be_pinned_cids = set(await db_manager.get_all_pinned_cids_from_db())
        
        active_profile = await db_manager.get_active_miner_profile()
        active_profile_cid = active_profile[0] if active_profile else None

        # CIDs in IPFS but not in DB (or not supposed to be pinned by DB)
        for cid in ipfs_pinned_cids - db_should_be_pinned_cids:
            if cid == active_profile_cid:
                logging.debug(f"Skipping unpin for active profile CID {cid} found in IPFS but not explicitly in db_should_be_pinned_cids (it should be added there by manage_miner_profile).")
                # Ensure active profile is in db_should_be_pinned_cids if it wasn't already
                if active_profile_cid and active_profile_cid not in db_should_be_pinned_cids:
                    await db_manager.add_cid_to_pin(active_profile_cid)
                    await db_manager.update_cid_status(active_profile_cid, 'pinned')
                continue
            logging.warning(f"Reconciliation: CID {cid} pinned in IPFS but not in DB or not marked for pinning. Unpinning.")
            if await ipfs_utils.unpin_cid(cid):
                logging.info(f"Reconciliation: Successfully unpinned {cid}.")
            else:
                logging.error(f"Reconciliation: Failed to unpin {cid}.")

        # CIDs in DB (marked for pinning) but not in IPFS
        for cid in db_should_be_pinned_cids - ipfs_pinned_cids:
            logging.warning(f"Reconciliation: CID {cid} in DB to be pinned, but not found in IPFS. Attempting to pin.")
            if await ipfs_utils.pin_cid(cid):
                await db_manager.update_cid_status(cid, 'pinned') # Ensure DB status is correct
                logging.info(f"Reconciliation: Successfully pinned {cid}.")
            else:
                # This might have been a temporary issue, or it could be an unpinnable CID.
                # Update status to failed_pin to allow retry logic to handle it.
                cid_details = await db_manager.get_cid_details(cid)
                current_retry_count = cid_details[2] if cid_details and cid_details[2] is not None else 0
                new_retry_count = current_retry_count + 1

                if new_retry_count >= config_manager.MAX_PIN_RETRIES:
                    logging.warning(f"Reconciliation: CID {cid} failed pinning after {new_retry_count} total attempts (discovered during reconciliation). Marking as unpinnable.")
                    await db_manager.remove_cid_from_pinning(cid)
                    await db_manager.add_unpinnable_cid(cid, f"Failed after {new_retry_count} retries (discovered during reconciliation).")
                else:
                    await db_manager.update_cid_status(cid, 'failed_pin', new_retry_count)
                    logging.error(f"Reconciliation: Failed to pin {cid}. Marked as failed_pin with retry count {new_retry_count}.")
        logging.info("IPFS pins reconciliation finished.")
    except Exception as e:
        logging.error(f"Error during IPFS pins reconciliation: {e}")

async def report_unpinnable_cids():
    """Generates a JSON report of CIDs that could not be pinned."""
    cids_to_report = await db_manager.get_unpinnable_cids_to_report()
    if not cids_to_report:
        logging.debug("No new unpinnable CIDs to report.")
        return

    report_data = []
    try:
        if os.path.exists(config_manager.UNPINNABLE_CIDS_REPORT_FILE):
            with open(config_manager.UNPINNABLE_CIDS_REPORT_FILE, 'r') as f:
                try:
                    report_data = json.load(f)
                    if not isinstance(report_data, list):
                        logging.warning(f"Existing report file {config_manager.UNPINNABLE_CIDS_REPORT_FILE} is not a list. Starting fresh.")
                        report_data = []
                except json.JSONDecodeError:
                    logging.warning(f"Could not decode existing report file {config_manager.UNPINNABLE_CIDS_REPORT_FILE}. Starting fresh.")
                    report_data = []
    except Exception as e:
        logging.error(f"Error reading existing report file {config_manager.UNPINNABLE_CIDS_REPORT_FILE}: {e}")
        # Continue with an empty list if read fails
        report_data = [] 

    newly_reported_cids_for_db_update = []
    for cid, reason in cids_to_report:
        report_entry = {"cid": cid, "reason": reason, "reported_at": time.time()}
        if not any(entry.get('cid') == cid for entry in report_data): # Avoid duplicates in the file
             report_data.append(report_entry)
        newly_reported_cids_for_db_update.append(cid)

    try:
        with open(config_manager.UNPINNABLE_CIDS_REPORT_FILE, 'w') as f:
            json.dump(report_data, f, indent=4)
        logging.info(f"Successfully wrote/updated unpinnable CIDs report to {config_manager.UNPINNABLE_CIDS_REPORT_FILE}")
        if newly_reported_cids_for_db_update:
            await db_manager.mark_unpinnable_cids_as_reported(newly_reported_cids_for_db_update)
    except Exception as e:
        logging.error(f"Error writing unpinnable CIDs report to {config_manager.UNPINNABLE_CIDS_REPORT_FILE}: {e}")

async def main_loop():
    """The main operational loop for the miner service."""
    # MY_IPFS_NODE_ID should already be set by startup()
    if not MY_IPFS_NODE_ID:
        logging.critical("CRITICAL: MY_IPFS_NODE_ID not set at start of main_loop. Exiting.")
        return
        
    # Subscription setup is removed from here
    # logging.info(f"Initiating Substrate profile subscription for node ID: {MY_IPFS_NODE_ID}")
    # asyncio.create_task(substrate_interface.subscribe_to_profile_changes(
    #     MY_IPFS_NODE_ID,
    #     handle_profile_update, 
    #     handle_subscription_error
    # ))
    
    # Initial profile fetch is done in startup() before main_loop is called
    # logging.info("Performing initial profile fetch before starting main processing loop...")
    # initial_profile_cid = await substrate_interface.get_miner_profile_cid(MY_IPFS_NODE_ID)
    # await handle_profile_update(initial_profile_cid) 

    logging.info("Miner service main processing loop started (polling mode).")
    
    gc_counter = 0

    while True:
        # Log current block number at the start of each cycle
        current_block_num = await substrate_interface.get_current_block_number()
        if current_block_num is not None:
            logging.info(f"Current chain block number: {current_block_num}")
        else:
            logging.warning("Could not determine current chain block number for this cycle.")
            
        logging.debug("Main loop iteration starting (profile poll, pin processing, reconciliation, GC check).")
        try:
            # Poll for profile updates
            await fetch_and_process_profile()
            
            await process_pending_pins()
            await process_failed_pins()
            await process_unpin_requests()
            await reconcile_ipfs_pins() # Still useful for general consistency and old profile doc cleanup
            await report_unpinnable_cids()

            gc_counter += 1
            if gc_counter >= config_manager.GC_TRIGGER_INTERVAL_LOOPS:
                logging.info("Triggering periodic IPFS garbage collection.")
                await ipfs_utils.trigger_garbage_collection()
                gc_counter = 0

        except Exception as e:
            logging.error(f"Unhandled error in main processing loop: {e}", exc_info=True)
        
        logging.debug(f"Main processing loop iteration finished. Sleeping for {config_manager.POLLING_INTERVAL_SECONDS} seconds.")
        await asyncio.sleep(config_manager.POLLING_INTERVAL_SECONDS)

if __name__ == "__main__":
    # Print ASCII Art First
    print(HIPPIUS_ASCII_ART)
    print(f"Hippius IPFS Miner Service - Version: {config_manager.APP_VERSION}\n") # Print version

    # Configure logging first using config_manager
    log_level_str = config_manager.LOG_LEVEL.upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    
    # Install colored C. By default, this will set up a handler on the root logger.
    # You can customize field styles, level styles, etc.
    coloredlogs.install(level=numeric_level, 
                        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(module)s:%(lineno)d)',
                        # Example: custom colors for levels
                        # level_styles={'debug': {'color': 'green'}, 'info': {'color': 'blue'}, ...}
                        )
    
    # logging.basicConfig(level=numeric_level, format='%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s') # Old way

    async def startup():
        global MY_IPFS_NODE_ID
        MY_IPFS_NODE_ID = await get_self_ipfs_node_id()
        if not MY_IPFS_NODE_ID:
            logging.critical("CRITICAL: Could not determine own IPFS Node ID at startup. Service cannot continue.")
            return

        await db_manager.initialize_database()
        logging.info("Database initialized.")

        # --- Aggressive Startup Cleanup & Pinning ---
        logging.info("Starting aggressive IPFS cleanup and initial pin setup...")
        initial_profile_doc_cid = None # Define here to ensure it's in scope for handle_profile_update
        try:
            currently_pinned_on_ipfs = set(await ipfs_utils.list_pinned_cids())
            logging.info(f"Found {len(currently_pinned_on_ipfs)} CIDs currently pinned on IPFS node.")

            initial_profile_doc_cid = await substrate_interface.get_miner_profile_cid(MY_IPFS_NODE_ID)
            
            desired_pins_from_profile = set()
            profile_content_cids = set()

            if initial_profile_doc_cid:
                logging.info(f"Initial profile document CID from chain: {initial_profile_doc_cid}")
                desired_pins_from_profile.add(initial_profile_doc_cid)
                logging.info(f"Attempting to pin initial profile document CID {initial_profile_doc_cid} during startup.")
                if await ipfs_utils.pin_cid(initial_profile_doc_cid):
                    logging.info(f"Successfully pinned initial profile document CID {initial_profile_doc_cid}.")
                    profile_content = await ipfs_utils.get_json_from_cid(initial_profile_doc_cid)
                    if profile_content and isinstance(profile_content, list):
                        for item in profile_content:
                            if isinstance(item, dict) and 'file_hash' in item:
                                target_cid = decode_profile_file_hash_to_cid(item['file_hash'])
                                if target_cid:
                                    profile_content_cids.add(target_cid)
                        desired_pins_from_profile.update(profile_content_cids)
                        logging.info(f"Found {len(profile_content_cids)} CIDs within the initial profile content.")
                    elif profile_content:
                        logging.warning(f"Initial profile content from {initial_profile_doc_cid} is not a list.")
                    else:
                        logging.warning(f"Failed to fetch or parse initial profile content from {initial_profile_doc_cid}.")
                else:
                    logging.error(f"Failed to pin initial profile document CID {initial_profile_doc_cid} during startup. Content cannot be processed.")
            else:
                logging.warning("No initial profile document CID found on chain for this miner.")

            cids_to_unpin_on_startup = currently_pinned_on_ipfs - desired_pins_from_profile
            if cids_to_unpin_on_startup:
                logging.info(f"Startup: Found {len(cids_to_unpin_on_startup)} CIDs to unpin: {cids_to_unpin_on_startup}")
                for cid_to_unpin in cids_to_unpin_on_startup:
                    logging.info(f"Startup: Aggressively unpinning {cid_to_unpin}")
                    await ipfs_utils.unpin_cid(cid_to_unpin)
            else:
                logging.info("Startup: No CIDs found on IPFS that need immediate unpinning based on initial profile.")

        except Exception as e_cleanup:
            logging.error(f"Error during startup IPFS cleanup: {e_cleanup}", exc_info=True)
        
        logging.info("Processing initial profile with fetch_and_process_profile to set DB state...")
        await fetch_and_process_profile(is_startup=True) # block_hash will be None here

        logging.info("Performing initial IPFS garbage collection...")
        await ipfs_utils.trigger_garbage_collection()
        logging.info("Initial IPFS garbage collection finished.")
        
        # Now that initial state is set up, start the main continuous loop which includes subscription
        await main_loop()

    # Use asyncio.run() for cleaner top-level execution if preferred, or manage loop manually.
    # For Python 3.7+ asyncio.run() is the recommended way to run the top-level entry point.
    try:
        asyncio.run(startup())
    except KeyboardInterrupt:
        logging.info("Miner service shutting down due to KeyboardInterrupt...")
    except Exception as e_global:
        logging.critical(f"Global unhandled exception in miner service: {e_global}", exc_info=True)
    finally:
        logging.info("Miner service shutdown sequence finished.") # Changed from loop.close as asyncio.run handles it. 