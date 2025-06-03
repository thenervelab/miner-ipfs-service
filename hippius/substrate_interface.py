# Functions for interacting with the Substrate chain
import logging
from substrateinterface import SubstrateInterface, Keypair
from substrateinterface.exceptions import SubstrateRequestException
import os
import binascii
from .config_manager import SUBSTRATE_NODE_URL
import asyncio
import time

# Configuration
# SUBSTRATE_NODE_URL_DEV = "wss://rpc.hippius.network" # Old way
# SUBSTRATE_NODE_URL_PROD = "ws://127.0.0.1:9944" # Old way

# Determine which URL to use (e.g., via an environment variable or a config file)
# For now, let's default to dev and allow override via ENV
# SUBSTRATE_URL = os.environ.get("SUBSTRATE_NODE_URL", SUBSTRATE_NODE_URL_DEV) # Old way
# Use the value directly from config_manager
# SUBSTRATE_URL = SUBSTRATE_NODE_URL # This line is redundant as SUBSTRATE_NODE_URL is already the correct value


def get_substrate_connection() -> SubstrateInterface | None:
    """Establishes and returns a verified connection to the Substrate node with infinite retries.

    Retries every 5 seconds on failure until a successful connection is verified by querying the chain head.

    Returns:
        SubstrateInterface | None: A verified SubstrateInterface instance or None if connection cannot be verified.
    """
    substrate = None
    attempt = 1

    while True:
        try:
            logging.info(
                f"Attempt {attempt} to connect to Substrate node at {SUBSTRATE_NODE_URL}..."
            )
            substrate = SubstrateInterface(url=SUBSTRATE_NODE_URL)
            # Verify connection by attempting a simple query
            substrate.get_chain_head()
            logging.info(
                f"Successfully connected to {SUBSTRATE_NODE_URL} and verified with chain head query."
            )
            return substrate

        except (
            ConnectionRefusedError,
            SubstrateRequestException,
            BrokenPipeError,
        ) as e:
            logging.error(
                f"Connection error when connecting to Substrate node at {SUBSTRATE_NODE_URL} on attempt {attempt}: {e}"
            )
        except Exception as e:
            logging.error(
                f"General error creating or verifying SubstrateInterface for {SUBSTRATE_NODE_URL} on attempt {attempt}: {e}",
                exc_info=True,
            )

        # Clean up if substrate object was partially created
        if substrate:
            try:
                substrate.close()
            except:
                pass
            substrate = None

        logging.info("Waiting 5 seconds before retrying...")
        time.sleep(5)
        attempt += 1


def decode_hex_bytes_to_cid_string(hex_bytes_value: str) -> str | None:
    """Decodes a hex string (potentially '0x' prefixed) from the chain.
    Assumes the hex string is the hexadecimal representation of the UTF-8 encoded CID string.
    Also handles cases where the value is already a CID.
    """
    if not hex_bytes_value:
        logging.warning("Received empty hex_bytes_value for decoding.")
        return None

    # First check if the input is already a valid CID format
    if (
        (hex_bytes_value.startswith("Qm") and len(hex_bytes_value) == 46)
        or (hex_bytes_value.startswith("bafy") and len(hex_bytes_value) > 50)
        or (hex_bytes_value.startswith("bafk") and len(hex_bytes_value) > 50)
        or (hex_bytes_value.startswith("k") and len(hex_bytes_value) > 50)
    ):
        logging.info(
            f"Input value '{hex_bytes_value}' is already in CID format. Using as is."
        )
        return hex_bytes_value

    cleaned_hex = hex_bytes_value.lower()
    if cleaned_hex.startswith("0x"):
        cleaned_hex = cleaned_hex[2:]

    if not cleaned_hex:
        logging.warning(f"Hex value became empty after cleaning: {hex_bytes_value}")
        return None

    try:
        cid_bytes = binascii.unhexlify(cleaned_hex)
        cid_candidate = cid_bytes.decode("utf-8")
        if (
            (cid_candidate.startswith("Qm") and len(cid_candidate) == 46)
            or (cid_candidate.startswith("bafy") and len(cid_candidate) > 50)
            or (cid_candidate.startswith("bafk") and len(cid_candidate) > 50)
            or (cid_candidate.startswith("k") and len(cid_candidate) > 50)
        ):
            logging.debug(
                f"Successfully decoded hex '{hex_bytes_value}' to CID string: '{cid_candidate}'"
            )
            return cid_candidate
        else:
            logging.warning(
                f"Decoded string '{cid_candidate}' from hex '{hex_bytes_value}' does not look like a standard IPFS CID. Using it as is."
            )
            return cid_candidate

    except (binascii.Error, UnicodeDecodeError):
        is_likely_hex = all(c in "0123456789abcdefABCDEF" for c in cleaned_hex)
        if is_likely_hex and (
            cleaned_hex.lower().startswith("f0")
            or cleaned_hex.lower().startswith("01")
            or len(cleaned_hex) > 40
        ):
            logging.warning(
                f"Could not decode hex '{cleaned_hex}' as UTF-8. Assuming it is a direct base16 CID or similar."
            )
            return cleaned_hex
        elif (
            (hex_bytes_value.startswith("Qm") and len(hex_bytes_value) == 46)
            or (hex_bytes_value.startswith("bafy") and len(hex_bytes_value) > 50)
            or (hex_bytes_value.startswith("bafk") and len(hex_bytes_value) > 50)
            or (hex_bytes_value.startswith("k") and len(hex_bytes_value) > 50)
        ):
            logging.warning(
                f"Treating input '{hex_bytes_value}' as a direct CID string as hex decoding failed."
            )
            return hex_bytes_value
        logging.error(
            f"Invalid hex string for CID decoding and not a direct CID: '{hex_bytes_value}'."
        )
        return None
    except Exception as e:
        logging.error(
            f"Unexpected error decoding hex '{hex_bytes_value}' to CID string: {e}"
        )
        return None


