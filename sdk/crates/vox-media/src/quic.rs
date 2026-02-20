//! QUIC transport to the Vox SFU.
//!
//! Connects to the SFU using the same packet format as vox-sfu,
//! sends/receives media frames over QUIC datagrams.

use bytes::{BufMut, Bytes, BytesMut};
use quinn::ClientConfig;
use std::sync::Arc;

/// ALPN protocol identifier — must match the SFU server.
const ALPN_PROTOCOL: &[u8] = b"vox-media/1";

/// Size of the fixed media frame header in bytes (matches vox-sfu header.rs).
pub const HEADER_SIZE: usize = 22;

// Media type values
pub const MEDIA_TYPE_AUDIO: u8 = 0;
pub const MEDIA_TYPE_VIDEO: u8 = 1;

// Flag bits (byte 3) — mirrors vox-sfu header.rs
pub const FLAG_KEYFRAME: u8 = 0b1000_0000;
pub const FLAG_END_OF_FRAME: u8 = 0b0100_0000;
pub const FLAG_FEC: u8 = 0b0010_0000;
pub const FLAG_MARKER: u8 = 0b0001_0000;
pub const FLAG_HAS_DEP_DESC: u8 = 0b0000_1000;

/// Current protocol version.
const PROTOCOL_VERSION: u8 = 1;

/// Media frame header (22 bytes fixed), matching vox-sfu exactly.
///
/// Wire layout (big-endian):
/// ```text
/// Byte 0:      version (u8)
/// Byte 1:      media_type (u8)
/// Byte 2:      codec_id (u8)
/// Byte 3:      flags (u8)
/// Bytes 4-7:   room_id (u32)
/// Bytes 8-11:  user_id (u32)
/// Bytes 12-15: sequence (u32)
/// Bytes 16-19: timestamp (u32)
/// Byte 20:     spatial_id (upper 4 bits) | temporal_id (lower 4 bits)
/// Byte 21:     dtx flag (bit 7, MSB)
/// ```
#[derive(Debug, Clone)]
pub struct MediaHeader {
    pub version: u8,
    pub media_type: u8,
    pub codec_id: u8,
    pub flags: u8,
    pub room_id: u32,
    pub user_id: u32,
    pub sequence: u32,
    pub timestamp: u32,
    pub spatial_id: u8,
    pub temporal_id: u8,
    pub dtx: bool,
}

impl MediaHeader {
    /// Parse a media header from the first 22 bytes of a datagram.
    pub fn parse(data: &[u8]) -> Option<Self> {
        if data.len() < HEADER_SIZE {
            return None;
        }
        Some(MediaHeader {
            version: data[0],
            media_type: data[1],
            codec_id: data[2],
            flags: data[3],
            room_id: u32::from_be_bytes([data[4], data[5], data[6], data[7]]),
            user_id: u32::from_be_bytes([data[8], data[9], data[10], data[11]]),
            sequence: u32::from_be_bytes([data[12], data[13], data[14], data[15]]),
            timestamp: u32::from_be_bytes([data[16], data[17], data[18], data[19]]),
            spatial_id: data[20] >> 4,
            temporal_id: data[20] & 0x0F,
            dtx: (data[21] & 0x80) != 0,
        })
    }

    /// Serialize the header into 22 bytes (big-endian).
    pub fn encode(&self) -> [u8; HEADER_SIZE] {
        let mut buf = [0u8; HEADER_SIZE];
        buf[0] = self.version;
        buf[1] = self.media_type;
        buf[2] = self.codec_id;
        buf[3] = self.flags;
        buf[4..8].copy_from_slice(&self.room_id.to_be_bytes());
        buf[8..12].copy_from_slice(&self.user_id.to_be_bytes());
        buf[12..16].copy_from_slice(&self.sequence.to_be_bytes());
        buf[16..20].copy_from_slice(&self.timestamp.to_be_bytes());
        buf[20] = (self.spatial_id << 4) | (self.temporal_id & 0x0F);
        buf[21] = if self.dtx { 0x80 } else { 0 };
        buf
    }

    pub fn is_keyframe(&self) -> bool {
        self.flags & FLAG_KEYFRAME != 0
    }

    pub fn is_end_of_frame(&self) -> bool {
        self.flags & FLAG_END_OF_FRAME != 0
    }

