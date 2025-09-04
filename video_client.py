import cv2
import socket
import struct
import time
import numpy as np

class VideoClient:
    def __init__(self, server_host='localhost', server_port=8080, camera_index=0):
        """
        Initialize video client
        
        Args:
            server_host (str): Server host address
            server_port (int): Server port
            camera_index (int): Camera device index
        """
        self.server_host = server_host
        self.server_port = server_port
        self.camera_index = camera_index
        self.socket = None
        self.cap = None
        self.running = False
        
    def connect(self):
        """Connect to the video server"""
        try:
            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            print(f"✅ Connected to server at {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to server: {e}")
            return False
    
    def start_camera(self):
        """Initialize camera capture"""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                print(f"❌ Failed to open camera {self.camera_index}")
                return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            print(f"📷 Camera {self.camera_index} initialized")
            return True
        except Exception as e:
            print(f"❌ Camera initialization error: {e}")
            return False
    
    def send_frame(self, frame):
        """Send a single frame to the server"""
        try:
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_data = buffer.tobytes()
            
            # Send frame size first (4 bytes)
            frame_size = len(frame_data)
            size_data = struct.pack('!I', frame_size)
            self.socket.sendall(size_data)
            
            # Send frame data
            self.socket.sendall(frame_data)
            
            return True
        except Exception as e:
            print(f"❌ Frame sending error: {e}")
            return False
    
    def stream_video(self):
        """Main video streaming loop"""
        if not self.connect():
            return
        
        if not self.start_camera():
            return
        
        print("🎬 Starting video stream...")
        print("Press 'q' to quit")
        
        self.running = True
        frame_count = 0
        start_time = time.time()
        
        try:
            while self.running:
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    print("⚠️ Failed to capture frame")
                    break
                
                # Add timestamp overlay
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.7, (0, 255, 0), 2)
                
                # Add frame counter
                cv2.putText(frame, f"Frame: {frame_count}", (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Send frame to server
                if not self.send_frame(frame):
                    print("❌ Failed to send frame")
                    break
                
                frame_count += 1
                
                # Calculate and display FPS
                elapsed_time = time.time() - start_time
                if elapsed_time > 0:
                    fps = frame_count / elapsed_time
                    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 90), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Display local preview (optional)
                cv2.imshow('Video Client', frame)
                
                # Check for quit key
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                # Small delay to control frame rate
                time.sleep(0.033)  # ~30 FPS
                
        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
        except Exception as e:
            print(f"❌ Streaming error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the video client"""
        self.running = False
        
        if self.cap:
            self.cap.release()
        
        if self.socket:
            self.socket.close()
        
        cv2.destroyAllWindows()
        print("🛑 Video client stopped")


def main():
    """Main function to run the video client"""
    print("🎬 Video Stream Client")
    print("=" * 30)
    
    # Configuration
    SERVER_HOST = 'localhost'  # Change to server IP if different
    SERVER_PORT = 8080
    CAMERA_INDEX = 0  # Usually 0 for built-in webcam
    
    # Create and run client
    client = VideoClient(
        server_host=SERVER_HOST,
        server_port=SERVER_PORT,
        camera_index=CAMERA_INDEX
    )
    
    try:
        client.stream_video()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down client...")
        client.stop()


if __name__ == "__main__":
    main()
