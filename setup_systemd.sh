#!/bin/bash

# Script to set up the Hippius IPFS Miner service with systemd

# --- Configuration - Please review and modify if needed --- 
SERVICE_NAME="hippius-miner"
SERVICE_DESCRIPTION="Hippius IPFS Miner Service"
# Consider creating a dedicated user for the service if not running as current user
# Defaulting to 'ubuntu' for now, common on Ubuntu servers.
# If your project files are owned by a different user, change this.
SERVICE_USER="ubuntu"

# --- End Configuration ---

echo "Hippius IPFS Miner Systemd Setup"
echo "----------------------------------"

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
  echo "This script needs to be run as root (or with sudo) to install systemd service files."
  exit 1
fi

# Get project directory
read -erp "Enter the absolute path to your project directory (e.g., /home/ubuntu/miner-ipfs-service): " PROJECT_DIR
if [ ! -d "${PROJECT_DIR}" ]; then
    echo "Error: Project directory '${PROJECT_DIR}' not found."
    exit 1
fi

# Validate essential files exist
if [ ! -f "${PROJECT_DIR}/miner_service.py" ] || [ ! -f "${PROJECT_DIR}/requirements.txt" ] || [ ! -f "${PROJECT_DIR}/config.ini" ]; then
    echo "Error: Essential project files (miner_service.py, requirements.txt, config.ini) not found in '${PROJECT_DIR}'."
    exit 1
fi

# Get Python interpreter path from venv
DEFAULT_PYTHON_EXEC="${PROJECT_DIR}/venv/bin/python3"
read -erp "Enter the absolute path to the Python interpreter in your venv (default: ${DEFAULT_PYTHON_EXEC}): " PYTHON_EXEC
PYTHON_EXEC=${PYTHON_EXEC:-$DEFAULT_PYTHON_EXEC}

if [ ! -f "${PYTHON_EXEC}" ]; then
    echo "Error: Python interpreter '${PYTHON_EXEC}' not found."
    echo "Please ensure you have created a virtual environment and it contains python3."
    exit 1
fi

# Get service user if different from default
read -erp "Enter the username to run the service as (default: ${SERVICE_USER}): " INPUT_SERVICE_USER
SERVICE_USER=${INPUT_SERVICE_USER:-$SERVICE_USER}

# Check if user exists
if ! id "${SERVICE_USER}" &>/dev/null; then
    echo "Error: User '${SERVICE_USER}' does not exist. Please create the user or choose an existing one."
    exit 1
fi

# Create systemd service file content
SERVICE_FILE_CONTENT="[Unit]
Description=${SERVICE_DESCRIPTION}
After=network.target

[Service]
User=${SERVICE_USER}
Group=$(id -gn ${SERVICE_USER})

WorkingDirectory=${PROJECT_DIR}

# Ensure the Python interpreter and script path are correct
ExecStart=${PYTHON_EXEC} ${PROJECT_DIR}/miner_service.py

# Restart policy
Restart=on-failure
RestartSec=5s

# Logging to journald (standard for systemd)
StandardOutput=journal
StandardError=journal

# Optional: Set environment variables if needed (e.g., for config overrides)
# Environment=\"PYTHONUNBUFFERED=1\"
# Environment=\"SUBSTRATE_NODE_URL=ws://127.0.0.1:9944\"

[Install]
WantedBy=multi-user.target
"

# Systemd service file path
SERVICE_FILE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo ""
echo "The following systemd service file will be created at ${SERVICE_FILE_PATH}:"
echo "----------------------------------------------------------------------"
echo "${SERVICE_FILE_CONTENT}"
echo "----------------------------------------------------------------------"

read -rp "Do you want to proceed with creating this service file? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Setup aborted by user."
    exit 0
fi

# Write the service file
echo "Creating systemd service file..."
echo "${SERVICE_FILE_CONTENT}" > "${SERVICE_FILE_PATH}"
if [ $? -ne 0 ]; then
    echo "Error: Failed to write service file. Check permissions or path."
    exit 1
fi

# Set permissions for the service file (optional, usually root ownership is fine)
chmod 644 "${SERVICE_FILE_PATH}"

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload
if [ $? -ne 0 ]; then
    echo "Error: Failed to reload systemd daemon."
    # Attempt to show journal for systemd errors if possible
    journalctl -u systemd -n 5 --no-pager
    exit 1
fi

# Enable the service to start on boot
echo "Enabling service ${SERVICE_NAME} to start on boot..."
systemctl enable ${SERVICE_NAME}.service
if [ $? -ne 0 ]; then
    echo "Error: Failed to enable service."
    exit 1
fi

echo ""
echo "Service ${SERVICE_NAME} has been created and enabled."
echo ""
echo "To start the service now, run:"
echo "  sudo systemctl start ${SERVICE_NAME}.service"
echo ""
echo "To check the status of the service, run:"
echo "  sudo systemctl status ${SERVICE_NAME}.service"
echo ""
echo "To view the logs (output from the service), run:"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "To stop the service, run:"
echo "  sudo systemctl stop ${SERVICE_NAME}.service"
echo ""
echo "To disable the service from starting on boot, run:"
echo "  sudo systemctl disable ${SERVICE_NAME}.service"
echo ""
echo "Setup complete."

exit 0 