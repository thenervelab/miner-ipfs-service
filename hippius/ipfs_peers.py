import asyncio
import aiohttp
from substrateinterface import SubstrateInterface
from substrateinterface.exceptions import SubstrateRequestException
import logging


class PeersConnector:
    def __init__(
        self,
        ws_url,
        block_interval=20,
        batch_size=10,
        batch_interval=2,
        connect_timeout=10,
    ):
        """
        Initialize the PeersConnector.

        Args:
            ws_url (str): WebSocket URL of the Substrate node
            block_interval (int): Number of blocks between queries
            batch_size (int): Number of peers to process in one batch
            batch_interval (int): Seconds to wait between batches
            connect_timeout (int): Timeout in seconds for connecting to a peer
        """
        self.ws_url = ws_url
        self.block_interval = block_interval
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.connect_timeout = connect_timeout
        self.substrate = None
        self.last_processed_block = None
        self.ipfs_api_url = "http://127.0.0.1:5001"

    async def connect(self):
        """Establish connection to the Substrate node with retries."""
        while True:
            try:
                logging.info("Connecting...")
                self.substrate = await asyncio.to_thread(
                    SubstrateInterface, url=self.ws_url
                )
                logging.info(f"Connected to Substrate node at {self.ws_url}")
                return  # Exit the loop on success
            except (
                ConnectionRefusedError,
                SubstrateRequestException,
                BrokenPipeError,
            ) as e:
                logging.info(f"Connection attempt failed: {e}")
                await asyncio.sleep(5)  # Wait 5 seconds before retrying
            except Exception as e:
                logging.info(f"Unexpected error: {e}")
                await asyncio.sleep(5)  # Wait 5 seconds before retrying

    async def query_storage_map(self, block_hash, pallet, storage_function):
        """
        Query a storage map from a pallet at a specific block hash.

        Args:
            block_hash (str): Block hash to query
            pallet (str): Pallet name
            storage_function (str): Storage function name

        Returns:
            list: List of (key, value) tuples with decoded storage data
        """
        try:
            query_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.substrate.query_map(
                    module=pallet,
                    storage_function=storage_function,
                    block_hash=block_hash,
                ),
            )
            result = []
            for key, value in query_result:
                key_decoded = key.value  # Vec<u8> as bytes
                value_decoded = value.value  # NodeInfo as dict
                result.append((key_decoded, value_decoded))
            return result
        except SubstrateRequestException as e:
            logging.info(f"Error querying {pallet}.{storage_function}: {e}")
            return []

    async def add_peers(self, session, peer_id):
        """
        Connects to a peer using the local IPFS node API with a timeout.

        Args:
            session (aiohttp.ClientSession): Session for making HTTP requests
            peer_id (str): The peer ID to connect to

        Returns:
            dict: Structured result with status, message, and raw response if applicable
        """
        connect_url = f"{self.ipfs_api_url}/api/v0/swarm/connect"
        params = {"arg": f"/p2p/{peer_id}"}
        
        try:
            async with session.post(
                connect_url, params=params, timeout=self.connect_timeout
            ) as response:
                result = await response.json()

                # Handle remote-side error (issue with the peer or IPFS network, not the user's setup)
                if "error" in result:
                    return {
                        "status": "remote_error",
                        "peer": peer_id,
                        "message": (
                            "We couldn't connect to this peer because of an issue on their end or the IPFS network. "
                            f"→ Details: {result.get('error', 'Unknown issue with the peer')}"
                        ),
                        "raw": result,
                    }

                # Success
                return {
                    "status": "success",
                    "peer": peer_id,
                    "message": "Connected to the peer successfully!",
                    "raw": result,
                }

        except asyncio.TimeoutError:
            # Timeout (peer is not responding)
            return {
                "status": "timeout",
                "peer": peer_id,
                "message": (
                    f"tried to connect to the peer, but it didn't respond within {self.connect_timeout} seconds. "
                    "This usually means the peer is offline or not reachable right now. "
                ),
            }

        except Exception as e:
            # Local issues (network problems on the user's side)
            return {
                "status": "exception",
                "peer": peer_id,
                "message": (
                    "Something went wrong while trying to connect to this peer. "
                    "This might be due to your internet connection being down or unstable. "
                    f"→ Details: {str(e)}"
                ),
            }

    async def process_peers_in_batches(self, peer_ids):
        """
        Process peers in batches with a sleep interval between batches.

        Args:
            peer_ids (list): List of peer IDs to process
        """
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(peer_ids), self.batch_size):
                batch = peer_ids[i : i + self.batch_size]
                logging.info(f"Processing batch of {len(batch)} peers")

                tasks = [self.add_peers(session, peer_id) for peer_id in batch]
                results = await asyncio.gather(*tasks)

                for result in results:
                    status = result.get("status")
                    peer = result.get("peer")
                    message = result.get("message")

                    if status == "success":
                        logging.info(f"[✓] Connected to {peer}: {message}")
                    else:
                        logging.warning(f"[x] Failed to connect to {peer}: {message}")

                if i + self.batch_size < len(peer_ids):
                    logging.info(
                        f"Waiting {self.batch_interval} seconds before next batch"
                    )
                    await asyncio.sleep(self.batch_interval)

    async def process_block(self, block_number, block_hash):
        """
        Process storage items for a given block, collect IPFS node IDs, and add them as peers.

        Args:
            block_number (int): Block number
            block_hash (str): Block hash
        """
        logging.info(f"Processing block {block_number} ({block_hash})")

        # Query ColdkeyNodeRegistration
        coldkey_nodes = await self.query_storage_map(
            block_hash, "Registration", "ColdkeyNodeRegistration"
        )
        logging.info(f"ColdkeyNodeRegistration entries: {len(coldkey_nodes)}")

        # Query NodeRegistration
        node_registrations = await self.query_storage_map(
            block_hash, "Registration", "NodeRegistration"
        )
        logging.info(f"NodeRegistration entries: {len(node_registrations)}")

        # Collect all IPFS node IDs into a set to remove duplicates
        ipfs_node_ids = set()
        for _, node_info in coldkey_nodes + node_registrations:
            if (
                node_info
                and "ipfs_node_id" in node_info
                and node_info["ipfs_node_id"] is not None
            ):
                ipfs_node_id_str = node_info["ipfs_node_id"]
                logging.info(
                    "ipfs_node_id_str: %s", ipfs_node_id_str
                )  # Proper string formatting
                ipfs_node_ids.add(ipfs_node_id_str)

        # logging.info the IPFS node IDs and process them in batches
        if ipfs_node_ids:
            logging.info(f"IPFS Node IDs at block {block_number}:")
            for idx, node_id in enumerate(ipfs_node_ids, 1):
                logging.info(f"{idx}. {node_id}")
            await self.process_peers_in_batches(list(ipfs_node_ids))
        else:
            logging.info("No IPFS Node IDs found")

    async def run(self):
        """Main loop to monitor blocks and query storage at intervals."""
        await self.connect()

        while True:
            try:
                # Get current block
                current_block = self.substrate.get_block()
                current_block_number = current_block["header"]["number"]
                current_block_hash = self.substrate.get_block_hash(current_block_number)
                logging.info(
                    "current_block_hash: %s", current_block_hash
                )  # Proper string formatting
                # Initialize last_processed_block to the nearest previous interval
                if self.last_processed_block is None:
                    self.last_processed_block = current_block_number - (
                        current_block_number % self.block_interval
                    )

                # Check if it's time to process a new block
                if (
                    current_block_number
                    >= self.last_processed_block + self.block_interval
                ):
                    target_block = self.last_processed_block + self.block_interval
                    target_block_hash = self.substrate.get_block_hash(target_block)

                    if target_block_hash:
                        logging.info("processing block....")
                        await self.process_block(target_block, target_block_hash)
                        self.last_processed_block = target_block
                    else:
                        logging.info(f"Could not get hash for block {target_block}")

                await asyncio.sleep(6)  # Wait approximately one block time (6 seconds)

            except BrokenPipeError as e:
                logging.info(
                    f"Broken pipe error in PeersConnector run: {e}. Reconnecting..."
                )
                await self.connect()  # Reconnect to the Substrate node
            except Exception as e:
                logging.info(f"Error in main loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying


async def main():
    """Entry point for the application."""
    ws_url = "ws://127.0.0.1:9944"
    peer_connector = PeersConnector(
        ws_url, block_interval=20, batch_size=10, batch_interval=2, connect_timeout=10
    )
    await peer_connector.run()


if __name__ == "__main__":
    asyncio.run(main())
