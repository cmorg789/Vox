mod audio;
mod codec;
mod quic;
mod state;
mod video;

use pyo3::prelude::*;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

/// Commands from Python to the media runtime.
enum MediaCommand {
    Connect {
        url: String,
        token: String,
        cert_der: Option<Vec<u8>>,
    },
    Disconnect,
    SetMute(bool),
    SetDeaf(bool),
    SetVideo(bool),
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
    muted: bool,
    deafened: bool,
    video: bool,
}

#[pymethods]
impl VoxMediaClient {
    #[new]
    fn new() -> Self {
        VoxMediaClient {
            cmd_tx: None,
            cancel: None,
            rt_handle: None,
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

        let handle = std::thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async move {
                state::run_media_loop(cmd_rx, cancel).await;
            });
        });

        self.rt_handle = Some(handle);
        Ok(())
    }

    /// Connect to a voice room via the SFU.
    #[pyo3(signature = (url, token, cert_der=None))]
    fn connect(&self, url: &str, token: &str, cert_der: Option<Vec<u8>>) -> PyResult<()> {
        self.send_cmd(MediaCommand::Connect {
            url: url.to_string(),
            token: token.to_string(),
            cert_der,
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
fn vox_media(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<VoxMediaClient>()?;
    Ok(())
}
