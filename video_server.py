import socket
import cv2
import numpy as np
import threading
import time
import base64
from flask import Flask, render_template_string, Response
import io
from PIL import Image
import struct

class VideoServer:
    def __init__(self, host='0.0.0.0', port=8080, web_port=5000):
        """
        Initialize the video server with TCP socket and Flask web interface
        
        Args:
            host (str): Host address for TCP server
            port (int): Port for TCP video stream
            web_port (int): Port for Flask web dashboard
        """
        self.host = host
        self.port = port
        self.web_port = web_port
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.server_socket = None
        
        # Initialize Flask app for web dashboard
        self.app = Flask(__name__)
        self.setup_flask_routes()
        
    def setup_flask_routes(self):
        """Setup Flask routes for web dashboard"""
        
        # HTML template for the video dashboard
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Video Stream Dashboard</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    text-align: center;
                }
                .header {
                    margin-bottom: 30px;
                }
                .video-container {
                    background: rgba(0, 0, 0, 0.3);
                    border-radius: 15px;
                    padding: 20px;
                    margin-bottom: 20px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                }
                .video-feed {
                    max-width: 100%;
                    border-radius: 10px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
                }
                .status {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 15px;
                    border-radius: 10px;
                    margin: 20px 0;
                    backdrop-filter: blur(10px);
                }
                .controls {
                    display: flex;
                    justify-content: center;
                    gap: 15px;
                    margin-top: 20px;
                }
                .btn {
                    padding: 12px 24px;
                    border: none;
                    border-radius: 8px;
                    background: rgba(255, 255, 255, 0.2);
                    color: white;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    backdrop-filter: blur(10px);
                }
                .btn:hover {
                    background: rgba(255, 255, 255, 0.3);
                    transform: translateY(-2px);
                }
                .stats {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin-top: 20px;
                }
                .stat-card {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 15px;
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                }
                .stat-value {
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 5px;
                }
                .stat-label {
                    font-size: 14px;
                    opacity: 0.8;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎥 Video Stream Dashboard</h1>
                    <p>Real-time video streaming from TCP client</p>
                </div>
                
                <div class="video-container">
                    <img id="videoFeed" class="video-feed" src="/video_feed" alt="Video Stream">
                </div>
                
                <div class="status">
                    <h3>Server Status</h3>
                    <p>TCP Server: <span id="tcpStatus">Running on {{ host }}:{{ port }}</span></p>
                    <p>Web Dashboard: <span id="webStatus">Running on {{ web_host }}:{{ web_port }}</span></p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value" id="fpsCounter">0</div>
                        <div class="stat-label">FPS</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="frameCounter">0</div>
                        <div class="stat-label">Frames Received</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="connectionStatus">Disconnected</div>
                        <div class="stat-label">Client Status</div>
                    </div>
                </div>
                
                <div class="controls">
                    <button class="btn" onclick="refreshPage()">🔄 Refresh</button>
                    <button class="btn" onclick="toggleFullscreen()">⛶ Fullscreen</button>
                </div>
            </div>
            
            <script>
                let frameCount = 0;
                let lastTime = Date.now();
                let fps = 0;
                
                // Update FPS counter
                function updateStats() {
                    frameCount++;
                    const now = Date.now();
                    const delta = now - lastTime;
                    
                    if (delta >= 1000) {
                        fps = Math.round((frameCount * 1000) / delta);
                        document.getElementById('fpsCounter').textContent = fps;
                        document.getElementById('frameCounter').textContent = frameCount;
                        frameCount = 0;
                        lastTime = now;
                    }
                }
                
                // Update video feed
                function updateVideo() {
                    const img = document.getElementById('videoFeed');
                    img.src = '/video_feed?' + new Date().getTime();
                    updateStats();
                }
                
                // Refresh page
                function refreshPage() {
                    location.reload();
                }
                
                // Toggle fullscreen
                function toggleFullscreen() {
                    const videoContainer = document.querySelector('.video-container');
                    if (!document.fullscreenElement) {
                        videoContainer.requestFullscreen().catch(err => {
                            console.log('Error attempting to enable fullscreen:', err);
                        });
                    } else {
                        document.exitFullscreen();
                    }
                }
                
                // Auto-refresh video feed
                setInterval(updateVideo, 33); // ~30 FPS
                
                // Check connection status
                setInterval(() => {
                    fetch('/status')
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('connectionStatus').textContent = 
                                data.connected ? 'Connected' : 'Disconnected';
                        })
                        .catch(() => {
                            document.getElementById('connectionStatus').textContent = 'Error';
                        });
                }, 1000);
            </script>
        </body>
        </html>
        """
        
        @self.app.route('/')
        def dashboard():
            """Main dashboard page"""
            return render_template_string(
                html_template,
                host=self.host,
                port=self.port,
                web_host='localhost',
                web_port=self.web_port
            )
        
        @self.app.route('/video_feed')
        def video_feed():
            """Stream video frames as MJPEG"""
            def generate():
                while True:
                    with self.frame_lock:
                        if self.current_frame is not None:
                            # Convert frame to JPEG
                            _, buffer = cv2.imencode('.jpg', self.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                            frame_bytes = buffer.tobytes()
                            
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                        else:
                            # Send placeholder frame if no video
                            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                            cv2.putText(placeholder, 'No Video Stream', (150, 240), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                            _, buffer = cv2.imencode('.jpg', placeholder)
                            frame_bytes = buffer.tobytes()
                            
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    
                    time.sleep(0.033)  # ~30 FPS
            
            return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
        
        @self.app.route('/status')
        def status():
            """Return server status as JSON"""
            return {
                'connected': self.current_frame is not None,
                'tcp_port': self.port,
                'web_port': self.web_port
            }
    
    def start_tcp_server(self):
        """Start the TCP server to receive video frames"""
        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            print(f"🎥 TCP Video Server started on {self.host}:{self.port}")
            print("Waiting for client connections...")
            
            self.running = True
            
            while self.running:
                try:
                    # Accept client connection
                    client_socket, client_address = self.server_socket.accept()
                    print(f"📡 Client connected from {client_address}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.error as e:
                    if self.running:
                        print(f"❌ Socket error: {e}")
                    break
                    
        except Exception as e:
            print(f"❌ Failed to start TCP server: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection and video stream"""
        try:
            while self.running:
                # Receive frame size (4 bytes)
                size_data = client_socket.recv(4)
                if not size_data:
                    break
                
                frame_size = struct.unpack('!I', size_data)[0]
                
                # Receive frame data
                frame_data = b''
                while len(frame_data) < frame_size:
                    chunk = client_socket.recv(min(frame_size - len(frame_data), 4096))
                    if not chunk:
                        break
                    frame_data += chunk
                
                if len(frame_data) == frame_size:
                    # Decode JPEG frame
                    try:
                        # Convert bytes to numpy array
                        nparr = np.frombuffer(frame_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if frame is not None:
                            # Update current frame with thread safety
                            with self.frame_lock:
                                self.current_frame = frame
                            
                            print(f"📹 Received frame: {frame.shape[1]}x{frame.shape[0]} from {client_address}")
                        else:
                            print(f"⚠️ Failed to decode frame from {client_address}")
                            
                    except Exception as e:
                        print(f"❌ Frame decoding error: {e}")
                else:
                    print(f"⚠️ Incomplete frame received from {client_address}")
                    
        except Exception as e:
            print(f"❌ Client handling error: {e}")
        finally:
            print(f"🔌 Client {client_address} disconnected")
            client_socket.close()
            
            # Clear current frame when client disconnects
            with self.frame_lock:
                self.current_frame = None
    
    def start_web_server(self):
        """Start the Flask web server"""
        try:
            print(f"🌐 Web Dashboard started on http://localhost:{self.web_port}")
            self.app.run(host='0.0.0.0', port=self.web_port, debug=False, threaded=True)
        except Exception as e:
            print(f"❌ Failed to start web server: {e}")
    
    def start(self):
        """Start both TCP and web servers"""
        # Start TCP server in separate thread
        tcp_thread = threading.Thread(target=self.start_tcp_server)
        tcp_thread.daemon = True
        tcp_thread.start()
        
        # Start web server in main thread
        self.start_web_server()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("🛑 Server stopped")


def main():
    """Main function to run the video server"""
    print("🚀 Starting Video Stream Server...")
    print("=" * 50)
    
    # Create and start video server
    server = VideoServer(host='0.0.0.0', port=8080, web_port=5000)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        server.stop()
        print("✅ Server shutdown complete")


if __name__ == "__main__":
    main()
