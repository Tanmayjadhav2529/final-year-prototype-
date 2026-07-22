import os
import asyncio
import logging
import json
import aiomqtt

logger = logging.getLogger("metal_inspection.mqtt")

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

class MqttManager:
    def __init__(self):
        self.connected = False
        self.client = None
        self._loop_task = None
        self._send_queue = asyncio.Queue()

    def start(self):
        """Starts the MQTT client background loop."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._client_loop())

    async def _client_loop(self):
        attempt = 1
        delay = 1
        max_delay = 30
        
        while True:
            try:
                logger.info(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT} (Attempt {attempt})...")
                # Connect using aiomqtt Client
                async with aiomqtt.Client(MQTT_BROKER, port=MQTT_PORT, timeout=2.0) as client:
                    self.client = client
                    self.connected = True
                    logger.info("Successfully connected to MQTT Broker.")
                    attempt = 1
                    delay = 1
                    
                    # Publish initial status
                    await client.publish("inspection/status", payload=json.dumps({"status": "connected"}))
                    
                    # Consume send queue and publish messages
                    while self.connected:
                        try:
                            # Use wait_for or simply get with timeout to allow periodic checks
                            topic, payload = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        
                        try:
                            await client.publish(topic, payload=payload)
                            self._send_queue.task_done()
                        except Exception as pub_err:
                            logger.error(f"Failed to publish message to topic '{topic}': {pub_err}")
                            # Put the item back into the queue
                            # Note: To preserve ordering we insert at the front, but for simple logs standard queue put is fine
                            await self._send_queue.put((topic, payload))
                            self._send_queue.task_done()
                            raise pub_err
                            
            except (aiomqtt.MqttError, Exception) as e:
                self.connected = False
                self.client = None
                logger.warning(f"MQTT client connection lost/failed: {e}")
                logger.info(f"Retrying MQTT connection in {delay} seconds...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
                attempt += 1

    async def publish(self, topic: str, payload: str):
        """Queues a message to be published to the MQTT broker."""
        await self._send_queue.put((topic, payload))
        # Ensure the loop runs if not already running
        self.start()

    async def publish_status(self, status: str):
        """Publishes the current system/inspection status."""
        await self.publish("inspection/status", json.dumps({"status": status}))

mqtt_manager = MqttManager()
