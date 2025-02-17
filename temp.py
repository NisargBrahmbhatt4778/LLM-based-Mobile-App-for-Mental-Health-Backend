import asyncio
import websockets

# Define the WebSocket server URL and user ID
USER_ID = "1234"  # Replace with actual user ID
WS_URL = f"ws://0.0.0.0:8001/ws/{USER_ID}"  # Update host/port if needed

async def websocket_client():
    async with websockets.connect(WS_URL) as websocket:
        print(f"Connected to {WS_URL}")

        # Send a message to the WebSocket server
        message = "Hello, WebSocket Server!"
        await websocket.send(message)
        print(f"Sent: {message}")

        # Receive a response
        response = await websocket.recv()
        print(f"Received: {response}")

# Run the client
asyncio.run(websocket_client())
