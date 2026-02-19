//! Media state machine — processes commands from Python.

use crate::MediaCommand;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

/// Room connection state.
struct RoomState {
    url: String,
    token: String,
    muted: bool,
    deafened: bool,
    video: bool,
}

/// Main media event loop. Receives commands from the Python layer
/// and manages QUIC connection + audio pipeline lifecycle.
pub async fn run_media_loop(
    mut cmd_rx: mpsc::UnboundedReceiver<MediaCommand>,
    cancel: CancellationToken,
) {
    let mut room: Option<RoomState> = None;

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                tracing::info!("Media loop cancelled");
                break;
            }
            cmd = cmd_rx.recv() => {
                match cmd {
                    None => break,
                    Some(MediaCommand::Connect { url, token }) => {
                        tracing::info!("Connecting to SFU at {}", url);
                        room = Some(RoomState {
                            url,
                            token,
                            muted: false,
                            deafened: false,
                            video: false,
                        });
                        // TODO: establish QUIC connection, start audio pipeline
                    }
                    Some(MediaCommand::Disconnect) => {
                        tracing::info!("Disconnecting from SFU");
                        room = None;
                        // TODO: tear down QUIC + audio
                    }
                    Some(MediaCommand::SetMute(muted)) => {
                        if let Some(ref mut r) = room {
                            r.muted = muted;
                        }
                    }
                    Some(MediaCommand::SetDeaf(deafened)) => {
                        if let Some(ref mut r) = room {
                            r.deafened = deafened;
                        }
                    }
                    Some(MediaCommand::SetVideo(enabled)) => {
                        if let Some(ref mut r) = room {
                            r.video = enabled;
                        }
                    }
                }
            }
        }
    }
}
