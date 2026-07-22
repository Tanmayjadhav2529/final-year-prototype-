import os
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger("metal_inspection.db")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "metal_inspection")

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self.collection_name = "inspections"
        self._connect_task = None

    def start_connection(self):
        """Starts the connection process in the background if not already running."""
        if not self.connected and (self._connect_task is None or self._connect_task.done()):
            self._connect_task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self):
        """Internal loop to connect to MongoDB with exponential backoff."""
        attempt = 1
        delay = 1
        max_delay = 30
        
        while not self.connected:
            try:
                logger.info(f"Connecting to MongoDB at {MONGO_URI} (Attempt {attempt})...")
                self.client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=2000)
                # Force connection check
                await self.client.admin.command('ping')
                self.db = self.client[MONGO_DB]
                self.connected = True
                logger.info("Successfully connected to MongoDB.")
            except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
                logger.warning(f"Failed to connect to MongoDB (Attempt {attempt}): {e}")
                self.connected = False
                self.client = None
                self.db = None
                logger.info(f"Retrying MongoDB connection in {delay} seconds...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1

    async def save_inspection(self, doc: dict) -> bool:
        """Saves inspection document to MongoDB. Returns True if successful, False otherwise."""
        if not self.connected or self.db is None:
            logger.warning("MongoDB is offline. Result not saved to db.")
            self.start_connection()
            return False
        
        try:
            collection = self.db[self.collection_name]
            # Perform insertion
            await collection.insert_one(doc)
            return True
        except Exception as e:
            logger.error(f"Error saving to MongoDB: {e}")
            self.connected = False
            self.start_connection()
            return False

    async def get_history(self, filter_query: dict, limit: int = 100, skip: int = 0):
        """Queries history of inspections."""
        if not self.connected or self.db is None:
            return []
        try:
            collection = self.db[self.collection_name]
            cursor = collection.find(filter_query).sort("timestamp", -1).skip(skip).limit(limit)
            results = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error fetching history from MongoDB: {e}")
            return []

db_manager = DatabaseManager()
