/// Size of the fixed media frame header in bytes.
pub const HEADER_SIZE: usize = 22;

// Flag bits (byte 3)
pub const FLAG_KEYFRAME: u8 = 0b1000_0000;
pub const FLAG_END_OF_FRAME: u8 = 0b0100_0000;
pub const FLAG_FEC: u8 = 0b0010_0000;
pub const FLAG_MARKER: u8 = 0b0001_0000;
pub const FLAG_HAS_DEP_DESC: u8 = 0b0000_1000;

/// Parsed media frame header (22 bytes fixed).
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
    /// Returns None if the buffer is too short.
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_valid_header() {
        let mut buf = [0u8; 22];
        buf[0] = 1; // version
        buf[1] = 0; // audio
        buf[2] = 1; // opus
        buf[3] = FLAG_KEYFRAME | FLAG_END_OF_FRAME;
        buf[4..8].copy_from_slice(&100u32.to_be_bytes()); // room_id
        buf[8..12].copy_from_slice(&42u32.to_be_bytes()); // user_id
        buf[12..16].copy_from_slice(&1u32.to_be_bytes()); // sequence
        buf[16..20].copy_from_slice(&48000u32.to_be_bytes()); // timestamp
        buf[20] = 0x21; // spatial=2, temporal=1
        buf[21] = 0x80; // dtx=true

        let h = MediaHeader::parse(&buf).unwrap();
        assert_eq!(h.version, 1);
        assert_eq!(h.media_type, 0);
        assert_eq!(h.codec_id, 1);
        assert!(h.is_keyframe());
        assert!(h.is_end_of_frame());
        assert_eq!(h.room_id, 100);
        assert_eq!(h.user_id, 42);
        assert_eq!(h.sequence, 1);
        assert_eq!(h.timestamp, 48000);
        assert_eq!(h.spatial_id, 2);
        assert_eq!(h.temporal_id, 1);
        assert!(h.dtx);
    }

    #[test]
    fn parse_too_short() {
        assert!(MediaHeader::parse(&[0u8; 10]).is_none());
    }
}
