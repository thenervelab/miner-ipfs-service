# Utilities for IPFS operations using aiohttp
import asyncio
import aiohttp  # Changed from ipfshttpclient
import json  # Already imported in previous version for get_json_from_cid
import logging
import os
from .config_manager import IPFS_API_HOST, IPFS_API_PORT

# Construct the base URL for IPFS API calls
IPFS_API_BASE_URL = f"http://{IPFS_API_HOST}:{IPFS_API_PORT}/api/v0"


async def get_ipfs_id() -> dict | None:
    """Fetches the IPFS node's ID and other information.
    Equivalent to `ipfs id` command.
    """
    url = f"{IPFS_API_BASE_URL}/id"
    logging.debug(f"Fetching IPFS ID from: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url
            ) as response:  # IPFS /id endpoint often uses POST
                response.raise_for_status()  # Raise an exception for HTTP error codes
                data = await response.json()
                logging.debug(f"Successfully fetched IPFS ID: {data.get('ID')}")
                return data
    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error while fetching IPFS ID: {e.status} {e.message}")
        # Try to get more details from response if it's an IPFS error JSON
        try:
            error_data = await e.response.json()
            logging.error(f"IPFS API Error: {error_data}")
        except Exception:
            pass  # Ignore if response is not JSON or already handled
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error while fetching IPFS ID: {e}")
    except asyncio.TimeoutError:
        logging.error(f"Timeout while fetching IPFS ID from {url}")
    except Exception as e:
        logging.error(f"Unexpected error fetching IPFS ID: {e}", exc_info=True)
    return None


