use proptest::prelude::*;
use voice_assistant::audio::AudioPreprocessor;

// Property 35: Audio Preprocessing Defaults
// The default AudioPreprocessor should have sensible defaults.

#[test]
fn test_default_audio_preprocessor_values() {
    let preproc = AudioPreprocessor::default();
    assert!(!preproc.noise_suppression);
    assert!(!preproc.auto_gain_control);
    assert_eq!(preproc.silence_threshold, 0.0);
}

// Property for any arbitrary values, struct should store them correctly.

proptest! {
    #[test]
    fn test_audio_preprocessor_arbitrary_values(
        noise_suppression in any::<bool>(),
        auto_gain_control in any::<bool>(),
        silence_threshold in 0.0..1.0
    ) {
        let preproc = AudioPreprocessor {
            noise_suppression,
            auto_gain_control,
            silence_threshold,
        };
        assert_eq!(preproc.noise_suppression, noise_suppression);
        assert_eq!(preproc.auto_gain_control, auto_gain_control);
        assert_eq!(preproc.silence_threshold, silence_threshold);
    }
}
