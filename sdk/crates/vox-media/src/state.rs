//! Media state machine — processes commands from Python.

use crate::{audio, codec, push_event, quic, EventQueue, MediaCommand, MediaEvent};
use bytes::Bytes;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

/// Maximum number of automatic reconnection attempts after a QUIC read error.
const MAX_RECONNECT_ATTEMPTS: u32 = 5;
/// Maximum backoff delay in seconds between reconnection attempts.
const MAX_BACKOFF_SECS: u64 = 30;

/// Snapshot of connection parameters for automatic reconnection.
#[derive(Clone)]
struct ConnectParams {
    url: String,
    token: String,
    room_id: u32,
    user_id: u32,
    cert_der: Option<Vec<u8>>,
    idle_timeout_secs: u64,
    datagram_buffer_size: usize,
}

/// Active media session — all live resources.
/// Dropping this struct tears down the QUIC connection, stops audio streams,
/// and frees the Opus encoder/decoder automatically.
struct ActiveSession {
    connection: quinn::Connection,
    room_id: u32,
    user_id: u32,
    sequence: u32,
    timestamp: u32,
    encoder: codec::OpusEncoder,
    decoder: codec::OpusDecoder,
    _capture_stream: cpal::Stream,
    capture_rx: mpsc::UnboundedReceiver<Vec<i16>>,
    _playback_stream: cpal::Stream,
    playback_tx: mpsc::UnboundedSender<Vec<i16>>,
    muted: bool,
    deafened: bool,
    video: bool,
}

/// Establish a QUIC connection and start the audio pipeline.
async fn establish_session(
    url: String,
    token: String,
    room_id: u32,
    user_id: u32,
    cert_der: Option<Vec<u8>>,
    idle_timeout_secs: u64,
    datagram_buffer_size: usize,
) -> Result<ActiveSession, Box<dyn std::error::Error>> {
    // Parse URL — strip optional quic:// prefix
    let addr_str = url
        .strip_prefix("quic://")
        .unwrap_or(&url);

    // Try to split host:port, preserving the hostname for TLS SNI
    let (host, addr) = if let Ok(sa) = addr_str.parse::<SocketAddr>() {
        // Bare IP:port — use IP string as server name (self-signed/pinned mode)
        (sa.ip().to_string(), sa)
    } else {
        // hostname:port — resolve and use hostname for TLS SNI (domain cert mode)
        let colon = addr_str.rfind(':').ok_or("missing port in URL")?;
        let hostname = &addr_str[..colon];
        let port: u16 = addr_str[colon + 1..].parse()?;
        let resolved = tokio::net::lookup_host((hostname, port)).await?
            .next().ok_or("DNS resolution failed")?;
        (hostname.to_string(), resolved)
    };

    // Create QUIC endpoint and connect
    let mut client_config = quic::make_client_config(cert_der)?;

    let mut transport = quinn::TransportConfig::default();
    transport.max_idle_timeout(Some(
        quinn::IdleTimeout::try_from(Duration::from_secs(idle_timeout_secs))
            .map_err(|e| format!("Invalid idle timeout: {e}"))?,
    ));
    transport.datagram_receive_buffer_size(Some(datagram_buffer_size));
    client_config.transport_config(Arc::new(transport));

    let mut endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?)?;
    endpoint.set_default_client_config(client_config);

    let connection = endpoint.connect(addr, &host)?.await?;

    // Send auth token as first datagram (SFU protocol requirement)
    connection.send_datagram(Bytes::from(token))?;

    // Start audio capture (960 samples = 20ms at 48kHz)
    let (capture_stream, capture_rx) = audio::start_capture(960)?;

    // Start audio playback
    let (playback_stream, playback_tx) = audio::start_playback()?;

    // Create Opus encoder/decoder
    let encoder = codec::OpusEncoder::new()?;
    let decoder = codec::OpusDecoder::new()?;

    Ok(ActiveSession {
        connection,
        room_id,
        user_id,
        sequence: 0,
        timestamp: 0,
        encoder,
        decoder,
        _capture_stream: capture_stream,
        capture_rx,
        _playback_stream: playback_stream,
        playback_tx,
        muted: false,
        deafened: false,
        video: false,
    })
}

