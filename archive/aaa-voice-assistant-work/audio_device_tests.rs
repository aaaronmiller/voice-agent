use proptest::prelude::*;
use voice_assistant::audio::{AudioDevice, AudioManager};

// Property 33: Audio Device Selection Persistence
// For any valid AudioDevice, after setting it on AudioManager and retrieving,
// the same device should be returned.

proptest! {
    #[test]
    fn test_device_selection_preserves_input_device(
        id in "[a-zA-Z0-9_-]{1,30}",
        name in "[a-zA-Z0-9_-]{1,50}",
        sample_rate in 8000u32..48000,
        channels in 1u16..8
    ) {
        let device = AudioDevice {
            id: id.clone(),
            name: name.clone(),
            sample_rate,
            channels,
        };

        let mut manager = AudioManager::new().expect("Failed to create AudioManager");
        manager.set_input_device(device.clone());

        let retrieved = manager.get_input_device();
        assert!(retrieved.is_some(), "Expected input device to be set");
        assert_eq!(retrieved.unwrap(), &device);
    }

    #[test]
    fn test_device_selection_preserves_output_device(
        id in "[a-zA-Z0-9_-]{1,30}",
        name in "[a-zA-Z0-9_-]{1,50}",
        sample_rate in 8000u32..48000,
        channels in 1u16..8
    ) {
        let device = AudioDevice {
            id: id.clone(),
            name: name.clone(),
            sample_rate,
            channels,
        };

        let mut manager = AudioManager::new().expect("Failed to create AudioManager");
        manager.set_output_device(device.clone());

        let retrieved = manager.get_output_device();
        assert!(retrieved.is_some(), "Expected output device to be set");
        assert_eq!(retrieved.unwrap(), &device);
    }
}

// Property 34: Audio Device Fallback
// If the AudioManager is asked to operate without a selected device,
// it should handle gracefully (e.g., return None or use default).
// This property checks that default state (no device) behaves as expected.

#[test]
fn test_default_audio_manager_has_no_devices() {
    let manager = AudioManager::new().expect("Failed to create AudioManager");
    assert!(manager.get_input_device().is_none());
    assert!(manager.get_output_device().is_none());
}

// Additional property: Setting a device and then clearing (if we had an unset method) would return to None.
// Since there's no explicit unset, we can test that a newly created manager has no devices.