    pub fn has_dep_desc(&self) -> bool {
        self.flags & FLAG_HAS_DEP_DESC != 0
    }
}

/// Outbound media frame to send to the SFU.
pub struct OutFrame {
    pub header: MediaHeader,
    pub payload: Bytes,
}

impl OutFrame {
    /// Build an audio frame with sensible defaults.
    pub fn audio(room_id: u32, user_id: u32, codec_id: u8, seq: u32, timestamp: u32, payload: Bytes) -> Self {
        OutFrame {
            header: MediaHeader {
                version: PROTOCOL_VERSION,
                media_type: MEDIA_TYPE_AUDIO,
                codec_id,
                flags: FLAG_END_OF_FRAME,
                room_id,
                user_id,
                sequence: seq,
                timestamp,
                spatial_id: 0,
                temporal_id: 0,
                dtx: false,
            },
            payload,
        }
    }

    pub fn encode(&self) -> Bytes {
        let header_bytes = self.header.encode();
        let mut buf = BytesMut::with_capacity(HEADER_SIZE + self.payload.len());
        buf.put_slice(&header_bytes);
        buf.extend_from_slice(&self.payload);
        buf.freeze()
    }
}

/// Inbound media frame received from the SFU.
pub struct InFrame {
    pub header: MediaHeader,
    pub payload: Bytes,
}

impl InFrame {
    pub fn decode(data: Bytes) -> Option<Self> {
        let header = MediaHeader::parse(&data)?;
        let payload = data.slice(HEADER_SIZE..);
        Some(InFrame { header, payload })
    }
}

/// Build a QUIC client config.
///
/// - `None` → CA-signed mode: uses Mozilla root certificates.
/// - `Some(der)` → Self-signed mode: pins to the exact certificate DER bytes.
pub fn make_client_config(cert_der: Option<Vec<u8>>) -> ClientConfig {
    let mut crypto = match cert_der {
        None => {
            let mut roots = rustls::RootCertStore::empty();
            roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
            rustls::ClientConfig::builder()
                .with_root_certificates(roots)
                .with_no_client_auth()
        }
        Some(der) => {
            rustls::ClientConfig::builder()
                .dangerous()
                .with_custom_certificate_verifier(Arc::new(PinnedCertVerifier { der }))
                .with_no_client_auth()
        }
    };
    crypto.alpn_protocols = vec![ALPN_PROTOCOL.to_vec()];
    ClientConfig::new(Arc::new(
        quinn::crypto::rustls::QuicClientConfig::try_from(crypto).unwrap(),
    ))
}

/// Verifies the server certificate by comparing its raw DER bytes against a
/// pinned value, then delegates signature verification to the default ring
/// provider.
#[derive(Debug)]
struct PinnedCertVerifier {
    der: Vec<u8>,
}

impl rustls::client::danger::ServerCertVerifier for PinnedCertVerifier {
    fn verify_server_cert(
        &self,
        end_entity: &rustls::pki_types::CertificateDer<'_>,
        _intermediates: &[rustls::pki_types::CertificateDer<'_>],
        _server_name: &rustls::pki_types::ServerName<'_>,
        _ocsp_response: &[u8],
        _now: rustls::pki_types::UnixTime,
    ) -> Result<rustls::client::danger::ServerCertVerified, rustls::Error> {
        if end_entity.as_ref() == self.der.as_slice() {
            Ok(rustls::client::danger::ServerCertVerified::assertion())
        } else {
            Err(rustls::Error::InvalidCertificate(
                rustls::CertificateError::ApplicationVerificationFailure,
            ))
        }
    }

    fn verify_tls12_signature(
        &self,
        message: &[u8],
        cert: &rustls::pki_types::CertificateDer<'_>,
        dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        rustls::crypto::verify_tls12_signature(
            message,
            cert,
            dss,
            &rustls::crypto::ring::default_provider().signature_verification_algorithms,
        )
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &rustls::pki_types::CertificateDer<'_>,
        dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        rustls::crypto::verify_tls13_signature(
            message,
            cert,
            dss,
            &rustls::crypto::ring::default_provider().signature_verification_algorithms,
        )
    }

    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> {
        rustls::crypto::ring::default_provider()
            .signature_verification_algorithms
            .supported_schemes()
    }
}