/// Attempt to reconnect with exponential backoff.
/// Returns `Some(session)` on success, `None` after all attempts exhausted.
async fn reconnect_with_backoff(
    params: &ConnectParams,
    events: &EventQueue,
) -> Option<ActiveSession> {
    for attempt in 1..=MAX_RECONNECT_ATTEMPTS {
        let delay_secs = std::cmp::min(2u64.pow(attempt - 1), MAX_BACKOFF_SECS);
        push_event(events, MediaEvent::Reconnecting { attempt, delay_secs });
        tokio::time::sleep(Duration::from_secs(delay_secs)).await;

        tracing::info!("Reconnect attempt {}/{}", attempt, MAX_RECONNECT_ATTEMPTS);
        match establish_session(
            params.url.clone(),
            params.token.clone(),
            params.room_id,
            params.user_id,
            params.cert_der.clone(),
            params.idle_timeout_secs,
            params.datagram_buffer_size,
        ).await {
            Ok(s) => {
                push_event(events, MediaEvent::Connected);
                return Some(s);
            }
            Err(e) => {
                tracing::warn!("Reconnect attempt {} failed: {}", attempt, e);
            }
        }
    }

    push_event(
        events,
        MediaEvent::Disconnected(format!(
            "Reconnection failed after {} attempts",
            MAX_RECONNECT_ATTEMPTS
        )),
    );
    None
}

