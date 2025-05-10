import configparser
import os
import logging

CONFIG_FILE_PATH = 'config.ini'

class ConfigManager:
    def __init__(self, config_file=CONFIG_FILE_PATH):
        self.parser = configparser.ConfigParser()
        if not os.path.exists(config_file):
            logging.warning(f"Config file '{config_file}' not found. Using default values and environment variables where possible.")
            # Create a dummy parser if file not found, so sections exist for env var overrides
            self._create_default_sections_for_env_override()
        else:
            try:
                self.parser.read(config_file)
            except configparser.Error as e:
                logging.error(f"Error reading config file '{config_file}': {e}. Using defaults/env vars.")
                self._create_default_sections_for_env_override()

    def _create_default_sections_for_env_override(self):
        """Ensures sections exist in the parser even if the file is missing, for env var lookups."""
        sections = ['General', 'IPFS', 'Substrate', 'Database', 'MinerService']
        for section in sections:
            if not self.parser.has_section(section):
                self.parser.add_section(section)

    def get(self, section, key, default=None, is_int=False, is_bool=False, env_var=None):
        """Fetches a config value, checking environment variables first, then config file, then default."""
        # 1. Check environment variable
        if env_var:
            value = os.environ.get(env_var)
            if value is not None:
                if is_int:
                    try: return int(value)
                    except ValueError: logging.warning(f"Env var {env_var}={value} is not a valid int. Ignoring.")
                elif is_bool:
                    return value.lower() in ['true', '1', 't', 'y', 'yes']
                return value
        
        # 2. Check config file
        try:
            if self.parser.has_option(section, key):
                if is_int:
                    return self.parser.getint(section, key)
                elif is_bool:
                    return self.parser.getboolean(section, key)
                return self.parser.get(section, key)
        except configparser.NoSectionError:
            logging.debug(f"Section '{section}' not found in config file. Using default for {key}.")
        except configparser.NoOptionError:
            logging.debug(f"Option '{key}' not found in section '{section}'. Using default.")
        except ValueError as e:
             logging.warning(f"Error parsing {section}.{key} from config: {e}. Using default.")

        # 3. Return default
        return default

# Create a single instance to be imported by other modules
config = ConfigManager()

# Example of how to define specific config properties for easy access
LOG_LEVEL = config.get('General', 'LOG_LEVEL', default='INFO', env_var='LOG_LEVEL')

IPFS_API_HOST = config.get('IPFS', 'API_HOST', default='127.0.0.1', env_var='IPFS_API_HOST')
IPFS_API_PORT = config.get('IPFS', 'API_PORT', default=5001, is_int=True, env_var='IPFS_API_PORT')

SUBSTRATE_NODE_URL = config.get('Substrate', 'NODE_URL', default='wss://rpc.hippius.network', env_var='SUBSTRATE_NODE_URL')

DATABASE_NAME = config.get('Database', 'NAME', default='miner_data.db', env_var='DATABASE_NAME')

POLLING_INTERVAL_SECONDS = config.get('MinerService', 'POLLING_INTERVAL_SECONDS', default=60, is_int=True, env_var='POLLING_INTERVAL_SECONDS')
MAX_PIN_RETRIES = config.get('MinerService', 'MAX_PIN_RETRIES', default=5, is_int=True, env_var='MAX_PIN_RETRIES')
UNPINNABLE_CIDS_REPORT_FILE = config.get('MinerService', 'UNPINNABLE_CIDS_REPORT_FILE', default='unpinnable_cids_report.json', env_var='UNPINNABLE_CIDS_REPORT_FILE')
GC_TRIGGER_INTERVAL_LOOPS = config.get('MinerService', 'GC_TRIGGER_INTERVAL_LOOPS', default=10, is_int=True, env_var='GC_TRIGGER_INTERVAL_LOOPS')

if __name__ == '__main__':
    # Test the config manager
    logging.basicConfig(level=LOG_LEVEL)
    logging.info(f"Log Level: {LOG_LEVEL}")
    logging.info(f"IPFS API Host: {IPFS_API_HOST}")
    logging.info(f"IPFS API Port: {IPFS_API_PORT}")
    logging.info(f"Substrate Node URL: {SUBSTRATE_NODE_URL}")
    logging.info(f"Database Name: {DATABASE_NAME}")
    logging.info(f"Polling Interval: {POLLING_INTERVAL_SECONDS}s")
    logging.info(f"Max Pin Retries: {MAX_PIN_RETRIES}")
    logging.info(f"Unpinnable CIDs Report File: {UNPINNABLE_CIDS_REPORT_FILE}")
    logging.info(f"GC Trigger Interval Loops: {GC_TRIGGER_INTERVAL_LOOPS}")

    # Example of testing an env var override
    # Set an env var like: export TEST_ENV_OVERRIDE="overridden_value"
    # TEST_VALUE = config.get('General', 'TEST_VALUE', default='default_test', env_var='TEST_ENV_OVERRIDE')
    # logging.info(f"Test Value (check env override): {TEST_VALUE}") 