async def get_miner_profile_cid(ipfs_node_id: str) -> str | None:
    """Queries the Substrate chain for the miner's profile CID."""
    substrate = get_substrate_connection()
    if not substrate:
        return None

    profile_cid_str = None
    try:
        logging.info(
            f"Querying ipfsPallet.MinerProfile for IPFS node ID: {ipfs_node_id}"
        )
        params = [ipfs_node_id]
        result = substrate.query(
            module="IpfsPallet", storage_function="MinerProfile", params=params
        )
        logging.debug(f"Raw result from MinerProfile query: {result}")

        if result is not None and hasattr(result, "value") and result.value is not None:
            hex_encoded_profile_hash = result.value
            logging.info(
                f"Received hex encoded profile hash: {hex_encoded_profile_hash}"
            )
            profile_cid_str = decode_hex_bytes_to_cid_string(hex_encoded_profile_hash)
            if profile_cid_str:
                logging.info(
                    f"Decoded profile CID: {profile_cid_str} for node {ipfs_node_id}"
                )
        else:
            logging.warning(
                f"No profile found or empty result for IPFS node ID: {ipfs_node_id}. Result: {result}"
            )

    except SubstrateRequestException as e:
        logging.error(
            f"Substrate request failed when querying MinerProfile for {ipfs_node_id}: {e}"
        )
    except Exception as e:
        logging.error(
            f"An unexpected error occurred when querying MinerProfile for {ipfs_node_id}: {e}",
            exc_info=True,
        )
    finally:
        if substrate:
            try:
                substrate.close()
            except:
                pass
            logging.debug("Substrate connection closed after query attempt.")

    return profile_cid_str


async def get_substrate_node_id() -> str | None:
    """Fetches the node ID from the Substrate node."""
    substrate = get_substrate_connection()
    if not substrate:
        logging.error("Failed to get substrate connection for fetching node ID.")
        return None

    node_id = None
    try:
        # Query the system for node information using the correct method system_localPeerId
        response = substrate.rpc_request(method="system_localPeerId", params=[])
        if response and "result" in response:
            node_id = response["result"]
            logging.info(f"Successfully fetched Substrate node ID: {node_id}")
            return node_id
        else:
            logging.warning(f"Could not retrieve node ID. Response: {response}")
    except SubstrateRequestException as e:
        logging.error(f"Substrate request failed when fetching node ID: {e}")
    except Exception as e:
        logging.error(
            f"An unexpected error occurred when fetching node ID: {e}", exc_info=True
        )
    finally:
        if substrate:
            try:
                substrate.close()
            except:
                pass
            logging.debug("Substrate connection closed after fetching node ID.")
    return node_id


async def get_current_block_number() -> int | None:
    """Fetches the current (latest) block number of the Substrate chain."""
    substrate = get_substrate_connection()
    if not substrate:
        logging.error("Failed to get substrate connection for fetching block number.")
        return None

    block_number = None
    try:
        # Get the header of the latest block (head)
        # The get_block_header() method returns a dict that includes the 'header' key itself.
        response = substrate.get_block_header()
        if (
            response
            and "header" in response
            and isinstance(response["header"], dict)
            and "number" in response["header"]
        ):
            block_number = response["header"]["number"]
            # The block number might be hex (e.g., '0x...') or int depending on library/node.
            # Ensure it's an int.
            if isinstance(block_number, str) and block_number.startswith("0x"):
                block_number = int(block_number, 16)
            elif not isinstance(block_number, int):
                logging.warning(
                    f"Block number is not in expected int or hex format: {block_number}"
                )
                block_number = None  # Invalid format

            if block_number is not None:
                logging.debug(
                    f"Successfully fetched current block number: {block_number}"
                )
        else:
            logging.warning(
                f"Could not retrieve block number from header structure. Response: {response}"
            )
    except SubstrateRequestException as e:
        logging.error(
            f"Substrate request failed when fetching current block number: {e}"
        )
    except Exception as e:
        logging.error(
            f"An unexpected error occurred when fetching current block number: {e}",
            exc_info=True,
        )
    finally:
        if substrate:
            try:
                substrate.close()
            except:
                pass
            logging.debug("Substrate connection closed after fetching block number.")
    return block_number


# In substrate_interface.py (or wherever substrate_interface is defined)
async def reconnect():
    global substrate
    substrate = None
    while True:
        try:
            substrate = await asyncio.to_thread(
                SubstrateInterface, url="ws://127.0.0.1:9944"
            )
            logging.info("Reconnected to Substrate node.")
            break
        except Exception as e:
            logging.error(f"Reconnection failed: {e}")
            await asyncio.sleep(5)

