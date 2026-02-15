use std::sync::Arc;

use quinn::crypto::rustls::QuicServerConfig;
use rustls::pki_types::{CertificateDer, PrivatePkcs8KeyDer};

/// Generate a self-signed TLS certificate and return a quinn ServerConfig
/// plus the DER-encoded certificate bytes (for client pinning).
pub fn generate_self_signed() -> (quinn::ServerConfig, Vec<u8>) {
    let cert = rcgen::generate_simple_self_signed(vec!["localhost".to_string()])
        .expect("failed to generate self-signed cert");

    let cert_der = CertificateDer::from(cert.cert);
    let key_der = PrivatePkcs8KeyDer::from(cert.key_pair.serialize_der());

    let mut rustls_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(vec![cert_der.clone()], key_der.into())
        .expect("failed to build rustls ServerConfig");
    rustls_config.alpn_protocols = vec![b"vox-media/1".to_vec()];

    let quic_config = QuicServerConfig::try_from(rustls_config)
        .expect("failed to create QuicServerConfig");

    let mut server_config = quinn::ServerConfig::with_crypto(Arc::new(quic_config));

    // Enable datagrams (required for media transport)
    let mut transport = quinn::TransportConfig::default();
    transport.max_idle_timeout(Some(
        quinn::IdleTimeout::try_from(std::time::Duration::from_secs(30)).unwrap(),
    ));
    transport.datagram_receive_buffer_size(Some(65535));
    server_config.transport_config(Arc::new(transport));

    let der_bytes = cert_der.to_vec();
    (server_config, der_bytes)
}
