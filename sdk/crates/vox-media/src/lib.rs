mod audio;
mod codec;
mod quic;
mod state;
mod video;

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

/// Commands from Python to the media runtime.
enum MediaCommand {
    Connect {
        url: String,
        token: String,
        room_id: u32,
        user_id: u32,
        cert_der: Option<Vec<u8>>,
        idle_timeout_secs: u64,
        datagram_buffer_size: usize,
    },
    Disconnect,
    SetMute(bool),
    SetDeaf(bool),
    SetVideo(bool),
    SetVideoConfig {
        width: u32,
        height: u32,
        fps: u32,
        bitrate_kbps: u32,
    },
}

/// Events emitted by the media runtime for Python consumption.
enum MediaEvent {
    Connected,
    Disconnected(String),
    ConnectFailed(String),
    Reconnecting { attempt: u32, delay_secs: u64 },
    AudioError(String),
    VideoError(String),
}

impl MediaEvent {
    fn to_tuple(&self) -> (String, String) {
        match self {
            MediaEvent::Connected => ("connected".into(), String::new()),
            MediaEvent::Disconnected(reason) => ("disconnected".into(), reason.clone()),
            MediaEvent::ConnectFailed(reason) => ("connect_failed".into(), reason.clone()),
            MediaEvent::Reconnecting { attempt, delay_secs } => {
                ("reconnecting".into(), format!("attempt={attempt},delay={delay_secs}"))
            }
            MediaEvent::AudioError(msg) => ("audio_error".into(), msg.clone()),
            MediaEvent::VideoError(msg) => ("video_error".into(), msg.clone()),
        }
    }
}

/// Thread-safe event queue for pushing events from the media runtime to Python.
pub(crate) type EventQueue = Arc<Mutex<VecDeque<(String, String)>>>;

/// Push an event onto the queue.
pub(crate) fn push_event(queue: &EventQueue, event: MediaEvent) {
    if let Ok(mut q) = queue.lock() {
        q.push_back(event.to_tuple());
    }
}

/// A decoded video frame ready for Python consumption.
pub(crate) struct VideoFrameOutput {
    pub user_id: u32,   // 0 = local preview
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

/// Thread-safe queue of decoded video frames.
pub(crate) type VideoFrameQueue = Arc<Mutex<VecDeque<VideoFrameOutput>>>;

/// Push a video frame onto the queue (bounded to 8 frames, drops oldest).
pub(crate) fn push_video_frame(queue: &VideoFrameQueue, frame: VideoFrameOutput) {
    if let Ok(mut q) = queue.lock() {
        if q.len() >= 8 {
            q.pop_front();
        }
        q.push_back(frame);
    }
}

/// Client-side media transport for Vox voice/video rooms.
///
/// Runs a background tokio runtime that manages QUIC transport to the SFU,
/// Opus encoding/decoding, and cpal audio capture/playback.
#[pyclass]
struct VoxMediaClient {
    cmd_tx: Option<mpsc::UnboundedSender<MediaCommand>>,
    cancel: Option<CancellationToken>,
    rt_handle: Option<std::thread::JoinHandle<()>>,
    events: EventQueue,
    video_frames: VideoFrameQueue,
    muted: bool,
    deafened: bool,
    video: bool,
}

#[pymethods]
impl VoxMediaClient {
    #[new]
    fn new() -> Self {
        let _ = tracing_subscriber::fmt::try_init();
        VoxMediaClient {
            cmd_tx: None,
            cancel: None,
            rt_handle: None,
            events: Arc::new(Mutex::new(VecDeque::new())),
            video_frames: Arc::new(Mutex::new(VecDeque::new())),
            muted: false,
            deafened: false,
            video: false,
        }
    }

    /// Start the background media runtime.
    fn start(&mut self) -> PyResult<()> {
        if self.cancel.is_some() {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Media client is already running",
            ));
        }

        let cancel = CancellationToken::new();
        self.cancel = Some(cancel.clone());

        let (cmd_tx, cmd_rx) = mpsc::unbounded_channel();
        self.cmd_tx = Some(cmd_tx);

