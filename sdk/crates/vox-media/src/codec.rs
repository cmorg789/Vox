//! Opus codec encode/decode wrappers.

use bytes::Bytes;

/// Opus encoder wrapper.
pub struct OpusEncoder {
    inner: opus::Encoder,
    frame_size: usize,
}

impl OpusEncoder {
    /// Create a new Opus encoder at 48kHz mono.
    pub fn new() -> Result<Self, opus::Error> {
        let encoder = opus::Encoder::new(48000, opus::Channels::Mono, opus::Application::Voip)?;
        Ok(OpusEncoder {
            inner: encoder,
            frame_size: 960, // 20ms at 48kHz
        })
    }

    /// Encode a frame of PCM i16 samples to Opus.
    pub fn encode(&mut self, pcm: &[i16]) -> Result<Bytes, opus::Error> {
        let mut output = vec![0u8; 4000]; // max opus frame
        let len = self.inner.encode(pcm, &mut output)?;
        output.truncate(len);
        Ok(Bytes::from(output))
    }

    pub fn frame_size(&self) -> usize {
        self.frame_size
    }
}

/// Opus decoder wrapper.
pub struct OpusDecoder {
    inner: opus::Decoder,
    frame_size: usize,
}

impl OpusDecoder {
    /// Create a new Opus decoder at 48kHz mono.
    pub fn new() -> Result<Self, opus::Error> {
        let decoder = opus::Decoder::new(48000, opus::Channels::Mono)?;
        Ok(OpusDecoder {
            inner: decoder,
            frame_size: 960,
        })
    }

    /// Decode an Opus frame to PCM i16 samples.
    pub fn decode(&mut self, data: &[u8]) -> Result<Vec<i16>, opus::Error> {
        let mut output = vec![0i16; self.frame_size];
        let len = self.inner.decode(data, &mut output, false)?;
        output.truncate(len);
        Ok(output)
    }

    pub fn frame_size(&self) -> usize {
        self.frame_size
    }
}
