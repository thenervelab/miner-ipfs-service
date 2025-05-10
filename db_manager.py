# Database management functions
import aiosqlite
import logging
# import config_manager # This will be the new way
from config_manager import DATABASE_NAME # Directly import the specific config

# DATABASE_NAME = "miner_data.db" # Old way

async def initialize_database():
    """Initializes the database and creates tables if they don\'t exist."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            # Table for CIDs managed by the miner
            await db.execute('''
                CREATE TABLE IF NOT EXISTS pinned_cids (
                    cid TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('pinned', 'pending_pin', 'failed_pin', 'unpin_requested', 'unpinned')),
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    retry_count INTEGER DEFAULT 0
                )
            ''')

            # Table to store the miner's own profile CID
            await db.execute('''
                CREATE TABLE IF NOT EXISTS miner_profile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_cid TEXT UNIQUE NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE, 
                    pinned_locally BOOLEAN DEFAULT FALSE,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Ensure only one profile can be active
            await db.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_profile
                ON miner_profile (is_active)
                WHERE is_active = TRUE;
            ''')

            # Table for CIDs that could not be pinned after retries
            await db.execute('''
                CREATE TABLE IF NOT EXISTS unpinnable_cids (
                    cid TEXT PRIMARY KEY,
                    reason TEXT,
                    reported BOOLEAN DEFAULT FALSE,
                    first_failure_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_retry_timestamp TIMESTAMP
                )
            ''')

            await db.commit()
            logging.info(f"Database '{DATABASE_NAME}' initialized successfully.")
    except aiosqlite.Error as e:
        logging.error(f"Database initialization error: {e}")
        raise

async def add_cid_to_pin(cid: str):
    """Adds a CID to the pinned_cids table with 'pending_pin' status."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute(
                "INSERT OR IGNORE INTO pinned_cids (cid, status, retry_count) VALUES (?, 'pending_pin', 0)",
                (cid,)
            )
            # If it was previously failed, update status and reset retries
            await db.execute(
                "UPDATE pinned_cids SET status = 'pending_pin', retry_count = 0 WHERE cid = ? AND status = 'failed_pin'",
                (cid,)
            )
            await db.commit()
            logging.info(f"CID {cid} added/updated for pinning.")
    except aiosqlite.Error as e:
        logging.error(f"Error adding CID {cid} to pin: {e}")

async def update_cid_status(cid: str, status: str, retry_count: int = None):
    """Updates the status and optionally retry count of a CID in pinned_cids."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            if retry_count is not None:
                await db.execute(
                    "UPDATE pinned_cids SET status = ?, retry_count = ?, last_checked = CURRENT_TIMESTAMP WHERE cid = ?",
                    (status, retry_count, cid)
                )
            else:
                await db.execute(
                    "UPDATE pinned_cids SET status = ?, last_checked = CURRENT_TIMESTAMP WHERE cid = ?",
                    (status, cid)
                )
            await db.commit()
            logging.debug(f"CID {cid} status updated to {status}" + (f", retry count {retry_count}" if retry_count is not None else ""))
    except aiosqlite.Error as e:
        logging.error(f"Error updating status for CID {cid}: {e}")

async def get_cids_by_status(status: str):
    """Retrieves all CIDs with a specific status."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            async with db.execute("SELECT cid, retry_count FROM pinned_cids WHERE status = ?", (status,)) as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error as e:
        logging.error(f"Error fetching CIDs with status {status}: {e}")
        return []

async def add_unpinnable_cid(cid: str, reason: str):
    """Adds a CID to the unpinnable_cids table."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO unpinnable_cids (cid, reason, last_retry_timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (cid, reason)
            )
            await db.commit()
            logging.warning(f"CID {cid} marked as unpinnable. Reason: {reason}")
    except aiosqlite.Error as e:
        logging.error(f"Error adding unpinnable CID {cid}: {e}")

async def get_unpinnable_cids_to_report():
    """Retrieves unpinnable CIDs that have not been reported yet."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            async with db.execute("SELECT cid, reason FROM unpinnable_cids WHERE reported = FALSE") as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error as e:
        logging.error(f"Error fetching unpinnable CIDs to report: {e}")
        return []