        let events = self.events.clone();
        let events_thread = self.events.clone();
        let video_frames = self.video_frames.clone();
        let handle = std::thread::spawn(move || {
            let rt = match tokio::runtime::Runtime::new() {
                Ok(rt) => rt,
                Err(e) => {
                    push_event(&events_thread, MediaEvent::ConnectFailed(format!("Failed to create runtime: {e}")));
                    return;
                }
            };
            rt.block_on(async move {
                state::run_media_loop(cmd_rx, cancel, events, video_frames).await;
            });
        });

        self.rt_handle = Some(handle);
        Ok(())
    }

    /// Connect to a voice room via the SFU.
    #[pyo3(signature = (url, token, room_id, user_id, cert_der=None, idle_timeout_secs=30, datagram_buffer_size=65535))]
    fn connect(&self, url: &str, token: &str, room_id: u32, user_id: u32, cert_der: Option<Vec<u8>>, idle_timeout_secs: u64, datagram_buffer_size: usize) -> PyResult<()> {
        self.send_cmd(MediaCommand::Connect {
            url: url.to_string(),
            token: token.to_string(),
            room_id,
            user_id,
            cert_der,
            idle_timeout_secs,
            datagram_buffer_size,
        })
    }

    /// Disconnect from the current room.
    fn disconnect(&self) -> PyResult<()> {
        self.send_cmd(MediaCommand::Disconnect)
    }

    /// Set microphone mute state.
    fn set_mute(&mut self, muted: bool) -> PyResult<()> {
        self.muted = muted;
        self.send_cmd(MediaCommand::SetMute(muted))
    }

    /// Set deafen state (no audio playback).
    fn set_deaf(&mut self, deafened: bool) -> PyResult<()> {
        self.deafened = deafened;
        self.send_cmd(MediaCommand::SetDeaf(deafened))
    }

    /// Enable or disable video.
    fn set_video(&mut self, enabled: bool) -> PyResult<()> {
        self.video = enabled;
        self.send_cmd(MediaCommand::SetVideo(enabled))
    }

    /// Configure video capture parameters. Must be called before set_video(true).
    #[pyo3(signature = (width=640, height=480, fps=30, bitrate_kbps=500))]
    fn set_video_config(&self, width: u32, height: u32, fps: u32, bitrate_kbps: u32) -> PyResult<()> {
        self.send_cmd(MediaCommand::SetVideoConfig {
            width,
            height,
            fps,
            bitrate_kbps,
        })
    }

    /// Poll for the next decoded video frame.
    /// Returns (user_id, width, height, rgba_bytes) or None.
    /// user_id=0 means local camera preview.
    fn poll_video_frame<'py>(&self, py: Python<'py>) -> Option<(u32, u32, u32, Bound<'py, PyBytes>)> {
        let frame = self.video_frames.lock().ok()?.pop_front()?;
        let bytes = PyBytes::new(py, &frame.rgba);
        Some((frame.user_id, frame.width, frame.height, bytes))
    }

    /// Poll for the next event from the media runtime.
    /// Returns a (event_type, detail) tuple, or None if no events are pending.
    fn poll_event(&self) -> Option<(String, String)> {
        self.events.lock().ok()?.pop_front()
    }

    /// Stop the media runtime entirely.
    fn stop(&mut self) -> PyResult<()> {
        if let Some(cancel) = self.cancel.take() {
            cancel.cancel();
        }
        self.cmd_tx = None;
        if let Some(handle) = self.rt_handle.take() {
            let _ = handle.join();
        }
        Ok(())
    }

    /// Whether the microphone is muted.
    #[getter]
    fn is_muted(&self) -> bool {
        self.muted
    }

    /// Whether audio playback is deafened.
    #[getter]
    fn is_deafened(&self) -> bool {
        self.deafened
    }

    /// Whether video is enabled.
    #[getter]
    fn is_video_enabled(&self) -> bool {
        self.video
    }
}

impl VoxMediaClient {
    fn send_cmd(&self, cmd: MediaCommand) -> PyResult<()> {
        match &self.cmd_tx {
            Some(tx) => tx.send(cmd).map_err(|_| {
                PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Media runtime is not running")
            }),
            None => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Media client not started",
            )),
        }
    }
}

/// Python module definition.
#[pymodule]
fn _media(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<VoxMediaClient>()?;
    Ok(())
}
