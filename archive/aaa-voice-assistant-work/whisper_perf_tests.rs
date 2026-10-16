use voice_assistant::providers::stt::{WhisperCppProvider, Language, STTProvider};
use std::time::{Duration, Instant};

/// Performance tests for WhisperCppProvider.

/// Helper: Determine if the whisper.cpp binary is likely available.
fn is_whisper_available() -> bool {
    // Check environment for binary path
    if let Ok(bin) = std::env::var("WHISPER_CPP_BINARY") {
        if let Ok(true) = std::path::Path::new(&bin).exists() {
            return true;
        }
    }
    // Check default binary in PATH
    if let Ok(path) = which::which("whisper-cpp") {
        return path.exists();
    }
    false
}

/// Helper: Determine if a model file exists based on env var.
fn has_model() -> bool {
    if let Ok(model) = std::env::var("WHISPER_MODEL_PATH") {
        return std::path::Path::new(&model).exists();
    }
    false
}

/// Simple sanity performance test: ensure that transcribing 1 second of silence
/// does not take unreasonably long (e.g., > 30 seconds), which would indicate
/// misconfiguration or hung process. Also ensure it completes successfully if
/// binary+model available.
#[test]
fn test_whisper_cpp_transcribe_performance() {
    // Skip test if prerequisites not met
    if !is_whisper_available() || !has_model() {
        eprintln!("Skipping Whisper.cpp perf test: binary or model not found");
        return;
    }

    let model_path = std::env::var("WHISPER_MODEL_PATH").unwrap();
    let binary_path = std::env::var("WHISPER_CPP_BINARY").ok();

    let provider = WhisperCppProvider::new()
        .with_model(&model_path)
        .with_binary_path(binary_path.as_deref().unwrap_or("whisper-cpp"));

    // If provider is not available according to its is_available (maybe model not loaded?), skip.
    if !provider.is_available() {
        eprintln!("Skipping Whisper.cpp perf test: provider not available");
        return;
    }

    // Generate 1 second of silence audio at 16kHz
    let sample_rate = 16000;
    let num_samples = sample_rate;
    let audio = vec![0.0f32; num_samples];
    let language = Language::EnUS;

    let start = Instant::now();
    let result = provider.transcribe(&audio, &language);
    let elapsed = start.elapsed();

    // We consider a generous threshold: 30 seconds
    let threshold = Duration::from_secs(30);

    assert!(
        elapsed < threshold,
        "Transcribe took too long: {:?} (threshold {:?})",
        elapsed,
        threshold
    );

    // Also ensure no error occurred (if any, we'll panic)
    let transcription = result.expect("Transcription failed");
    assert!(!transcription.text.is_empty(), "Transcription text was empty");
}

/// More detailed property: transcribe time scales roughly linearly with audio length.
/// For brevity, we test two lengths: 1 second and 5 seconds. Expect 5x length yields
/// not more than 5.5x time (with tolerance for overhead).
#[test]
fn test_whisper_cpp_transcribe_scaling() {
    if !is_whisper_available() || !has_model() {
        eprintln!("Skipping Whisper.cpp scaling test: binary or model not found");
        return;
    }

    let model_path = std::env::var("WHISPER_MODEL_PATH").unwrap();
    let binary_path = std::env::var("WHISPER_CPP_BINARY").ok();

    let provider = WhisperCppProvider::new()
        .with_model(&model_path)
        .with_binary_path(binary_path.as_deref().unwrap_or("whisper-cpp"));

    if !provider.is_available() {
        eprintln!("Skipping Whisper.cpp scaling test: provider not available");
        return;
    }

    let sample_rate = 16000;
    let lengths = [sample_rate, sample_rate * 5]; // 1s, 5s
    let mut times = Vec::new();

    for &len in &lengths {
        let audio = vec![0.0f32; len];
        let language = Language::EnUS;

        let start = Instant::now();
        // ignore errors for brevity
        let _ = provider.transcribe(&audio, &language);
        let elapsed = start.elapsed();
        times.push(elapsed);
    }

    // 5s should be no more than 5.5x the 1s time (some overhead)
    let ratio = times[1].as_secs_f32() / times[0].as_secs_f32();
    assert!(
        ratio <= 5.5,
        "5s audio took too long relative to 1s: {}x",
        ratio
    );
}
