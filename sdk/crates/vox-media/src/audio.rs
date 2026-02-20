//! cpal audio capture and playback.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;

/// Captured audio samples from the microphone.
pub type AudioSamples = Vec<i16>;

/// Maximum playback buffer size: 2 seconds at 48kHz mono.
const MAX_PLAYBACK_SAMPLES: usize = 48_000 * 2;

/// Start capturing audio from the default input device.
/// Returns a receiver that yields PCM frames.
pub fn start_capture(
    frame_size: usize,
) -> Result<(cpal::Stream, mpsc::UnboundedReceiver<AudioSamples>), Box<dyn std::error::Error>> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or("No input device available")?;

    let config = cpal::StreamConfig {
        channels: 1,
        sample_rate: 48000,
        buffer_size: cpal::BufferSize::Default,
    };

    let (tx, rx) = mpsc::unbounded_channel();
    let buffer: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::with_capacity(frame_size)));
    let buffer_clone = buffer.clone();

    let stream = device.build_input_stream(
        &config,
        move |data: &[f32], _: &cpal::InputCallbackInfo| {
            let mut buf = buffer_clone.lock().unwrap_or_else(|p| p.into_inner());
            for &sample in data {
                buf.push((sample * 32767.0) as i16);
                if buf.len() >= frame_size {
                    let frame = buf.drain(..frame_size).collect();
                    let _ = tx.send(frame);
                }
            }
        },
        |err| {
            tracing::error!("Audio capture error: {}", err);
        },
        None,
    )?;

    stream.play()?;
    Ok((stream, rx))
}

/// Start playback on the default output device.
/// Returns a sender to push PCM frames for playback.
pub fn start_playback(
) -> Result<(cpal::Stream, mpsc::UnboundedSender<AudioSamples>), Box<dyn std::error::Error>> {
    let host = cpal::default_host();
    let device = host
        .default_output_device()
        .ok_or("No output device available")?;

    let config = cpal::StreamConfig {
        channels: 1,
        sample_rate: 48000,
        buffer_size: cpal::BufferSize::Default,
    };

    let (tx, rx) = mpsc::unbounded_channel::<AudioSamples>();
    let rx = Arc::new(Mutex::new(rx));
    let playback_buffer: Arc<Mutex<VecDeque<i16>>> = Arc::new(Mutex::new(VecDeque::new()));
    let pb_clone = playback_buffer.clone();
    let rx_clone = rx.clone();

    let stream = device.build_output_stream(
        &config,
        move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
            let mut buf = pb_clone.lock().unwrap_or_else(|p| p.into_inner());
            // Drain any waiting frames into the buffer
            if let Ok(mut rx) = rx_clone.try_lock() {
                while let Ok(frame) = rx.try_recv() {
                    buf.extend(frame.into_iter());
                }
            }
            // Cap the buffer to prevent unbounded growth
            if buf.len() > MAX_PLAYBACK_SAMPLES {
                let excess = buf.len() - MAX_PLAYBACK_SAMPLES;
                buf.drain(..excess);
                tracing::warn!("Playback buffer overflow, dropped {} oldest samples", excess);
            }
            for sample in data.iter_mut() {
                if let Some(s) = buf.pop_front() {
                    *sample = s as f32 / 32767.0;
                } else {
                    *sample = 0.0;
                }
            }
        },
        |err| {
            tracing::error!("Audio playback error: {}", err);
        },
        None,
    )?;

    stream.play()?;
    Ok((stream, tx))
}
