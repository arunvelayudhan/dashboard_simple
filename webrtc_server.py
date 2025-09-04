import asyncio
import json
import logging
from typing import Optional

from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from flask import Flask, request, jsonify, render_template_string

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_server")

app = Flask(__name__)
relay = MediaRelay()

# Shared relayed track from the current publisher
publisher_track: Optional[MediaStreamTrack] = None

# Keep references to connections to avoid GC
active_pcs: set[RTCPeerConnection] = set()

INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>WebRTC H264 Viewer</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; padding: 24px; background: #0e1117; color: #e6e6e6; }
    .container { max-width: 960px; margin: 0 auto; }
    h1 { margin: 0 0 8px 0; font-weight: 600; }
    .card { background: #11151c; border: 1px solid #1f2430; border-radius: 12px; padding: 16px; }
    video { width: 100%; max-height: 70vh; border-radius: 8px; background: #000; }
    .row { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
    button { background:#2b5cff; color:white; border:none; padding:10px 14px; border-radius:8px; cursor:pointer; }
    button:disabled { opacity:.6; cursor:not-allowed; }
    .tag { font-size: 12px; padding: 4px 8px; border-radius: 999px; background:#1f2430; display:inline-block; }
  </style>
</head>
<body>
  <div class="container">
    <h1>WebRTC H264 Viewer</h1>
    <p class="tag">This page receives H264 video from the Python publisher via the Flask+aiortc server.</p>
    <div class="card">
      <video id="video" playsinline autoplay></video>
      <div class="row">
        <button id="btnStart">Connect</button>
        <span id="status">Idle</span>
      </div>
    </div>
  </div>
  <script>
    async function start() {
      const status = document.getElementById('status');
      status.textContent = 'Creating offer...';

      const pc = new RTCPeerConnection({
        bundlePolicy: 'balanced',
        rtcpMuxPolicy: 'require'
      });

      pc.ontrack = (event) => {
        const el = document.getElementById('video');
        if (el.srcObject !== event.streams[0]) {
          el.srcObject = event.streams[0];
        }
      };

      // Prefer H264 if available
      const transceiver = pc.addTransceiver('video');

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      status.textContent = 'Sending offer...';
      const res = await fetch('/viewer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
      });

      if (!res.ok) {
        status.textContent = 'Server error creating answer';
        return;
      }

      const ans = await res.json();
      await pc.setRemoteDescription(new RTCSessionDescription(ans));
      status.textContent = 'Connected';
    }

    document.getElementById('btnStart').onclick = () => {
      document.getElementById('btnStart').disabled = true;
      start().catch(err => {
        document.getElementById('status').textContent = 'Error: ' + err;
      });
    };
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/publish", methods=["POST"])
async def publish():
    """Endpoint for the Python publisher client to POST its SDP offer (H264).
    Returns the SDP answer with no transceivers added (server receives only).
    The incoming video track is relayed for viewers.
    """
    global publisher_track

    params = await request.get_json(force=True)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    active_pcs.add(pc)

    @pc.on("track")
    def on_track(track: MediaStreamTrack):
        nonlocal publisher_track
        logger.info("Publisher track received: %s", track.kind)
        if track.kind == "video":
            publisher_track = relay.subscribe(track)

        @track.on("ended")
        async def on_ended():
            logger.info("Publisher track ended")

    await pc.setRemoteDescription(offer)

    # Server receives only; create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    logger.info("Publisher connected. PCs=%d", len(active_pcs))
    return jsonify({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

@app.route("/viewer", methods=["POST"])
async def viewer():
    """Endpoint for the browser viewer to POST its SDP offer.
    The server responds with an answer containing the relayed video track if present.
    """
    params = await request.get_json(force=True)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    active_pcs.add(pc)

    # If we have a relayed publisher track, add it for viewing
    if publisher_track is not None:
        sender = pc.addTrack(publisher_track)
        # Prefer H264 when possible
        try:
            from aiortc.rtcrtpsender import RTCRtpSender
            caps = RTCRtpSender.getCapabilities("video")
            h264_codecs = [c for c in caps.codecs if c.mimeType == "video/H264"]
            if h264_codecs:
                sender.setCodecPreferences(h264_codecs)
        except Exception as exc:
            logger.warning("Codec preference set failed: %s", exc)

    @pc.on("iceconnectionstatechange")
    def on_state_change():
        logger.info("Viewer ICE state: %s", pc.iceConnectionState)
        if pc.iceConnectionState in ("failed", "closed", "disconnected"):
            active_pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    logger.info("Viewer connected. PCs=%d", len(active_pcs))
    return jsonify({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

@app.route("/health")
def health() -> tuple[str, int]:
    return "ok", 200

if __name__ == "__main__":
    # Use asyncio.run to ensure proper event loop for Flask async views (requires Flask>=2.0)
    # Run Flask development server
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
