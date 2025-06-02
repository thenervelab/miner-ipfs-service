import logging
import requests
import pkg_resources
from config_manager import APP_VERSION

# Configure basic logging for standalone testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def check_for_updates():
    """Check GitHub for newer versions using tags"""
    try:
        # Get all tags (sorted by newest first)
        tags_response = requests.get(
            f"https://api.github.com/repos/thenervelab/thebrain/tags",
            timeout=5
        )
        tags_response.raise_for_status()
        
        tags_data = tags_response.json()
        if not tags_data:
            logging.info("No tags found in repository - cannot check versions")
            return False
            
        latest_tag = tags_data[0]['name']  # Gets newest tag
        current_version = pkg_resources.parse_version(APP_VERSION)
        latest_version = pkg_resources.parse_version(latest_tag.lstrip('v'))
        
        if latest_version > current_version:
            logging.warning(
                f"NEW VERSION AVAILABLE: {latest_tag} (Current: {APP_VERSION})\n"
                f"Update at: https://github.com/thenervelab/thebrain"
            )
            return True
        elif latest_version == current_version:
            logging.info(f"You're running the latest version: {APP_VERSION}")
        else:
            logging.warning(
                f"Development version detected: {APP_VERSION} "
                f"(Latest stable: {latest_tag})"
            )
            
    except requests.exceptions.RequestException as e:
        logging.debug(f"Network error checking versions: {str(e)}")
    except Exception as e:
        logging.debug(f"Version check failed: {str(e)}", exc_info=True)
    return False