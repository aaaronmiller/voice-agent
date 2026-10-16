use proptest::prelude::*;
use voice_assistant::clipboard::ClipboardManager;
use arboard::Clipboard;

/// Property 40: Clipboard round-trip
/// For any given text content, saving the clipboard state and then restoring it
/// after modifying the clipboard should return the original content.
proptest! {
    #[test]
    fn test_clipboard_roundtrip(text in "[\\x00-\\x7F]{1,200}") {
        // Skip text containing null character as it may cause issues.
        if text.contains('\0') {
            return Ok(());
        }

        let mut clipboard = Clipboard::new().expect("Failed to get clipboard");
        clipboard.set_text(text.clone()).expect("Failed to set clipboard text");

        let mut manager = ClipboardManager::new();
        manager.save().expect("Save failed");

        // Modify clipboard
        let new_text = format!("modified_{}", text);
        clipboard.set_text(new_text.clone()).expect("Failed to modify clipboard");

        manager.restore().expect("Restore failed");

        // Verify original text is restored
        let result = clipboard.get_text().expect("Failed to get clipboard text");
        assert_eq!(result, text);
    }
}

/// Unit tests for clipboard edge cases.

#[test]
fn test_save_with_empty_clipboard() {
    // Ensure clipboard is empty first.
    let mut clipboard = Clipboard::new().unwrap();
    clipboard.set_text("").unwrap(); // empty string
    // Confirm empty string is actually the text.
    assert_eq!(clipboard.get_text().unwrap(), "");

    let mut manager = ClipboardManager::new();
    // Save empty clipboard: should store None? Actually get_text on empty string returns Ok("") not Err.
    // According to arboard, get_text returns Ok(Some(String)) if there is text, even empty? It returns Err if no data.
    // Let's test: if clipboard contains empty string, get_text likely returns Ok("") which is Some(""). So saved_content will be Some("").
    // The spec: "Handle empty clipboard gracefully". We'll treat empty as valid.
    manager.save().unwrap();
    // saved_content should be Some("")
    // Restore will set clipboard to "".
    manager.restore().unwrap();
    let result = clipboard.get_text().unwrap();
    assert_eq!(result, "");
}

#[test]
fn test_save_after_failed_get() {
    // Simulate a situation where clipboard does not contain text (e.g., only non-text data).
    // Hard to simulate without raw control. Instead, we test the internal state: if get_text fails,
    // saved_content becomes None. But our ClipboardManager doesn't expose that. So we can only
    // test behavior: after creating manager without save, restore does nothing.
    let mut manager = ClipboardManager::new();
    // Without any save, saving hasn't happened. Restore should be a no-op and return Ok.
    let result = manager.restore();
    assert!(result.is_ok());
}

#[test]
fn test_multiple_save_overwrites() {
    let mut clipboard = Clipboard::new().unwrap();
    let mut manager = ClipboardManager::new();

    clipboard.set_text("first").unwrap();
    manager.save().unwrap();

    clipboard.set_text("second").unwrap();
    manager.save().unwrap(); // overwrite

    clipboard.set_text("third").unwrap();

    // Restore should bring back "second" (the last saved).
    manager.restore().unwrap();
    assert_eq!(clipboard.get_text().unwrap(), "second");
}

#[test]
fn test_large_content_roundtrip() {
    // Generate a moderately large string (1MB of 'A's)
    let size = 1024 * 1024;
    let text = "A".repeat(size);

    let mut clipboard = Clipboard::new().unwrap();
    clipboard.set_text(&text).expect("Failed to set large text");

    let mut manager = ClipboardManager::new();
    manager.save().expect("Save failed");

    // Modify
    clipboard.set_text("other").unwrap();

    manager.restore().expect("Restore failed");

    let result = clipboard.get_text().expect("Failed to get large text");
    assert_eq!(result.len(), size);
    assert!(result.starts_with("A"));
}
