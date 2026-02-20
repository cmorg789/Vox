//! Video capture via nokhwa — camera capture and pixel format conversion.

use nokhwa::pixel_format::RgbFormat;
use nokhwa::utils::{
    CameraFormat, CameraIndex, FrameFormat, RequestedFormat, RequestedFormatType, Resolution,
};
use nokhwa::Camera;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc;

/// A captured frame from the camera, with both RGB→I420 and RGBA data.
pub struct CapturedFrame {
    pub width: u32,
    pub height: u32,
    /// Y plane (width * height bytes).
    pub y: Vec<u8>,
    /// U plane ((width/2) * (height/2) bytes).
    pub u: Vec<u8>,
    /// V plane ((width/2) * (height/2) bytes).
    pub v: Vec<u8>,
    /// RGBA for local preview (width * height * 4 bytes).
    pub rgba: Vec<u8>,
}

/// Camera configuration.
#[derive(Debug, Clone)]
pub struct CameraConfig {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
}

impl Default for CameraConfig {
    fn default() -> Self {
        CameraConfig {
            width: 640,
            height: 480,
            fps: 30,
        }
    }
}

/// Handle to stop the camera thread. Dropping this stops capture.
pub struct CameraStopHandle {
    stop: Arc<AtomicBool>,
}

impl Drop for CameraStopHandle {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
    }
}

/// Start camera capture in a background std::thread.
///
/// Returns a bounded receiver of captured frames and a stop handle.
/// The channel has capacity 4 for backpressure — old frames are dropped
/// if the consumer can't keep up.
pub fn start_camera_capture(
    config: CameraConfig,
) -> Result<(mpsc::Receiver<CapturedFrame>, CameraStopHandle), String> {
    let (tx, rx) = mpsc::channel(4);
    let stop = Arc::new(AtomicBool::new(false));
    let stop_clone = stop.clone();

    std::thread::spawn(move || {
        if let Err(e) = camera_thread(config, tx, stop_clone) {
            tracing::error!("Camera thread exited with error: {e}");
        }
    });

    Ok((rx, CameraStopHandle { stop }))
}

fn camera_thread(
    config: CameraConfig,
    tx: mpsc::Sender<CapturedFrame>,
    stop: Arc<AtomicBool>,
) -> Result<(), String> {
    let index = CameraIndex::Index(0);
    let format = CameraFormat::new(
        Resolution::new(config.width, config.height),
        FrameFormat::MJPEG,
        config.fps,
    );
    let requested =
        RequestedFormat::new::<RgbFormat>(RequestedFormatType::Closest(format));

    let mut camera =
        Camera::new(index, requested).map_err(|e| format!("Camera open: {e}"))?;
    camera
        .open_stream()
        .map_err(|e| format!("Camera stream: {e}"))?;

    let actual = camera.camera_format();
    let w = actual.resolution().width();
    let h = actual.resolution().height();
    tracing::info!("Camera started: {}x{} @ {}fps", w, h, actual.frame_rate());

    while !stop.load(Ordering::Relaxed) {
        let frame = match camera.frame() {
            Ok(f) => f,
            Err(e) => {
                tracing::warn!("Camera frame error: {e}");
                continue;
            }
        };

        let decoded = match frame.decode_image::<RgbFormat>() {
            Ok(img) => img,
            Err(e) => {
                tracing::warn!("Frame decode error: {e}");
                continue;
            }
        };

        let rgb = decoded.as_raw();
        let (y, u, v) = rgb_to_i420(rgb, w as usize, h as usize);
        let rgba = rgb_to_rgba(rgb);

        let captured = CapturedFrame {
            width: w,
            height: h,
            y,
            u,
            v,
            rgba,
        };

        // try_send: drop frame if consumer is behind
        if tx.try_send(captured).is_err() {
            tracing::trace!("Video frame dropped (consumer behind)");
        }
    }

    let _ = camera.stop_stream();
    tracing::info!("Camera stopped");
    Ok(())
}

/// Convert RGB888 to I420 (YUV 4:2:0) planes.
pub fn rgb_to_i420(rgb: &[u8], width: usize, height: usize) -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let mut y = vec![0u8; width * height];
    let cw = width / 2;
    let ch = height / 2;
    let mut u = vec![0u8; cw * ch];
    let mut v = vec![0u8; cw * ch];

    for row in 0..height {
        for col in 0..width {
            let idx = (row * width + col) * 3;
            let r = rgb[idx] as f32;
            let g = rgb[idx + 1] as f32;
            let b = rgb[idx + 2] as f32;

            let yv = (0.299 * r + 0.587 * g + 0.114 * b).clamp(0.0, 255.0);
            y[row * width + col] = yv as u8;

            if row % 2 == 0 && col % 2 == 0 {
                let uv = (-0.169 * r - 0.331 * g + 0.5 * b + 128.0).clamp(0.0, 255.0);
                let vv = (0.5 * r - 0.419 * g - 0.081 * b + 128.0).clamp(0.0, 255.0);
                let ci = (row / 2) * cw + (col / 2);
                u[ci] = uv as u8;
                v[ci] = vv as u8;
            }
        }
    }

    (y, u, v)
}

/// Convert RGB888 to RGBA8888 (alpha = 255).
pub fn rgb_to_rgba(rgb: &[u8]) -> Vec<u8> {
    let pixel_count = rgb.len() / 3;
    let mut rgba = Vec::with_capacity(pixel_count * 4);
    for pixel in rgb.chunks_exact(3) {
        rgba.push(pixel[0]);
        rgba.push(pixel[1]);
        rgba.push(pixel[2]);
        rgba.push(255);
    }
    rgba
}
