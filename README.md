IPFS Miner Service

This service acts as an IPFS miner for the Dubs Subnet. It interacts with a Substrate-based blockchain and a local IPFS node to manage the pinning and unpinning of CIDs based on a miner profile fetched from the chain.

## Features

-   Fetches miner profile CID from the Substrate chain.
-   Downloads and parses the miner profile content (a JSON file) from IPFS.
-   Manages a local list of CIDs to be pinned based on the profile.
-   Pins new CIDs from the profile to the local IPFS node.
-   Unpins CIDs no longer listed in the profile.
-   Retries failed pinning operations up to a configurable limit.
-   Reports CIDs that consistently fail to pin to a local JSON file.
-   Periodically runs IPFS garbage collection.
-   Uses a local SQLite database to track pinning status and miner profile.
-   Configuration via `config.ini` and environment variables.
-   Comprehensive asynchronous logging.

## Prerequisites

1.  **Python**: Python 3.9 or higher is recommended.
2.  **IPFS Daemon**: A local IPFS Kubo daemon must be running and accessible via its HTTP API (default: `127.0.0.1:5001`).
3.  **Substrate Node**: Access to a Substrate node for the Dubs Subnet. The service can be configured to point to a development node (e.g., `wss://rpc.hippius.network`) or a local/production node.

## Setup

1.  **Clone the repository (if applicable)**:
    ```bash
    # git clone <repository_url>
    # cd <repository_directory>
    ```

2.  **Create and activate a virtual environment (recommended)**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The service is configured through a `config.ini` file and can be overridden by environment variables.

**`config.ini` structure:**

```ini
[General]
LOG_LEVEL = INFO

[IPFS]
API_HOST = 127.0.0.1
API_PORT = 5001

[Substrate]
# Default to development node. For production, change this to ws://127.0.0.1:9944
# or use the SUBSTRATE_NODE_URL environment variable.
NODE_URL = wss://rpc.hippius.network

[Database]
NAME = miner_data.db

[MinerService]
POLLING_INTERVAL_SECONDS = 60
MAX_PIN_RETRIES = 5
UNPINNABLE_CIDS_REPORT_FILE = unpinnable_cids_report.json
GC_TRIGGER_INTERVAL_LOOPS = 10
```

**Environment Variable Overrides:**

Each setting in `config.ini` can be overridden by an environment variable. The corresponding environment variable name is usually the uppercase version of the key, prefixed with the section if ambiguous (though the `config_manager.py` defines specific env var names if needed).

Key environment variables (as used by `config_manager.py`):

-   `LOG_LEVEL` (e.g., `DEBUG`, `INFO`, `WARNING`)
-   `IPFS_API_HOST`
-   `IPFS_API_PORT`
-   `SUBSTRATE_NODE_URL`
-   `DATABASE_NAME`
-   `POLLING_INTERVAL_SECONDS`
-   `MAX_PIN_RETRIES`
-   `UNPINNABLE_CIDS_REPORT_FILE`
-   `GC_TRIGGER_INTERVAL_LOOPS`

**Example:** To use a local Substrate node, you could set:
`export SUBSTRATE_NODE_URL="ws://127.0.0.1:9944"`

## Running the Service

Ensure your IPFS daemon is running and the Substrate node is accessible according to your configuration.

To start the miner service:

```bash
python miner_service.py
```

The service will start, initialize its database (e.g., `miner_data.db` will be created), and begin its main operational loop.
Logs will be printed to standard output.

To stop the service, press `Ctrl+C`.

## Modules Overview

-   **`miner_service.py`**: The main application entry point and orchestrator.
-   **`ipfs_utils.py`**: Handles all interactions with the IPFS daemon (pinning, unpinning, fetching content, GC).
-   **`substrate_interface.py`**: Manages communication with the Substrate node (fetching miner profile CID).
-   **`db_manager.py`**: Handles all SQLite database operations for local state persistence.
-   **`config_manager.py`**: Loads and provides access to configuration from `config.ini` and environment variables.
-   **`requirements.txt`**: Lists Python dependencies.
-   **`config.ini`**: Configuration file.
-   **`how_it_works.md`**: Original requirements document.
-   **`profile.json`**: Example structure of a miner's profile document (content fetched from IPFS).

## Development Notes

-   The service relies heavily on `asyncio` for non-blocking operations.
-   The `decode_profile_file_hash_to_cid` in `miner_service.py` and `decode_hex_bytes_to_cid_string` in `substrate_interface.py` handle the conversion of chain/profile data to usable CID strings. Their logic might need adjustment based on the precise data formats encountered on the live Substrate chain and in IPFS profile documents.
-   Ensure the IPFS node ID used to query the `IpfsPallet.MinerProfile` on the Substrate chain is the correct ID of the running IPFS daemon this service is paired with. The service attempts to fetch this automatically. 