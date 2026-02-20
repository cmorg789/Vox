use std::sync::Arc;
use std::time::Duration;

use arc_swap::ArcSwap;
use quinn::crypto::rustls::QuicServerConfig;
use rustls::pki_types::{CertificateDer, PrivatePkcs8KeyDer};
use rustls::sign::CertifiedKey;
use tokio_util::sync::CancellationToken;

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

    let mut transport = quinn::TransportConfig::default();
    transport.max_idle_timeout(Some(
        quinn::IdleTimeout::try_from(Duration::from_secs(30)).unwrap(),
    ));
    transport.datagram_receive_buffer_size(Some(65535));
    server_config.transport_config(Arc::new(transport));

    let der_bytes = cert_der.to_vec();
    (server_config, der_bytes)
}

// ---------------------------------------------------------------------------
// Domain cert path: ReloadingCertResolver
// ---------------------------------------------------------------------------

fn load_certified_key(
    cert_path: &str,
    key_path: &str,
) -> Result<CertifiedKey, Box<dyn std::error::Error + Send + Sync>> {
    let cert_pem = std::fs::read(cert_path)?;
    let key_pem = std::fs::read(key_path)?;

    let certs: Vec<CertificateDer<'static>> =
        rustls_pemfile::certs(&mut cert_pem.as_slice()).collect::<Result<Vec<_>, _>>()?;

    if certs.is_empty() {
        return Err("no certificates found in cert file".into());
    }

    let key = rustls_pemfile::private_key(&mut key_pem.as_slice())?
        .ok_or("no private key found in key file")?;

    let signing_key = rustls::crypto::ring::sign::any_supported_type(&key)?;

    Ok(CertifiedKey::new(certs, signing_key))
}

/// A cert resolver that serves the current certificate for every TLS handshake
/// and supports hot-reloading from disk without dropping active connections.
#[derive(Debug)]
pub struct ReloadingCertResolver {
    current: ArcSwap<CertifiedKey>,
    cert_path: String,
    key_path: String,
}

impl ReloadingCertResolver {
    pub fn new(
        cert_path: &str,
        key_path: &str,
    ) -> Result<Arc<Self>, Box<dyn std::error::Error + Send + Sync>> {
        let key = load_certified_key(cert_path, key_path)?;
        Ok(Arc::new(Self {
            current: ArcSwap::from_pointee(key),
            cert_path: cert_path.to_string(),
            key_path: key_path.to_string(),
        }))
    }

    pub fn reload(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let key = load_certified_key(&self.cert_path, &self.key_path)?;
        self.current.store(Arc::new(key));
        Ok(())
    }
}

impl rustls::server::ResolvesServerCert for ReloadingCertResolver {
    fn resolve(
        &self,
        _: rustls::server::ClientHello<'_>,
    ) -> Option<Arc<CertifiedKey>> {
        Some(self.current.load_full())
    }
}

/// Build a quinn ServerConfig using a ReloadingCertResolver.
pub fn build_server_config(resolver: Arc<ReloadingCertResolver>) -> quinn::ServerConfig {
    let mut rustls_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_cert_resolver(resolver);
    rustls_config.alpn_protocols = vec![b"vox-media/1".to_vec()];

    let quic_config = QuicServerConfig::try_from(rustls_config)
        .expect("failed to create QuicServerConfig");

    let mut server_config = quinn::ServerConfig::with_crypto(Arc::new(quic_config));

    let mut transport = quinn::TransportConfig::default();
    transport.max_idle_timeout(Some(
        quinn::IdleTimeout::try_from(Duration::from_secs(30)).unwrap(),
    ));
    transport.datagram_receive_buffer_size(Some(65535));
    server_config.transport_config(Arc::new(transport));

    server_config
}

/// Spawn a background task that reloads the cert from disk once per hour.
/// Existing QUIC connections are unaffected — only new TLS handshakes pick
/// up the refreshed cert.
pub fn spawn_cert_watcher(resolver: Arc<ReloadingCertResolver>, cancel: CancellationToken) {
    tokio::spawn(async move {
        loop {
            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(3600)) => {
                    match resolver.reload() {
                        Ok(()) => tracing::info!("TLS cert hot-reloaded from disk"),
                        Err(e) => tracing::error!("TLS cert reload failed: {}", e),
                    }
                }
                _ = cancel.cancelled() => break,
            }
        }
    });
}
