use bytes::Bytes;
use tokio_util::sync::CancellationToken;

use crate::header::MediaHeader;
use crate::state::SharedState;
use crate::tls;

/// Run the QUIC media endpoint: accept connections, authenticate, forward datagrams.
pub async fn run(bind_addr: String, state: SharedState, cancel: CancellationToken) {
    let (server_config, _cert_der) = tls::generate_self_signed();

    let addr: std::net::SocketAddr = bind_addr
        .parse()
        .expect("invalid bind address");

    let endpoint = quinn::Endpoint::server(server_config, addr)
        .expect("failed to create QUIC endpoint");

    tracing::info!("SFU QUIC endpoint listening on {}", addr);

    loop {
        tokio::select! {
            incoming = endpoint.accept() => {
                let Some(incoming) = incoming else {
                    tracing::info!("QUIC endpoint closed");
                    break;
                };
                let state = state.clone();
                let cancel = cancel.clone();
                tokio::spawn(async move {
                    match incoming.accept() {
                        Ok(connecting) => match connecting.await {
                            Ok(conn) => {
                                handle_connection(conn, state, cancel).await;
                            }
                            Err(e) => {
                                tracing::warn!("connection handshake failed: {}", e);
                            }
                        },
                        Err(e) => {
                            tracing::warn!("failed to accept incoming: {}", e);
                        }
                    }
                });
            }
            _ = cancel.cancelled() => {
                tracing::info!("SFU endpoint shutting down");
                break;
            }
        }
    }

    endpoint.close(0u32.into(), b"shutdown");
    endpoint.wait_idle().await;
}

/// Handle a single QUIC connection: authenticate via first datagram, then forward.
async fn handle_connection(conn: quinn::Connection, state: SharedState, cancel: CancellationToken) {
    // Auth: first datagram must be the media token (UTF-8)
    let token_data = tokio::select! {
        result = conn.read_datagram() => {
            match result {
                Ok(data) => data,
                Err(e) => {
                    tracing::debug!("failed to read auth datagram: {}", e);
                    return;
                }
            }
        }
        _ = cancel.cancelled() => return,
    };

    let token = match std::str::from_utf8(&token_data) {
        Ok(t) => t.to_string(),
        Err(_) => {
            tracing::debug!("invalid UTF-8 in auth token");
            conn.close(1u32.into(), b"invalid token");
            return;
        }
    };

    // Look up token -> (room_id, user_id)
    let (room_id, user_id) = {
        let st = state.read().await;
        match st.token_index.get(&token) {
            Some(&ids) => ids,
            None => {
                tracing::debug!("unknown media token");
                conn.close(1u32.into(), b"unknown token");
                return;
            }
        }
    };

    // Store connection in user session
    {
        let mut st = state.write().await;
        if let Some(room) = st.rooms.get_mut(&room_id) {
            if let Some(session) = room.users.get_mut(&user_id) {
                session.connection = Some(conn.clone());
            }
        }
    }

    tracing::info!(
        "user {} authenticated in room {} via QUIC",
        user_id, room_id
    );

    // Forwarding loop
    loop {
        tokio::select! {
            result = conn.read_datagram() => {
                match result {
                    Ok(data) => {
                        forward_datagram(&data, room_id, user_id, &state).await;
                    }
                    Err(e) => {
                        tracing::debug!("connection closed for user {}: {}", user_id, e);
                        break;
                    }
                }
            }
            _ = cancel.cancelled() => break,
        }
    }

    // Clean up connection reference
    {
        let mut st = state.write().await;
        if let Some(room) = st.rooms.get_mut(&room_id) {
            if let Some(session) = room.users.get_mut(&user_id) {
                session.connection = None;
            }
        }
    }
}

/// Forward a datagram to all other connected users in the same room.
async fn forward_datagram(data: &[u8], room_id: u32, sender_id: u32, state: &SharedState) {
    let header = match MediaHeader::parse(data) {
        Some(h) => h,
        None => {
            tracing::trace!("datagram too short to parse header");
            return;
        }
    };

    // Validate that the header room/user match the authenticated session
    if header.room_id != room_id || header.user_id != sender_id {
        tracing::warn!(
            "header mismatch: expected room={} user={}, got room={} user={}",
            room_id, sender_id, header.room_id, header.user_id
        );
        return;
    }

    let data = Bytes::copy_from_slice(data);
    let st = state.read().await;
    if let Some(room) = st.rooms.get(&room_id) {
        for (uid, session) in &room.users {
            if *uid != sender_id {
                if let Some(ref peer_conn) = session.connection {
                    let _ = peer_conn.send_datagram(data.clone());
                }
            }
        }
    }
}
