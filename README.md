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
-   Ensure the IPFS node ID used to query the `IpfsPallet.MinerProfile` on the Substrate chain is the correct ID of the running IPFS daemon this service is paired with. The service attempts to fetch this automatically.

## Running as a Systemd Service (Linux)

To run the Hippius IPFS Miner as a background service on a Linux system using systemd (common on Ubuntu, Debian, CentOS, etc.), you can use the provided `setup_systemd.sh` script.

**Prerequisites for Systemd Setup:**

1.  All prerequisites from the main [Prerequisites](#prerequisites) section are met.
2.  You have `sudo` access on the machine.
3.  The project files are in their final location on the server.
4.  A Python virtual environment (`venv`) has been created within the project directory and dependencies installed as per the [Setup](#setup) section.

**Steps to Set Up the Service:**

1.  **Navigate to the project directory**:
    ```bash
    cd /path/to/your/miner-ipfs-service
    ```

2.  **Make the setup script executable**:
    ```bash
    chmod +x setup_systemd.sh
    ```

3.  **Run the setup script with sudo**:
    ```bash
    sudo ./setup_systemd.sh
    ```
    The script will prompt you for:
    *   The absolute path to your project directory.
    *   The absolute path to the Python 3 interpreter inside your project's `venv` (e.g., `/path/to/your/miner-ipfs-service/venv/bin/python3`).
    *   The username under which the service should run (defaults to `ubuntu`). Ensure this user has read/write permissions to the project directory, `config.ini`, `miner_data.db`, and `unpinnable_cids_report.json`.

4.  **Confirm the details**: The script will show you the content of the systemd unit file it's about to create. Review it and confirm.

Upon successful completion, the script will:
*   Create a service file (e.g., `/etc/systemd/system/hippius-miner.service`).
*   Reload the systemd daemon.
*   Enable the service to start on boot.

**Managing the Service:**

Once set up, you can manage the service using `systemctl` commands:

*   **Start the service**:
    ```bash
    sudo systemctl start hippius-miner.service
    ```
*   **Check the status**:
    ```bash
    sudo systemctl status hippius-miner.service
    ```
*   **View live logs** (output from the service):
    ```bash
    sudo journalctl -u hippius-miner.service -f
    ```
    To see more historical logs:
    ```bash
    sudo journalctl -u hippius-miner.service --since "1 hour ago"
    sudo journalctl -u hippius-miner.service -n 200 # Last 200 lines
    ```
*   **Stop the service**:
    ```bash
    sudo systemctl stop hippius-miner.service
    ```
*   **Restart the service**:
    ```bash
    sudo systemctl restart hippius-miner.service
    ```
*   **Disable from starting on boot**:
    ```bash
    sudo systemctl disable hippius-miner.service
    ```
*   **Enable to start on boot (if previously disabled)**:
    ```bash
    sudo systemctl enable hippius-miner.service
    ```

**Modifying the Service:**

If you need to change the service configuration (e.g., update the project path or Python interpreter), you should:
1.  Modify the `/etc/systemd/system/hippius-miner.service` file directly (with `sudo`).
2.  Run `sudo systemctl daemon-reload` for changes to take effect.
3.  Restart the service: `sudo systemctl restart hippius-miner.service`.

## Development Notes

-   The service relies heavily on `asyncio` for non-blocking operations.
-   The `decode_profile_file_hash_to_cid` in `miner_service.py` and `decode_hex_bytes_to_cid_string` in `substrate_interface.py` handle the conversion of chain/profile data to usable CID strings. Their logic might need adjustment based on the precise data formats encountered on the live Substrate chain and in IPFS profile documents.

## Versioning

The application version is defined in the `__version__.py` file at the root of the project.

Example: `__version__ = "0.1.0"`

When preparing a new release:

1.  **Update `__version__.py`**: Manually change the `__version__` string to the new version number (e.g., "0.2.0", "1.0.0").
2.  **Commit the change**:
    ```bash
    git add __version__.py
    git commit -m "Bump version to X.Y.Z"
    ```
3.  **Tag the release**:
    ```bash
    git tag vX.Y.Z
    git push origin vX.Y.Z
    ```
    (Also push your main branch changes: `git push origin main`)

**Automating Version Bumping (Recommended for frequent releases):**

For a more automated approach to updating the version string in `__version__.py`, committing, and tagging, consider using a tool like `bump2version` or `bump-my-version`.

**Example using `bump2version`:**

1.  Install `bump2version` (e.g., `pip install bump2version`).
2.  Configure it by creating a `.bumpversion.cfg` file in your project root:
    ```ini
    [bumpversion]
    current_version = 0.1.0
    commit = True
    tag = True

    [bumpversion:file:__version__.py]
    search = __version__ = "{current_version}"
    replace = __version__ = "{new_version}"
    ```
    (Ensure `current_version` in `.bumpversion.cfg` matches `__version__.py` initially.)

3.  To bump the version (e.g., patch, minor, major):
    ```bash
    bump2version patch  # e.g., 0.1.0 -> 0.1.1
    # bump2version minor
    # bump2version major
    ```
    This will update `__version__.py`, create a commit, and create a tag.
4.  Push changes and tags:
    ```bash
    git push --follow-tags
    ```
This strategy helps keep versioning consistent and tied to your Git history. 