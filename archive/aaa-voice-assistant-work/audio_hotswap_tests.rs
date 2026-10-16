use proptest::prelude::*;
use voice_assistant::audio::{AudioDevice, AudioManager, DeviceChange};

/// Property tests for the hot-swapping decision logic.

/// The specification for `determine_device_change`:
/// - If current device (Some) is present in the available list (by id), return None.
/// - If current device is missing and available is non-empty, return Switched(first available).
/// - If current device is missing and available is empty, return Disconnected.
/// - If current is None, return None (no automatic selection).

proptest! {
    #[test]
    fn test_determine_change_matches_spec(
        current in any::<AudioDevice>(),
        available in prop::collection::vec(any::<AudioDevice>(), 0..10)
    ) {
        let change = AudioManager::determine_device_change(&Some(current), &available);
        let expected = if available.iter().any(|d| d.id == current.id) {
            None
        } else if available.is_empty() {
            Some(DeviceChange::Disconnected)
        } else {
            Some(DeviceChange::Switched(available[0].clone()))
        };
        assert_eq!(change, expected);
    }
}

#[test]
fn test_determine_change_none_current_returns_none() {
    // With available devices, None current yields None.
    let devices = vec![
        AudioDevice { id: "d1".to_string(), name: "dev1".to_string(), sample_rate: 16000, channels: 1 },
        AudioDevice { id: "d2".to_string(), name: "dev2".to_string(), sample_rate: 44100, channels: 2 },
    ];
    assert!(AudioManager::determine_device_change(&None, &devices).is_none());
}

#[test]
fn test_determine_change_empty_available_when_current_missing() {
    let current = AudioDevice { id: "x".to_string(), name: "x".to_string(), sample_rate: 48000, channels: 2 };
    let available: Vec<AudioDevice> = vec![];
    let change = AudioManager::determine_device_change(&Some(current), &available);
    assert_eq!(change, Some(DeviceChange::Disconnected));
}

#[test]
fn test_determine_change_switched_when_current_missing_nonempty_available() {
    let current = AudioDevice { id: "cur".to_string(), name: "cur".to_string(), sample_rate: 48000, channels: 2 };
    let available = vec![
        AudioDevice { id: "first".to_string(), name: "first".to_string(), sample_rate: 16000, channels: 1 },
        AudioDevice { id: "second".to_string(), name: "second".to_string(), sample_rate: 44100, channels: 2 },
    ];
    let change = AudioManager::determine_device_change(&Some(current), &available);
    assert!(matches!(change, Some(DeviceChange::Switched(dev)) if dev.id == "first"));
}
