fn document_url(document: &str, language: &str) -> Result<String, &'static str> {
    if !["terms", "privacy", "refunds", "payments"].contains(&document)
        || !["ru", "en", "de", "fr", "es", "zh"].contains(&language)
    {
        return Err("DOCUMENT_NOT_ALLOWED");
    }
    let prefix = if language == "ru" {
        String::new()
    } else {
        format!("/{language}")
    };
    Ok(format!(
        "https://prettylisavpn.com{prefix}/legal/{document}/"
    ))
}

#[tauri::command]
pub fn open_public_document(document: String, language: String) -> Result<(), &'static str> {
    super::payment_browser::open_browser(&document_url(&document, &language)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_fixed_localized_documents_no_query_or_credentials() {
        assert_eq!(
            document_url("terms", "ru").unwrap(),
            "https://prettylisavpn.com/legal/terms/"
        );
        assert_eq!(
            document_url("privacy", "en").unwrap(),
            "https://prettylisavpn.com/en/legal/privacy/"
        );
        for invalid in ["../account", "terms?email=x", "https://evil.test"] {
            assert!(document_url(invalid, "ru").is_err());
        }
        assert!(document_url("terms", "../en").is_err());
    }
}
