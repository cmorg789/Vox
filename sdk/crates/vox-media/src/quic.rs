//! QUIC transport to the Vox SFU.
//!
//! Connects to the SFU using the same packet format as vox-sfu,
//! sends/receives media frames over QUIC datagrams.

use bytes::{Buf, BufMut, Bytes, BytesMut};
use quinn::{ClientConfig, Endpoint};
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::mpsc;

/// Media packet header matching vox-sfu format.
/// [1 byte type] [4 bytes user_id] [4 bytes room_id] [2 bytes seq] [payload...]
const HEADER_SIZE: usize = 11;

/// Packet types matching vox-sfu.
const PKT_AUDIO: u8 = 1;
const PKT_VIDEO: u8 = 2;

/// Outbound frame to send to SFU.
pub struct OutFrame {
    pub pkt_type: u8,
    pub user_id: u32,
    pub room_id: u32,
    pub seq: u16,
    pub payload: Bytes,
}

impl OutFrame {
    pub fn encode(&self) -> Bytes {
        let mut buf = BytesMut::with_capacity(HEADER_SIZE + self.payload.len());
        buf.put_u8(self.pkt_type);
        buf.put_u32(self.user_id);
        buf.put_u32(self.room_id);
        buf.put_u16(self.seq);
        buf.extend_from_slice(&self.payload);
        buf.freeze()
    }
}

/// Inbound frame received from SFU.
pub struct InFrame {
    pub pkt_type: u8,
    pub user_id: u32,
    pub room_id: u32,
    pub seq: u16,
    pub payload: Bytes,
}

impl InFrame {
    pub fn decode(data: Bytes) -> Option<Self> {
        if data.len() < HEADER_SIZE {
            return None;
        }
        let mut buf = &data[..];
        let pkt_type = buf[0];
        buf = &buf[1..];
        let user_id = u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]);
        buf = &buf[4..];
        let room_id = u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]);
        buf = &buf[4..];
        let seq = u16::from_be_bytes([buf[0], buf[1]]);
        let payload = data.slice(HEADER_SIZE..);
        Some(InFrame {
            pkt_type,
            user_id,
            room_id,
            seq,
            payload,
        })
    }
}

/// Build a QUIC client config with self-signed cert verification disabled
/// (matching vox-sfu's approach for local dev).
pub fn make_client_config() -> ClientConfig {
    let crypto = rustls::ClientConfig::builder()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(SkipServerVerification))
        .with_no_client_auth();
    ClientConfig::new(Arc::new(quinn::crypto::rustls::QuicClientConfig::try_from(crypto).unwrap()))
}

/// Skip TLS verification for development (matches vox-sfu self-signed setup).
#[derive(Debug)]
struct SkipServerVerification;

impl rustls::client::danger::ServerCertVerifier for SkipServerVerification {
    fn verify_server_cert(
        &self,
        _end_entity: &rustls::pki_types::CertificateDer<'_>,
        _intermediates: &[rustls::pki_types::CertificateDer<'_>],
        _server_name: &rustls::pki_types::ServerName<'_>,
        _ocsp_response: &[u8],
        _now: rustls::pki_types::UnixTime,
    ) -> Result<rustls::client::danger::ServerCertVerified, rustls::Error> {
        Ok(rustls::client::danger::ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &rustls::pki_types::CertificateDer<'_>,
        _dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        Ok(rustls::client::danger::HandshakeSignatureValid::assertion())
    }

    fn verify_tls13_signature(
        &self,
        _message: &[u8],
        _cert: &rustls::pki_types::CertificateDer<'_>,
        _dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        Ok(rustls::client::danger::HandshakeSignatureValid::assertion())
    }

    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> {
        vec![
            rustls::SignatureScheme::RSA_PKCS1_SHA256,
            rustls::SignatureScheme::RSA_PKCS1_SHA384,
            rustls::SignatureScheme::RSA_PKCS1_SHA512,
            rustls::SignatureScheme::ECDSA_NISTP256_SHA256,
            rustls::SignatureScheme::ECDSA_NISTP384_SHA384,
            rustls::SignatureScheme::ED25519,
        ]
    }
}
