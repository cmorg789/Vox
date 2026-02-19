//! Video capture stubs — camera support is planned for a future release.

/// Placeholder for video frame data.
pub struct VideoFrame {
    pub width: u32,
    pub height: u32,
    pub data: Vec<u8>,
}

/// Stub: start camera capture. Currently unimplemented.
pub fn start_camera_capture() -> Result<(), Box<dyn std::error::Error>> {
    tracing::warn!("Video capture is not yet implemented");
    Ok(())
}

/// Stub: stop camera capture.
pub fn stop_camera_capture() {
    // no-op
}
