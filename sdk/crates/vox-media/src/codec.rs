//! Opus and AV1 codec encode/decode wrappers.

use bytes::Bytes;
use rav1e::prelude::*;

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

// ---------------------------------------------------------------------------
// AV1 encoder (rav1e)
// ---------------------------------------------------------------------------

/// An encoded AV1 packet from the encoder.
pub struct EncodedPacket {
    pub data: Vec<u8>,
    pub is_keyframe: bool,
    pub timestamp: u64,
}

/// AV1 encoder using rav1e with low-latency settings.
pub struct Av1Encoder {
    ctx: Context<u8>,
    width: usize,
    height: usize,
    frame_count: u64,
}

impl Av1Encoder {
    /// Create a new AV1 encoder.
    ///
    /// * `width`, `height` — frame dimensions (must be even)
    /// * `fps` — frames per second
    /// * `bitrate_kbps` — target bitrate in kbit/s
    pub fn new(width: usize, height: usize, fps: u32, bitrate_kbps: u32) -> Result<Self, String> {
        let cfg = Config::new()
            .with_encoder_config(EncoderConfig {
                width,
                height,
                bit_depth: 8,
                chroma_sampling: ChromaSampling::Cs420,
                chroma_sample_position: ChromaSamplePosition::Unknown,
                time_base: Rational { num: 1, den: fps as u64 },
                low_latency: true,
                bitrate: bitrate_kbps as i32,
                min_key_frame_interval: 0,
                max_key_frame_interval: fps as u64 * 10,
                speed_settings: SpeedSettings::from_preset(10),
                ..Default::default()
            })
            .with_threads(2);

        let ctx: Context<u8> = cfg.new_context().map_err(|e| format!("rav1e context: {e}"))?;

        Ok(Av1Encoder {
            ctx,
            width,
            height,
            frame_count: 0,
        })
    }

    /// Encode raw I420 planes into AV1 packets.
    ///
    /// `y`, `u`, `v` must be the correct sizes for the configured resolution:
    /// - Y: width * height
    /// - U, V: (width/2) * (height/2)
    pub fn encode(&mut self, y: &[u8], u: &[u8], v: &[u8]) -> Result<Vec<EncodedPacket>, String> {
        let mut frame = self.ctx.new_frame();

        frame.planes[0].copy_from_raw_u8(y, self.width, 1);
        frame.planes[1].copy_from_raw_u8(u, self.width / 2, 1);
        frame.planes[2].copy_from_raw_u8(v, self.width / 2, 1);

        self.ctx.send_frame(frame).map_err(|e| format!("rav1e send_frame: {e}"))?;
        self.frame_count += 1;

        self.drain_packets()
    }

    /// Flush the encoder (call on shutdown to drain remaining packets).
    pub fn flush(&mut self) -> Result<Vec<EncodedPacket>, String> {
        self.ctx.flush();
        self.drain_packets()
    }

    fn drain_packets(&mut self) -> Result<Vec<EncodedPacket>, String> {
        let mut packets = Vec::new();
        loop {
            match self.ctx.receive_packet() {
                Ok(pkt) => {
                    packets.push(EncodedPacket {
                        data: pkt.data,
                        is_keyframe: pkt.frame_type == FrameType::KEY,
                        timestamp: pkt.input_frameno,
                    });
                }
                Err(EncoderStatus::Encoded) => continue,
                Err(EncoderStatus::NeedMoreData) => break,
                Err(EncoderStatus::LimitReached) => break,
                Err(e) => return Err(format!("rav1e receive_packet: {e}")),
            }
        }
        Ok(packets)
    }
}

// ---------------------------------------------------------------------------
// AV1 decoder (dav1d)
// ---------------------------------------------------------------------------

/// A decoded video frame (RGBA).
pub struct DecodedFrame {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

/// AV1 decoder using dav1d.
pub struct Av1Decoder {
    decoder: dav1d::Decoder,
}

impl Av1Decoder {
    /// Create a new AV1 decoder with 2 threads and minimal frame delay.
    pub fn new() -> Result<Self, String> {
        let mut settings = dav1d::Settings::new();
        settings.set_n_threads(2);
        settings.set_max_frame_delay(1);

        let decoder = dav1d::Decoder::with_settings(&settings)
            .map_err(|e| format!("dav1d init: {e}"))?;
        Ok(Av1Decoder { decoder })
    }

    /// Feed encoded AV1 data and try to get a decoded frame.
    pub fn decode(&mut self, data: &[u8]) -> Result<Option<DecodedFrame>, String> {
        self.decoder
            .send_data(data.to_vec(), None, None, None)
            .map_err(|e| format!("dav1d send_data: {e}"))?;

        match self.decoder.get_picture() {
            Ok(pic) => {
                let w = pic.width();
                let h = pic.height();
                let rgba = yuv_picture_to_rgba(&pic, w, h);
                Ok(Some(DecodedFrame {
                    width: w,
                    height: h,
                    rgba,
                }))
            }
            Err(dav1d::Error::Again) => Ok(None),
            Err(e) => Err(format!("dav1d get_picture: {e}")),
        }
    }
}

/// Convert a dav1d I420 picture to RGBA.
fn yuv_picture_to_rgba(pic: &dav1d::Picture, w: u32, h: u32) -> Vec<u8> {
    use dav1d::PlanarImageComponent;

    let y_plane = pic.plane(PlanarImageComponent::Y);
    let u_plane = pic.plane(PlanarImageComponent::U);
    let v_plane = pic.plane(PlanarImageComponent::V);

    let y_stride = pic.stride(PlanarImageComponent::Y) as usize;
    let u_stride = pic.stride(PlanarImageComponent::U) as usize;
    let v_stride = pic.stride(PlanarImageComponent::V) as usize;

    let w = w as usize;
    let h = h as usize;
    let mut rgba = vec![255u8; w * h * 4];

    for row in 0..h {
        for col in 0..w {
            let y_val = y_plane[row * y_stride + col] as f32;
            let u_val = u_plane[(row / 2) * u_stride + (col / 2)] as f32 - 128.0;
            let v_val = v_plane[(row / 2) * v_stride + (col / 2)] as f32 - 128.0;

            let r = (y_val + 1.402 * v_val).clamp(0.0, 255.0) as u8;
            let g = (y_val - 0.344136 * u_val - 0.714136 * v_val).clamp(0.0, 255.0) as u8;
            let b = (y_val + 1.772 * u_val).clamp(0.0, 255.0) as u8;

            let idx = (row * w + col) * 4;
            rgba[idx] = r;
            rgba[idx + 1] = g;
            rgba[idx + 2] = b;
        }
    }

    rgba
}
