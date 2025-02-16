from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

app = FastAPI()

@app.websocket("/test_client")
async def test_client(websocket: WebSocket):
    await websocket.accept()
    
    server_ws_url = "ws://localhost:8000/ws/123"  # Change as needed

    async with app.websocket_connect(server_ws_url) as server_ws:
        print("Connected to WebSocket server.")

        # Send a test message
        await server_ws.send_text("Hello, chatbot!")
        await websocket.send_text("Sent: Hello, chatbot!")

        try:
            while True:
                response = await server_ws.receive_text()
                print("Received:", response)
                await websocket.send_text(response)
        except WebSocketDisconnect:
            print("WebSocket connection closed.")

    await websocket.close()