async def mark_unpinnable_cids_as_reported(cids: list[str]):
    """Marks a list of unpinnable CIDs as reported."""
    if not cids:
        return
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            placeholders = ','.join('?' for _ in cids)
            await db.execute(
                f"UPDATE unpinnable_cids SET reported = TRUE WHERE cid IN ({placeholders})",
                cids
            )
            await db.commit()
            logging.info(f"Marked {len(cids)} CIDs as reported: {cids}")
    except aiosqlite.Error as e:
        logging.error(f"Error marking CIDs as reported: {e}")

async def set_active_miner_profile(profile_cid: str | None):
    """Sets the active miner profile CID, ensuring only one is active.
       If profile_cid is None, deactivates any current active profile.
    """
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            # Deactivate any existing active profile
            await db.execute("UPDATE miner_profile SET is_active = FALSE, pinned_locally = FALSE WHERE is_active = TRUE")
            
            if profile_cid:
                # Insert or update the new profile
                await db.execute(
                    '''
                    INSERT INTO miner_profile (profile_cid, is_active, pinned_locally) 
                    VALUES (?, TRUE, FALSE)
                    ON CONFLICT(profile_cid) DO UPDATE SET
                        is_active = TRUE,
                        pinned_locally = FALSE,
                        last_updated = CURRENT_TIMESTAMP
                    ''', (profile_cid,)
                )
                logging.info(f"Active miner profile set to {profile_cid}")
                # Ensure this profile document CID is in pinned_cids to be managed by the pinning process
                await add_cid_to_pin(profile_cid) 
                # Its status will be updated to 'pinned' by the standard pinning logic if successful
            else:
                logging.info("No active miner profile set (or current profile deactivated).")
            
            await db.commit()

    except aiosqlite.Error as e:
        logging.error(f"Error setting active miner profile (value: {profile_cid}): {e}")
        raise

async def get_active_miner_profile() -> tuple | None:
    """Retrieves the active miner profile CID and its pinned status."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            async with db.execute("SELECT profile_cid, pinned_locally FROM miner_profile WHERE is_active = TRUE") as cursor:
                return await cursor.fetchone()
    except aiosqlite.Error as e:
        logging.error(f"Error fetching active miner profile: {e}")
        return None

async def update_miner_profile_pinned_status(profile_cid: str, pinned: bool):
    """Updates the pinned_locally status of the miner profile."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute(
                "UPDATE miner_profile SET pinned_locally = ? WHERE profile_cid = ? AND is_active = TRUE",
                (pinned, profile_cid)
            )
            await db.commit()
            logging.info(f"Miner profile {profile_cid} pinned_locally status updated to {pinned}")
    except aiosqlite.Error as e:
        logging.error(f"Error updating miner profile {profile_cid} pinned status: {e}")

async def get_all_pinned_cids_from_db():
    """Retrieves all CIDs that are currently marked as 'pinned' or 'pending_pin' in the database."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            async with db.execute("SELECT cid FROM pinned_cids WHERE status IN ('pinned', 'pending_pin')") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    except aiosqlite.Error as e:
        logging.error(f"Error fetching all pinned CIDs: {e}")
        return []

async def get_cid_details(cid: str) -> tuple | None:
    """Retrieves details (cid, status, retry_count) for a specific CID from the pinned_cids table."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            async with db.execute("SELECT cid, status, retry_count FROM pinned_cids WHERE cid = ?", (cid,)) as cursor:
                return await cursor.fetchone()
    except aiosqlite.Error as e:
        logging.error(f"Error fetching details for CID {cid}: {e}")
        return None

async def remove_cid_from_pinning(cid: str):
    """Removes a CID from the pinned_cids table, effectively unpinning it."""
    try:
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute("DELETE FROM pinned_cids WHERE cid = ?", (cid,))
            await db.commit()
            logging.info(f"CID {cid} removed from pinning schedule.")
    except aiosqlite.Error as e:
        logging.error(f"Error removing CID {cid} from pinning: {e}") 