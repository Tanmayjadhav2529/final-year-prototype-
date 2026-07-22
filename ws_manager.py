import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger("metal_inspection.ws")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts a new WebSocket connection and adds it to the active list."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Removes a WebSocket connection from the active list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcasts a JSON message to all active WebSocket clients."""
        disconnected_clients = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to a WebSocket client, marking for removal: {e}")
                disconnected_clients.append(connection)
        
        for connection in disconnected_clients:
            self.disconnect(connection)

ws_manager = ConnectionManager()
