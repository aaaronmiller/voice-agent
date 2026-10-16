use proptest::prelude::*;
use serde_json::Value;
use std::collections::HashMap;
use tempfile::TempDir;
use std::fs;

use crate::config::{ConfigurationStore, Settings, STTConfig, TTSConfig, LLMConfig, HotkeyConfig, AudioConfig};

// Property 30: Configuration Round-Trip
// For any configuration setting, after saving, restarting the application, and loading,
// the setting should have the same value.

proptest! {
    #[test]
    fn test_config_round_trip_preserves_stt_settings(
        provider in "[a-zA-Z0-9_-]{1,20}",
        fallback in prop::collection::vec("[a-zA-Z0-9_-]{1,20}", 0..3),
        language in "[a-z]{2}(-[A-Z]{2})?",
        streaming in proptest::bool::ANY
    ) {
        let mut settings = Settings::default();
        settings.stt = STTConfig {
            provider: provider.clone(),
            fallback_providers: fallback.clone(),
            language: language.clone(),
            streaming,
        };

        // Save and load in same instance (simulates persistence)
        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        // Save to disk
        let save_result = config_store.save();
        assert!(save_result.is_ok(), "Save should succeed");

        // Load from disk
        let loaded = ConfigurationStore::load().unwrap();

        // Verify all fields match
        assert_eq!(loaded.get().stt.provider, provider);
        assert_eq!(loaded.get().stt.fallback_providers, fallback);
        assert_eq!(loaded.get().stt.language, language);
        assert_eq!(loaded.get().stt.streaming, streaming);
    }

    #[test]
    fn test_config_round_trip_preserves_tts_settings(
        provider in "[a-zA-Z0-9_-]{1,20}",
        voice in "[a-zA-Z0-9_-]{1,30}",
        volume in 0.0f32..1.0,
        speed in 0.1f32..2.0
    ) {
        let mut settings = Settings::default();
        settings.tts = TTSConfig {
            provider: provider.clone(),
            voice: voice.clone(),
            volume,
            speed,
        };

        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        config_store.save().unwrap();
        let loaded = ConfigurationStore::load().unwrap();

        assert_eq!(loaded.get().tts.provider, provider);
        assert_eq!(loaded.get().tts.voice, voice);
        assert!((loaded.get().tts.volume - volume).abs() < 1e-6);
        assert!((loaded.get().tts.speed - speed).abs() < 1e-6);
    }

    #[test]
    fn test_config_round_trip_preserves_llm_settings(
        provider in "[a-zA-Z0-9_-]{1,20}",
        model in "[a-zA-Z0-9_-]{1,30}",
        temperature in 0.0f32..1.0,
        max_tokens in 1u32..4096
    ) {
        let mut settings = Settings::default();
        settings.llm = LLMConfig {
            provider: provider.clone(),
            model: model.clone(),
            temperature,
            max_tokens,
        };

        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        config_store.save().unwrap();
        let loaded = ConfigurationStore::load().unwrap();

        assert_eq!(loaded.get().llm.provider, provider);
        assert_eq!(loaded.get().llm.model, model);
        assert!((loaded.get().llm.temperature - temperature).abs() < 1e-6);
        assert_eq!(loaded.get().llm.max_tokens, max_tokens);
    }

    #[test]
    fn test_config_round_trip_preserves_hotkeys(
        ptt in "[a-zA-Z0-9+^]{1,20}",
        paste_last in "[a-zA-Z0-9+^]{1,20}",
        toggle_wake_word in "[a-zA-Z0-9+^]{1,20}",
        toggle_cleanup in "[a-zA-Z0-9+^]{1,20}",
        open_history in "[a-zA-Z0-9+^]{1,20}",
        open_settings in "[a-zA-Z0-9+^]{1,20}",
        cancel_recording in "[a-zA-Z0-9+^]{1,20}"
    ) {
        let mut settings = Settings::default();
        settings.hotkeys = HotkeyConfig {
            ptt: ptt.clone(),
            paste_last: paste_last.clone(),
            toggle_wake_word: toggle_wake_word.clone(),
            toggle_cleanup: toggle_cleanup.clone(),
            open_history: open_history.clone(),
            open_settings: open_settings.clone(),
            cancel_recording: cancel_recording.clone(),
        };

        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        config_store.save().unwrap();
        let loaded = ConfigurationStore::load().unwrap();

        assert_eq!(loaded.get().hotkeys.ptt, ptt);
        assert_eq!(loaded.get().hotkeys.paste_last, paste_last);
        assert_eq!(loaded.get().hotkeys.toggle_wake_word, toggle_wake_word);
        assert_eq!(loaded.get().hotkeys.toggle_cleanup, toggle_cleanup);
        assert_eq!(loaded.get().hotkeys.open_history, open_history);
        assert_eq!(loaded.get().hotkeys.open_settings, open_settings);
        assert_eq!(loaded.get().hotkeys.cancel_recording, cancel_recording);
    }

    #[test]
    fn test_config_round_trip_preserves_audio_settings(
        input_device in "[a-zA-Z0-9_-]{1,30}",
        output_device in "[a-zA-Z0-9_-]{1,30}",
        noise_suppression in proptest::bool::ANY,
        auto_gain_control in proptest::bool::ANY,
        silence_threshold in 0.0f32..0.5
    ) {
        let mut settings = Settings::default();
        settings.audio = AudioConfig {
            input_device: input_device.clone(),
            output_device: output_device.clone(),
            noise_suppression,
            auto_gain_control,
            silence_threshold,
        };

        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        config_store.save().unwrap();
        let loaded = ConfigurationStore::load().unwrap();

        assert_eq!(loaded.get().audio.input_device, input_device);
        assert_eq!(loaded.get().audio.output_device, output_device);
        assert_eq!(loaded.get().audio.noise_suppression, noise_suppression);
        assert_eq!(loaded.get().audio.auto_gain_control, auto_gain_control);
        assert!((loaded.get().audio.silence_threshold - silence_threshold).abs() < 1e-6);
    }

    #[test]
    fn test_config_round_trip_preserves_all_other_settings(
        wake_word in "[a-zA-Z0-9 ]{1,30}",
        wake_word_enabled in proptest::bool::ANY,
        transcription_mode in prop::one_of!("insert", "replace", "append"),
        auto_capitalization in proptest::bool::ANY,
        auto_punctuation in proptest::bool::ANY,
        transcription_cleanup in proptest::bool::ANY,
        cleanup_prompt in "[\\w\\s.,!?-]{0,200}",
        history_retention in 1u32..100000,
        theme in prop::one_of!("light", "dark", "system")
    ) {
        let mut settings = Settings::default();
        settings.wake_word = wake_word.clone();
        settings.wake_word_enabled = wake_word_enabled;
        settings.transcription_mode = transcription_mode.to_string();
        settings.auto_capitalization = auto_capitalization;
        settings.auto_punctuation = auto_punctuation;
        settings.transcription_cleanup = transcription_cleanup;
        settings.cleanup_prompt = cleanup_prompt.clone();
        settings.history_retention = history_retention;
        settings.theme = theme.to_string();

        let config_store = ConfigurationStore {
            settings: settings.clone(),
            config_path: TempDir::new().unwrap().path().join("test_config.json"),
        };

        config_store.save().unwrap();
        let loaded = ConfigurationStore::load().unwrap();

        assert_eq!(loaded.get().wake_word, wake_word);
        assert_eq!(loaded.get().wake_word_enabled, wake_word_enabled);
        assert_eq!(loaded.get().transcription_mode, transcription_mode);
        assert_eq!(loaded.get().auto_capitalization, auto_capitalization);
        assert_eq!(loaded.get().auto_punctuation, auto_punctuation);
        assert_eq!(loaded.get().transcription_cleanup, transcription_cleanup);
        assert_eq!(loaded.get().cleanup_prompt, cleanup_prompt);
        assert_eq!(loaded.get().history_retention, history_retention);
        assert_eq!(loaded.get().theme, theme);
    }

    #[test]
    fn test_config_handles_missing_file_by_creating_defaults() {
        let temp_dir = TempDir::new().unwrap();
        let config_path = temp_dir.path().join("nonexistent_config.json");

        // Ensure file doesn't exist
        assert!(!config_path.exists());

        // Load should create default config
        let result = ConfigurationStore::load();
        assert!(result.is_ok());

        let config_store = result.unwrap();
        assert!(config_path.exists()); // File should be created

        // Verify defaults are present
        let settings = config_store.get();
        assert!(!settings.stt.provider.is_empty());
        assert!(!settings.tts.provider.is_empty());
        assert!(!settings.llm.provider.is_empty());
    }

    #[test]
    fn test_config_load_handles_corrupted_json() {
        let temp_dir = TempDir::new().unwrap();
        let config_path = temp_dir.path().join("corrupted_config.json");

        // Write invalid JSON
        fs::write(&config_path, "not valid json{").unwrap();

        // Load should fail gracefully
        let result = ConfigurationStore::load();
        assert!(result.is_err());
    }

    #[test]
    fn test_config_save_creates_parent_directories() {
        let temp_dir = TempDir::new().unwrap();
        // Use a nested path that doesn't exist
        let config_path = temp_dir.path().join("deeply").join("nested").join("config.json");

        let mut settings = Settings::default();
        settings.stt.provider = "test".to_string();

        let config_store = ConfigurationStore {
            settings,
            config_path: config_path.clone(),
        };

        // Save should create parent directories
        let result = config_store.save();
        assert!(result.is_ok(), "Save should succeed and create directories");
        assert!(config_path.exists(), "Config file should exist");
    }
}
