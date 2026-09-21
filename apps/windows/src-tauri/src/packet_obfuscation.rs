//! Keyless framing, NOT encryption or authentication. VPN ciphertext stays opaque.
use serde::Deserialize;

pub(crate) const WRAPPER_OVERHEAD: usize = 8;
const MAGIC: &[u8; 4] = b"PLPW";

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum PacketError {
    Malformed,
    Oversized,
}

pub(crate) trait ObfuscationProvider: Send + 'static {
    fn encode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError>;
    fn decode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError>;
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ObfuscationConfig {
    pub mode: String,
    pub version: u8,
    pub max_datagram_size: usize,
}

pub(crate) fn provider(
    config: &ObfuscationConfig,
) -> Result<Box<dyn ObfuscationProvider>, PacketError> {
    if !(9..=65_507).contains(&config.max_datagram_size) {
        return Err(PacketError::Oversized);
    }
    match (config.mode.as_str(), config.version) {
        ("NONE", 0) => Ok(Box::new(NoObfuscation(config.max_datagram_size))),
        ("SIMPLE_PACKET_WRAPPER_V1", 1) => {
            Ok(Box::new(SimplePacketWrapper(config.max_datagram_size)))
        }
        // TLS records belong to a mature TLS runtime, never this packet codec.
        _ => Err(PacketError::Malformed),
    }
}

struct NoObfuscation(usize);
impl ObfuscationProvider for NoObfuscation {
    fn encode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError> {
        if packet.is_empty() {
            return Err(PacketError::Malformed);
        }
        if packet.len() > self.0 {
            return Err(PacketError::Oversized);
        }
        Ok(packet.to_vec())
    }
    fn decode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError> {
        self.encode(packet)
    }
}

struct SimplePacketWrapper(usize);
impl ObfuscationProvider for SimplePacketWrapper {
    fn encode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError> {
        if packet.is_empty() {
            return Err(PacketError::Malformed);
        }
        if packet.len() > self.0 - WRAPPER_OVERHEAD {
            return Err(PacketError::Oversized);
        }
        let mut frame = Vec::with_capacity(packet.len() + WRAPPER_OVERHEAD);
        frame.extend_from_slice(MAGIC);
        frame.extend_from_slice(&[1, 0]);
        frame.extend_from_slice(&(packet.len() as u16).to_be_bytes());
        frame.extend(packet.iter().map(|byte| byte ^ 0xa5));
        Ok(frame)
    }
    fn decode(&self, frame: &[u8]) -> Result<Vec<u8>, PacketError> {
        if frame.len() > self.0 {
            return Err(PacketError::Oversized);
        }
        if frame.len() <= WRAPPER_OVERHEAD
            || &frame[..4] != MAGIC
            || frame[4..6] != [1, 0]
            || usize::from(u16::from_be_bytes([frame[6], frame[7]]))
                != frame.len() - WRAPPER_OVERHEAD
        {
            return Err(PacketError::Malformed);
        }
        Ok(frame[WRAPPER_OVERHEAD..]
            .iter()
            .map(|byte| byte ^ 0xa5)
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn symmetry_large_packets_mtu_and_cross_language_vector() {
        for size in [1, 148, 1280, 1312, 1392, 4096, 65499] {
            let codec = SimplePacketWrapper(65507);
            let packet = vec![42; size];
            assert_eq!(
                codec.decode(&codec.encode(&packet).unwrap()).unwrap(),
                packet
            );
        }
        let codec = SimplePacketWrapper(1400);
        assert_eq!(
            codec.encode(&[0, 1, 255]).unwrap(),
            [80, 76, 80, 87, 1, 0, 0, 3, 165, 164, 90]
        );
        assert_eq!(codec.encode(&vec![0; 1392]).unwrap().len(), 1400);
        assert_eq!(codec.encode(&vec![0; 1393]), Err(PacketError::Oversized));
        assert_eq!(NoObfuscation(1400).encode(&[1, 2, 3]).unwrap(), [1, 2, 3]);
    }
    #[test]
    fn malformed_packets_and_loss_do_not_desynchronize() {
        let codec = SimplePacketWrapper(1400);
        for packet in [
            vec![],
            vec![0; 9],
            b"PLPW\x02\x00\x00\x01x".to_vec(),
            b"PLPW\x01\x01\x00\x01x".to_vec(),
            b"PLPW\x01\x00\x00\x02x".to_vec(),
        ] {
            assert!(codec.decode(&packet).is_err());
        }
        for index in 0..100u8 {
            let packet = codec.encode(&[index]).unwrap();
            if index % 3 == 0 {
                continue;
            } // deterministic packet loss
            assert_eq!(codec.decode(&packet).unwrap(), [index]);
            assert_eq!(SimplePacketWrapper(1400).decode(&packet).unwrap(), [index]);
            // reconnect
        }
    }
    #[test]
    fn unsupported_versions_and_tls_are_rejected() {
        for (mode, version) in [("TLS_TRANSPORT", 1), ("SIMPLE_PACKET_WRAPPER_V1", 2)] {
            assert!(provider(&ObfuscationConfig {
                mode: mode.into(),
                version,
                max_datagram_size: 1400
            })
            .is_err());
        }
    }
}