/// Main media event loop. Receives commands from the Python layer
/// and manages QUIC connection + audio pipeline lifecycle.
pub async fn run_media_loop(
    mut cmd_rx: mpsc::UnboundedReceiver<MediaCommand>,
    cancel: CancellationToken,
    events: EventQueue,
) {
    let mut session: Option<ActiveSession> = None;
    let mut last_connect_params: Option<ConnectParams> = None;

    loop {
        match &mut session {
            None => {
                // Disconnected — only listen for commands and cancellation
                tokio::select! {
                    _ = cancel.cancelled() => {
                        tracing::info!("Media loop cancelled");
                        break;
                    }
                    cmd = cmd_rx.recv() => {
                        match cmd {
                            None => break,
                            Some(MediaCommand::Connect { url, token, room_id, user_id, cert_der, idle_timeout_secs, datagram_buffer_size }) => {
                                tracing::info!("Connecting to SFU at {}", url);
                                let params = ConnectParams {
                                    url: url.clone(),
                                    token: token.clone(),
                                    room_id,
                                    user_id,
                                    cert_der: cert_der.clone(),
                                    idle_timeout_secs,
                                    datagram_buffer_size,
                                };
                                match establish_session(url, token, room_id, user_id, cert_der, idle_timeout_secs, datagram_buffer_size).await {
                                    Ok(s) => {
                                        tracing::info!("Connected to SFU");
                                        push_event(&events, MediaEvent::Connected);
                                        last_connect_params = Some(params);
                                        session = Some(s);
                                    }
                                    Err(e) => {
                                        tracing::error!("Failed to connect to SFU: {}", e);
                                        push_event(&events, MediaEvent::ConnectFailed(e.to_string()));
                                    }
                                }
                            }
                            Some(MediaCommand::Disconnect) => {}
                            Some(MediaCommand::SetMute(_)) => {}
                            Some(MediaCommand::SetDeaf(_)) => {}
                            Some(MediaCommand::SetVideo(_)) => {}
                        }
                    }
                }
            }
            Some(s) => {
                // Connected — listen for commands, capture frames, and incoming datagrams
                tokio::select! {
                    _ = cancel.cancelled() => {
                        tracing::info!("Media loop cancelled");
                        break;
                    }
                    cmd = cmd_rx.recv() => {
                        match cmd {
                            None => break,
                            Some(MediaCommand::Connect { url, token, room_id, user_id, cert_der, idle_timeout_secs, datagram_buffer_size }) => {
                                tracing::info!("Reconnecting to SFU at {}", url);
                                // Drop current session, then connect
                                session = None;
                                let params = ConnectParams {
                                    url: url.clone(),
                                    token: token.clone(),
                                    room_id,
                                    user_id,
                                    cert_der: cert_der.clone(),
                                    idle_timeout_secs,
                                    datagram_buffer_size,
                                };
                                match establish_session(url, token, room_id, user_id, cert_der, idle_timeout_secs, datagram_buffer_size).await {
                                    Ok(new_s) => {
                                        tracing::info!("Connected to SFU");
                                        push_event(&events, MediaEvent::Connected);
                                        last_connect_params = Some(params);
                                        session = Some(new_s);
                                    }
                                    Err(e) => {
                                        tracing::error!("Failed to connect to SFU: {}", e);
                                        push_event(&events, MediaEvent::ConnectFailed(e.to_string()));
                                    }
                                }
                                continue;
                            }
                            Some(MediaCommand::Disconnect) => {
                                tracing::info!("Disconnecting from SFU");
                                push_event(&events, MediaEvent::Disconnected("user requested".into()));
                                last_connect_params = None;
                                session = None;
                                continue;
                            }
                            Some(MediaCommand::SetMute(muted)) => {
                                s.muted = muted;
                            }
                            Some(MediaCommand::SetDeaf(deafened)) => {
                                s.deafened = deafened;
                            }
                            Some(MediaCommand::SetVideo(enabled)) => {
                                s.video = enabled;
                            }
                        }
                    }
                    Some(pcm) = s.capture_rx.recv() => {
                        if !s.muted {
                            send_audio_frame(s, pcm);
                        }
                    }
                    result = s.connection.read_datagram() => {
                        match result {
                            Ok(data) => {
                                if !s.deafened {
                                    receive_audio_frame(s, data);
                                }
                            }
                            Err(e) => {
                                tracing::error!("QUIC read error: {}", e);
                                session = None;

                                // Attempt automatic reconnect if we have saved params
                                if let Some(ref params) = last_connect_params {
                                    if let Some(new_session) = reconnect_with_backoff(params, &events).await {
                                        session = Some(new_session);
                                    } else {
                                        last_connect_params = None;
                                    }
                                } else {
                                    push_event(&events, MediaEvent::Disconnected(e.to_string()));
                                }
                                continue;
                            }
                        }
                    }
                }
            }
        }
    }
}

/// Encode and send an audio frame over QUIC.
fn send_audio_frame(session: &mut ActiveSession, pcm: Vec<i16>) {
    let opus_data = match session.encoder.encode(&pcm) {
        Ok(data) => data,
        Err(e) => {
            tracing::warn!("Opus encode error: {}", e);
            return;
        }
    };

    let frame = quic::OutFrame::audio(
        session.room_id,
        session.user_id,
        quic::CODEC_OPUS,
        session.sequence,
        session.timestamp,
        opus_data,
    );

    if let Err(e) = session.connection.send_datagram(frame.encode()) {
        tracing::warn!("Failed to send datagram: {}", e);
    }

    session.sequence = session.sequence.wrapping_add(1);
    session.timestamp = session.timestamp.wrapping_add(960);
}

/// Decode and play back a received audio frame.
fn receive_audio_frame(session: &mut ActiveSession, data: Bytes) {
    let frame = match quic::InFrame::decode(data) {
        Some(f) => f,
        None => {
            tracing::trace!("Unparseable incoming datagram, ignoring");
            return;
        }
    };

    if frame.header.media_type != quic::MEDIA_TYPE_AUDIO {
        return;
    }

    let pcm = match session.decoder.decode(&frame.payload) {
        Ok(samples) => samples,
        Err(e) => {
            tracing::warn!("Opus decode error: {}", e);
            return;
        }
    };

    let _ = session.playback_tx.send(pcm);
}