async def pin_cid(cid: str, timeout_seconds: int = 60) -> bool:
    """Pins a CID to the local IPFS node using aiohttp.
    Args:
        cid: The CID string to pin.
        timeout_seconds: Timeout for the API call.
    Returns:
        True if pinning was successful or CID was already pinned, False otherwise.
    """
    url = f"{IPFS_API_BASE_URL}/pin/add"
    params = {"arg": cid, "recursive": "true", "progress": "false"}
    logging.info(f"Attempting to pin CID: {cid} via {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    # Successful pin usually returns a list of pins added, e.g. {"Pins": ["<cid>"]}
                    # Or if already pinned, it might also return 200 OK with the CID.
                    # We'll check if the response indicates success.
                    data = await response.json()
                    logging.info(f"Successfully pinned CID: {cid}. Response: {data}")
                    # Ensure the pinned CID is in the response if structure is known
                    # For now, status 200 is treated as success for pinning.
                    return True
                else:
                    # Check for IPFS-specific error messages in JSON response
                    error_text = await response.text()
                    try:
                        error_json = json.loads(error_text)
                        if (
                            "Message" in error_json
                            and "already pinned" in error_json["Message"].lower()
                        ):
                            logging.info(f"CID {cid} is already pinned.")
                            return True
                        logging.error(
                            f"IPFS API error while pinning {cid} (Status {response.status}): {error_json}"
                        )
                    except json.JSONDecodeError:
                        logging.error(
                            f"Non-JSON error response while pinning {cid} (Status {response.status}): {error_text}"
                        )
                    return False
    except aiohttp.ClientResponseError as e:
        logging.error(
            f"HTTP error while pinning {cid}: Status {e.status}, Message {e.message}"
        )
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error while pinning CID {cid}: {e}")
    except asyncio.TimeoutError:
        logging.error(f"Timeout while pinning CID {cid} after {timeout_seconds}s.")
    except Exception as e:
        logging.error(f"Unexpected error while pinning CID {cid}: {e}", exc_info=True)
    return False


async def unpin_cid(cid: str, timeout_seconds: int = 60) -> bool:
    """Unpins a CID from the local IPFS node using aiohttp.
    Args:
        cid: The CID string to unpin.
        timeout_seconds: Timeout for the API call.
    Returns:
        True if unpinning was successful or CID was not pinned, False otherwise.
    """
    url = f"{IPFS_API_BASE_URL}/pin/rm"
    params = {"arg": cid, "recursive": "true"}
    logging.info(f"Attempting to unpin CID: {cid} via {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logging.info(f"Successfully unpinned CID: {cid}. Response: {data}")
                    return True
                else:
                    error_text = await response.text()
                    try:
                        error_json = json.loads(error_text)
                        # Common error messages for "not pinned"
                        msg = error_json.get("Message", "").lower()
                        if "not pinned" in msg or "is not pinned" in msg:
                            logging.info(
                                f"CID {cid} was not pinned or already unpinned."
                            )
                            return True
                        logging.error(
                            f"IPFS API error while unpinning {cid} (Status {response.status}): {error_json}"
                        )
                    except json.JSONDecodeError:
                        logging.error(
                            f"Non-JSON error response while unpinning {cid} (Status {response.status}): {error_text}"
                        )
                    return False
    except aiohttp.ClientResponseError as e:
        logging.error(
            f"HTTP error while unpinning {cid}: Status {e.status}, Message {e.message}"
        )
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error while unpinning CID {cid}: {e}")
    except asyncio.TimeoutError:
        logging.error(f"Timeout while unpinning CID {cid} after {timeout_seconds}s.")
    except Exception as e:
        logging.error(f"Unexpected error while unpinning CID {cid}: {e}", exc_info=True)
    return False


async def is_cid_pinned(cid: str, timeout_seconds: int = 10) -> bool:
    """Checks if a CID is pinned locally using aiohttp.
    The /api/v0/pin/ls?arg=<cid> endpoint returns a list of matching pins.
    If the CID is pinned, it will be in the 'Keys' of the response.
    If not pinned, it usually returns an error or an empty list/different structure depending on IPFS version.
    We expect a 200 OK with the CID if directly pinned.
    An error (like 500 with "not pinned") means it's not pinned.
    Args:
        cid: The CID string to check.
        timeout_seconds: Timeout for the API call.
    Returns:
        True if the CID is pinned, False otherwise.
    """
    url = f"{IPFS_API_BASE_URL}/pin/ls"
    # For a specific CID, type=recursive is usually implied or a good default to check.
    # Some versions of IPFS might be strict about the types: 'direct', 'indirect', 'recursive', 'all'
    params = {"arg": cid, "type": "all"}  # Check all pin types for this CID
    logging.debug(f"Checking if CID {cid} is pinned via {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Successful response for a pinned CID typically looks like:
                    # {"Keys": {"<cid>": {"Type": "recursive"}}}
                    # If "Keys" is empty or CID not in Keys, it's effectively not pinned directly.
                    if "Keys" in data and cid in data["Keys"]:
                        logging.debug(
                            f"CID {cid} is pinned. Details: {data['Keys'][cid]}"
                        )
                        return True
                    else:
                        # The command might return 200 OK with an empty Keys object if no specific pin matches.
                        logging.debug(
                            f"CID {cid} not found in 'Keys' of pin/ls response. Data: {data}"
                        )
                        return False
                else:
                    # Handle non-200 responses. Some IPFS versions might return 500 for "not pinned".
                    error_text = await response.text()
                    try:
                        error_json = json.loads(error_text)
                        msg = error_json.get("Message", "").lower()
                        if (
                            "not pinned" in msg
                            or "no pin for" in msg
                            or "path is not pinned" in msg
                        ):
                            logging.debug(
                                f"CID {cid} is not pinned (API error message). Error: {error_json}"
                            )
                            return False
                        logging.warning(
                            f"IPFS API error checking pin status for {cid} (Status {response.status}): {error_json}"
                        )
                    except json.JSONDecodeError:
                        logging.warning(
                            f"Non-JSON error response checking pin status for {cid} (Status {response.status}): {error_text}"
                        )
                    return False  # Assume not pinned if error or unexpected 200 response structure

    except aiohttp.ClientResponseError as e:
        # A ClientResponseError (like 500) with "not pinned" message is a common way IPFS signals not pinned.
        error_text_body = ""
        try:
            error_text_body = await e.response.text()  # type: ignore
            error_json = json.loads(error_text_body)
            msg = error_json.get("Message", "").lower()
            if (
                "not pinned" in msg
                or "no pin for" in msg
                or "path is not pinned" in msg
            ):
                logging.debug(
                    f"CID {cid} is not pinned (HTTP {e.status} with specific message). Error: {error_json}"
                )
                return False
        except Exception:
            pass
        logging.warning(
            f"HTTP error while checking pin status for {cid}: Status {e.status}, Message {e.message}. Body: {error_text_body[:200]}"
        )
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error while checking pin status for CID {cid}: {e}")
    except asyncio.TimeoutError:
        logging.error(
            f"Timeout while checking pin status for CID {cid} after {timeout_seconds}s."
        )
    except Exception as e:
        logging.error(
            f"Unexpected error checking pin status for CID {cid}: {e}", exc_info=True
        )
    return False  # Default to false on errors


async def list_pinned_cids(timeout_seconds: int = 30) -> list[str]:
    """Lists all CIDs pinned (recursively) on the local IPFS node using aiohttp.
    Returns:
        A list of pinned CID strings. Returns an empty list on error.
    """
    url = f"{IPFS_API_BASE_URL}/pin/ls"
    # type=recursive is important to list all items that keep data locally
    params = {"type": "recursive"}
    logging.debug(f"Listing all recursively pinned CIDs from {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, params=params
            ) as response:  # pin/ls often uses POST
                response.raise_for_status()
                data = await response.json()
                if "Keys" in data and isinstance(data["Keys"], dict):
                    pinned_list = list(data["Keys"].keys())
                    logging.debug(f"Found {len(pinned_list)} recursively pinned CIDs.")
                    return pinned_list
                elif not data:  # Handles empty JSON object {} case for no pins
                    logging.debug("pin/ls response is empty, indicating no pins.")
                    return []
                else:
                    logging.warning(
                        f"Unexpected structure in pin/ls response (expected 'Keys' dict or empty dict): {data}"
                    )
                    return []
    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error while listing pinned CIDs: {e.status} {e.message}")
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error while listing pinned CIDs: {e}")
    except asyncio.TimeoutError:
        logging.error(f"Timeout while listing pinned CIDs after {timeout_seconds}s.")
    except Exception as e:
        logging.error(f"Unexpected error while listing pinned CIDs: {e}", exc_info=True)
    return []


async def get_json_from_cid(
    cid: str, timeout_seconds: int = 30, max_size_bytes: int = 2 * 1024 * 1024
) -> dict | list | None:
    """Fetches content from an IPFS CID and parses it as JSON using aiohttp.
    Args:
        cid: The IPFS CID string to fetch.
        timeout_seconds: Timeout for the API call.
        max_size_bytes: Maximum content size to download to prevent memory issues.
    Returns:
        A dictionary or list if JSON parsing is successful, None otherwise.
    """
    url = f"{IPFS_API_BASE_URL}/cat"
    params = {"arg": cid}
    logging.debug(f"Attempting to fetch and parse JSON from CID: {cid} via {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params) as response:  # cat uses POST
                response.raise_for_status()  # Will raise for 4xx/5xx errors

                content_bytes = b""
                current_size = 0
                # Manually stream the response to check size
                async for chunk in response.content.iter_chunked(
                    1024
                ):  # Read in 1KB chunks
                    current_size += len(chunk)
                    if current_size > max_size_bytes:
                        logging.error(
                            f"Content from CID {cid} exceeds max size of {max_size_bytes} bytes. Aborting download."
                        )
                        await response.release()  # Important to release connection resources
                        return None
                    content_bytes += chunk

                if not content_bytes:
                    logging.warning(f"No content found for CID: {cid}")
                    return None

                try:
                    json_data = json.loads(content_bytes.decode("utf-8"))
                    logging.debug(f"Successfully parsed JSON from CID: {cid}")
                    return json_data
                except json.JSONDecodeError as e_json:
                    logging.error(
                        f"Failed to decode JSON from CID {cid}. Error: {e_json}. Content (first 100 bytes): {content_bytes[:100]}..."
                    )
                    return None
                except UnicodeDecodeError as e_unicode:
                    logging.error(
                        f"Failed to decode content as UTF-8 from CID {cid}. Error: {e_unicode}. Content (first 100 bytes): {content_bytes[:100]}..."
                    )
                    return None

    except aiohttp.ClientResponseError as e_http:
        if e_http.status == 404 or (
            e_http.status == 500
            and (
                "not found" in str(e_http.message).lower()
                or "failed to get block" in str(e_http.message).lower()
            )
        ):
            logging.warning(
                f"CID {cid} not found or unavailable on IPFS node: {e_http.status} {e_http.message}"
            )
        else:
            logging.error(
                f"HTTP error while fetching CID {cid}: {e_http.status} {e_http.message}"
            )
    except aiohttp.ClientConnectionError as e_conn:
        logging.error(f"Connection error while fetching JSON from CID {cid}: {e_conn}")
    except asyncio.TimeoutError:
        logging.error(
            f"Timeout while fetching JSON from CID {cid} after {timeout_seconds}s."
        )
    except Exception as e_exc:
        logging.error(
            f"Unexpected error while fetching JSON from CID {cid}: {e_exc}",
            exc_info=True,
        )
    return None


async def trigger_garbage_collection(timeout_seconds: int = 300) -> list[dict] | None:
    """Triggers IPFS repository garbage collection using aiohttp.
    The /api/v0/repo/gc endpoint streams JSON objects.
    Args:
        timeout_seconds: Total timeout for the entire GC operation.
    Returns:
        A list of response objects from the IPFS daemon, or None if an error occurred.
    """
    url = f"{IPFS_API_BASE_URL}/repo/gc"
    logging.info(f"Attempting to trigger IPFS garbage collection via {url}")

    gc_responses = []
    try:
        # Use a longer timeout for GC as it can take time
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # The stream=True parameter for the request is not directly available in client.post like in `requests`.
            # Instead, we process the response content as a stream.
            async with session.post(url) as response:  # repo/gc uses POST
                response.raise_for_status()  # Check for initial HTTP errors

                # IPFS repo/gc streams newline-delimited JSON objects.
                # We need to read the stream line by line (or by object).
                # aiohttp's response.content is an StreamReader.
                buffer = b""
                async for (
                    line_bytes
                ) in (
                    response.content
                ):  # iter_any() might be too coarse, iter_chunked or readline
                    buffer += line_bytes
                    # Try to decode buffered lines, as JSON objects are newline-delimited
                    while b"\n" in buffer:
                        json_line, buffer = buffer.split(b"\n", 1)
                        if json_line.strip():  # Ensure it's not an empty line
                            try:
                                gc_event = json.loads(json_line.decode("utf-8"))
                                gc_responses.append(gc_event)
                                logging.debug(f"GC progress: {gc_event}")
                                if (
                                    isinstance(gc_event, dict)
                                    and "Error" in gc_event
                                    and gc_event["Error"]
                                ):
                                    logging.error(
                                        f"IPFS GC event reported an error: {gc_event['Error']}"
                                    )
                            except json.JSONDecodeError as e:
                                logging.warning(
                                    f"Could not decode GC event line as JSON: {json_line.decode('utf-8', errors='ignore')}. Error: {e}"
                                )

                # Process any remaining data in the buffer after the loop
                if buffer.strip():
                    try:
                        gc_event = json.loads(buffer.decode("utf-8"))
                        gc_responses.append(gc_event)
                        logging.debug(f"GC progress (final buffer): {gc_event}")
                        if (
                            isinstance(gc_event, dict)
                            and "Error" in gc_event
                            and gc_event["Error"]
                        ):
                            logging.error(
                                f"IPFS GC event (final buffer) reported an error: {gc_event['Error']}"
                            )
                    except json.JSONDecodeError as e:
                        logging.warning(
                            f"Could not decode final GC event buffer as JSON: {buffer.decode('utf-8', errors='ignore')}. Error: {e}"
                        )

            logging.info(
                f"IPFS garbage collection completed. {len(gc_responses)} events received."
            )
            return gc_responses

    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error during garbage collection: {e.status} {e.message}")
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error during garbage collection: {e}")
    except asyncio.TimeoutError:
        logging.error(f"Timeout during garbage collection after {timeout_seconds}s.")
    except Exception as e:
        logging.error(
            f"Unexpected error during IPFS garbage collection: {e}", exc_info=True
        )
    return None


# Example usage (for testing this module directly)
async def main_test():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
    )

    node_id_info = await get_ipfs_id()
    if node_id_info and "ID" in node_id_info:
        logging.info(f"Connected to IPFS node: {node_id_info['ID']}")
    else:
        logging.error(
            "Could not connect to IPFS for testing. Ensure IPFS daemon is running."
        )
        return

    # Create a dummy file and add it to IPFS to get a CID (manual step for now or use existing CID)
    # For aiohttp, adding files requires constructing multipart/form-data requests.
    # Let's use a known public CID for pinning tests for simplicity with aiohttp.
    test_cid = "QmbWqxBEKC3P8tqsKc98xmWNzrzDtRLMiMPL8wBuTGsMnR"  # Example: IPFS logo
    # Alternatively, add a file using `ipfs add <file>` on CLI and use that CID.

    logging.info(f"--- Testing pin_cid for {test_cid} ---")
    pin_success = await pin_cid(test_cid)
    logging.info(f"Pinning {test_cid} successful: {pin_success}")

    # More tests will be added as other functions are refactored.
    logging.info("IPFS utils (aiohttp) partial test finished.")


if __name__ == "__main__":
    asyncio.run(main_test())
