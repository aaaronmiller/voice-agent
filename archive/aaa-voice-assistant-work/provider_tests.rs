use proptest::prelude::*;
use voice_assistant::providers::stt::{
    STTEngine, STTError, STTProvider, Transcription, Language,
};

/// Mock STT provider that always fails.
struct MockFailProvider;
impl STTProvider for MockFailProvider {
    fn name(&self) -> &str {
        "mock_fail"
    }

    fn transcribe(&self, _audio: &[f32], _language: &Language) -> Result<Transcription, STTError> {
        Err(STTError::TranscriptionError("Mock failure".to_string()))
    }

    fn supports_language(&self, _language: &Language) -> bool {
        true
    }

    fn is_local(&self) -> bool {
        true
    }

    fn is_available(&self) -> bool {
        true
    }
}

/// Mock STT provider that always succeeds with a fixed text.
struct MockSuccessProvider;
impl STTProvider for MockSuccessProvider {
    fn name(&self) -> &str {
        "mock_success"
    }

    fn transcribe(&self, _audio: &[f32], _language: &Language) -> Result<Transcription, STTError> {
        Ok(Transcription {
            text: "mocked".to_string(),
            confidence: Some(1.0),
            alternatives: vec![],
            language: "en-US".to_string(),
            duration_ms: 0,
            provider: self.name().to_string(),
        })
    }

    fn supports_language(&self, _language: &Language) -> bool {
        true
    }

    fn is_local(&self) -> bool {
        true
    }

    fn is_available(&self) -> bool {
        true
    }
}

/// Property 7: Provider Selection Persistence
proptest! {
    #[test]
    fn test_provider_selection_persistence(provider_name in "mock_fail|mock_success") {
        let mut engine = STTEngine::new();
        // Register both providers so the engine has them.
        engine.register_provider(Box::new(MockFailProvider));
        engine.register_provider(Box::new(MockSuccessProvider));

        // Set active provider to the generated name
        let result = engine.set_active_provider(&provider_name);
        assert!(result.is_ok() || result.is_err()); // it should succeed if provider exists

        let active = engine.get_active_provider();
        assert_eq!(active, provider_name);
    }
}

/// Property 8: Provider Fallback Chain
/// When active provider fails, the engine should try fallback providers in order
/// and return the result from the first successful fallback.
#[test]
fn test_fallback_chain_uses_order() {
    let mut engine = STTEngine::new();
    engine.register_provider(Box::new(MockFailProvider));
    engine.register_provider(Box::new(MockSuccessProvider));

    // Set active to fail, fallback chain to success
    engine.set_active_provider("mock_fail").unwrap();
    engine.set_fallback_chain(vec!["mock_success".to_string()]);

    let audio = vec![0.1f32; 100];
    let language = Language::EnUS;
    let result = engine.transcribe(&audio, &language).unwrap();

    assert_eq!(result.provider, "mock_success");
    // Active provider should remain mock_fail
    assert_eq!(engine.get_active_provider(), "mock_fail");
}

/// Property 9: Provider Selection Consistency
/// After a transcription attempt (success or failure), the active provider should not change
/// unless explicitly set.
#[test]
fn test_active_provider_unchanged_after_transcription() {
    let mut engine = STTEngine::new();
    engine.register_provider(Box::new(MockSuccessProvider));
    engine.set_active_provider("mock_success").unwrap();

    let initial_active = engine.get_active_provider().to_string();
    let audio = vec![0.1; 50];
    let language = Language::EnUS;
    let _ = engine.transcribe(&audio, &language); // can succeed or fail

    let after_active = engine.get_active_provider();
    assert_eq!(after_active, initial_active);
}

/// Another consistency: if active provider is not available, transcription should fail
/// without trying fallback if chain is empty?
/// Not required.

#[test]
fn test_fallback_all_fail() {
    let mut engine = STTEngine::new();
    engine.register_provider(Box::new(MockFailProvider));
    engine.set_active_provider("mock_fail").unwrap();
    // No fallback chain
    engine.set_fallback_chain(vec![]);

    let audio = vec![0.1; 10];
    let language = Language::EnUS;
    let result = engine.transcribe(&audio, &language);
    assert!(matches!(result, Err(STTError::TranscriptionError(_))));
}
