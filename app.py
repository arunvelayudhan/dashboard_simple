import streamlit as st
import av
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase

st.set_page_config(page_title="Webcam Dashboard", page_icon="🎥", layout="wide")

st.title("Webcam Streaming Dashboard")
st.caption("Live webcam stream via WebRTC")

class PassthroughTransformer(VideoTransformerBase):
    def transform(self, frame: av.VideoFrame) -> av.VideoFrame:
        # No processing; pass frames through
        return frame

webrtc_streamer(
    key="webcam",
    video_transformer_factory=PassthroughTransformer,
    media_stream_constraints={"video": True, "audio": False},
)
