import argparse
import asyncio
import json
import logging
import cv2

from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame
import numpy as np
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_publisher")

class OpenCVCaptureTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 360, fps: int = 25):
        super().__init__()
        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.target_frame_time = 1.0 / float(fps)

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        ok, frame = self.cap.read()
        if not ok or frame is None:
            # fallback to black frame
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
        # BGR to RGB for av
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame

async def publish(server_url: str):
    pc = RTCPeerConnection()

    # Add video track from OpenCV
    video = OpenCVCaptureTrack()
    sender = pc.addTrack(video)

    # Prefer H264 if available
    try:
        from aiortc.rtcrtpsender import RTCRtpSender
        caps = RTCRtpSender.getCapabilities("video")
        h264_codecs = [c for c in caps.codecs if c.mimeType == "video/H264"]
        if h264_codecs:
            sender.setCodecPreferences(h264_codecs)
    except Exception as exc:
        logger.warning("Codec preference set failed: %s", exc)

    # Create offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Send to server /publish
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server_url}/publish",
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Server error: {resp.status}")
            ans = await resp.json()

    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    logger.info("Publishing started. Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await pc.close()

if __name__ == "__main__":
    import sys
    server = "http://localhost:5000"
    asyncio.run(publish(server))
