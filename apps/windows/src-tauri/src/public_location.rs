use serde::{Deserialize, Serialize};
use std::{net::IpAddr, time::Duration};
use tauri_plugin_http::reqwest::{redirect::Policy, Client, Request};

const UNAVAILABLE: &str = "PUBLIC_LOCATION_UNAVAILABLE";
const MAX_BODY: usize = 16 * 1024;

#[derive(Deserialize, Serialize)]
pub struct Observation {
    success: bool,
    ip: String,
    country_code: Option<String>,
    city: Option<String>,
}

fn request() -> Result<(Client, Request), &'static str> {
    // No webview Origin, account headers, cookie jar or arbitrary destination.
    let client = Client::builder()
        .timeout(Duration::from_secs(8))
        .connect_timeout(Duration::from_secs(5))
        .redirect(Policy::none())
        .user_agent(concat!("PrettyLisaVPN/", env!("CARGO_PKG_VERSION")))
        .build()
        .map_err(|_| UNAVAILABLE)?;
    let request = client
        .get("https://ipwho.is/")
        .header("Accept", "application/json")
        .build()
        .map_err(|_| UNAVAILABLE)?;
    Ok((client, request))
}

fn parse_observation(body: &[u8]) -> Result<Observation, &'static str> {
    if body.len() > MAX_BODY {
        return Err(UNAVAILABLE);
    }
    let value: Observation = serde_json::from_slice(body).map_err(|_| UNAVAILABLE)?;
    if !value.success || value.ip.parse::<IpAddr>().is_err() {
        return Err(UNAVAILABLE);
    }
    Ok(value)
}

#[tauri::command]
pub async fn get_public_location() -> Result<Observation, &'static str> {
    let (client, request) = request()?;
    let mut response = client.execute(request).await.map_err(|_| UNAVAILABLE)?;
    if !response.status().is_success()
        || response.content_length().is_some_and(|size| size > MAX_BODY as u64)
    {
        return Err(UNAVAILABLE);
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| UNAVAILABLE)? {
        if body.len() + chunk.len() > MAX_BODY {
            return Err(UNAVAILABLE);
        }
        body.extend_from_slice(&chunk);
    }
    parse_observation(&body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_request_does_not_send_browser_or_account_headers() {
        let (_, request) = request().unwrap();
        assert_eq!(request.url().as_str(), "https://ipwho.is/");
        assert_eq!(request.method(), "GET");
        for header in ["origin", "authorization", "cookie"] {
            assert!(!request.headers().contains_key(header));
        }
    }

    #[test]
    fn rejects_provider_failures_invalid_addresses_and_oversized_responses() {
        let valid = br#"{"success":true,"ip":"203.0.113.42"}"#;
        assert!(parse_observation(valid).is_ok());
        assert!(parse_observation(br#"{"success":true,"ip":"2001:db8::1"}"#).is_ok());
        assert!(parse_observation(br#"{"success":false,"ip":"203.0.113.42"}"#).is_err());
        assert!(parse_observation(br#"{"success":true,"ip":"999.1.1.1"}"#).is_err());
        assert!(parse_observation(&vec![b' '; MAX_BODY + 1]).is_err());
    }
}
