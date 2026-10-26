use serde::{Deserialize, Serialize};
use std::{future::Future, net::IpAddr, time::Duration};
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

#[derive(Clone, Copy, Debug, PartialEq)]
enum Provider {
    IpWho,
    IpInfo,
}

impl Provider {
    fn url(self) -> &'static str {
        match self {
            Self::IpWho => "https://ipwho.is/",
            Self::IpInfo => "https://ipinfo.io/json",
        }
    }
}

fn request(provider: Provider) -> Result<(Client, Request), &'static str> {
    // No webview Origin, account headers, cookie jar or arbitrary destination.
    let client = Client::builder()
        .timeout(Duration::from_secs(8))
        .connect_timeout(Duration::from_secs(5))
        .redirect(Policy::none())
        .user_agent(concat!("PrettyLisaVPN/", env!("CARGO_PKG_VERSION")))
        .build()
        .map_err(|_| UNAVAILABLE)?;
    let request = client
        .get(provider.url())
        .header("Accept", "application/json")
        .build()
        .map_err(|_| UNAVAILABLE)?;
    Ok((client, request))
}

fn parse_observation(body: &[u8], provider: Provider) -> Result<Observation, &'static str> {
    if body.len() > MAX_BODY {
        return Err(UNAVAILABLE);
    }
    let value: serde_json::Value = serde_json::from_slice(body).map_err(|_| UNAVAILABLE)?;
    if provider == Provider::IpWho && value.get("success").and_then(|v| v.as_bool()) != Some(true) {
        return Err(UNAVAILABLE);
    }
    if value.get("error").is_some() || value.get("bogon").and_then(|v| v.as_bool()) == Some(true) {
        return Err(UNAVAILABLE);
    }
    let ip = value
        .get("ip")
        .and_then(|v| v.as_str())
        .ok_or(UNAVAILABLE)?;
    ip.parse::<IpAddr>().map_err(|_| UNAVAILABLE)?;
    let country_field = if provider == Provider::IpWho {
        "country_code"
    } else {
        "country"
    };
    let country_code = value
        .get(country_field)
        .and_then(|v| v.as_str())
        .filter(|v| v.len() == 2 && v.bytes().all(|c| c.is_ascii_uppercase()))
        .map(str::to_owned);
    let city = value
        .get("city")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|v| !v.is_empty() && v.chars().count() <= 120 && !v.chars().any(char::is_control))
        .map(str::to_owned);
    // Discard coordinates, ASN and other provider fields; no location history.
    Ok(Observation {
        success: true,
        ip: ip.to_owned(),
        country_code,
        city,
    })
}

async fn first_location<F, R>(mut fetch: F) -> Result<Observation, &'static str>
where
    F: FnMut(Provider) -> R,
    R: Future<Output = Result<Observation, &'static str>>,
{
    for provider in [Provider::IpWho, Provider::IpInfo] {
        if let Ok(location) = fetch(provider).await {
            return Ok(location);
        }
    }
    Err(UNAVAILABLE)
}

#[tauri::command]
pub async fn get_public_location() -> Result<Observation, &'static str> {
    first_location(fetch_location).await
}

async fn fetch_location(provider: Provider) -> Result<Observation, &'static str> {
    let (client, request) = request(provider)?;
    let mut response = client.execute(request).await.map_err(|_| UNAVAILABLE)?;
    if !response.status().is_success()
        || response
            .content_length()
            .is_some_and(|size| size > MAX_BODY as u64)
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
    parse_observation(&body, provider)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_request_does_not_send_browser_or_account_headers() {
        let (_, request) = request(Provider::IpWho).unwrap();
        assert_eq!(request.url().as_str(), "https://ipwho.is/");
        assert_eq!(request.method(), "GET");
        for header in ["origin", "authorization", "cookie"] {
            assert!(!request.headers().contains_key(header));
        }
    }

    #[test]
    fn rejects_provider_failures_invalid_addresses_and_oversized_responses() {
        let valid = br#"{"success":true,"ip":"203.0.113.42"}"#;
        assert!(parse_observation(valid, Provider::IpWho).is_ok());
        assert!(
            parse_observation(br#"{"success":true,"ip":"2001:db8::1"}"#, Provider::IpWho).is_ok()
        );
        assert!(
            parse_observation(br#"{"success":false,"ip":"203.0.113.42"}"#, Provider::IpWho)
                .is_err()
        );
        assert!(
            parse_observation(br#"{"success":true,"ip":"999.1.1.1"}"#, Provider::IpWho).is_err()
        );
        assert!(parse_observation(&vec![b' '; MAX_BODY + 1], Provider::IpWho).is_err());
    }
    #[test]
    fn falls_back_after_failure_and_stops_after_success() {
        let mut calls = Vec::new();
        let location = tauri::async_runtime::block_on(first_location(|provider| {
            calls.push(provider);
            std::future::ready(match provider {
                Provider::IpWho => Err(UNAVAILABLE),
                Provider::IpInfo => parse_observation(
                    br#"{"ip":"203.0.113.42","country":"NL","city":"Amsterdam","loc":"ignored"}"#,
                    provider,
                ),
            })
        }))
        .unwrap();
        assert_eq!(calls, [Provider::IpWho, Provider::IpInfo]);
        assert_eq!(location.country_code.as_deref(), Some("NL"));
        assert_eq!(location.city.as_deref(), Some("Amsterdam"));
        calls.clear();
        assert!(tauri::async_runtime::block_on(first_location(|provider| {
            calls.push(provider);
            std::future::ready(parse_observation(
                br#"{"success":true,"ip":"203.0.113.42"}"#,
                provider,
            ))
        }))
        .is_ok());
        assert_eq!(calls, [Provider::IpWho]);
        assert!(
            tauri::async_runtime::block_on(first_location(|_| std::future::ready(Err(
                UNAVAILABLE
            ))))
            .is_err()
        );
    }

    #[test]
    fn fallback_request_and_response_are_bounded_and_anonymous() {
        let (_, request) = request(Provider::IpInfo).unwrap();
        assert_eq!(request.url().as_str(), "https://ipinfo.io/json");
        for header in ["origin", "authorization", "cookie"] {
            assert!(!request.headers().contains_key(header));
        }
        for body in [
            br#"{"ip":"invalid"}"#.as_slice(),
            br#"{"ip":"203.0.113.42","error":{}}"#,
            br#"{"ip":"127.0.0.1","bogon":true}"#,
        ] {
            assert!(parse_observation(body, Provider::IpInfo).is_err());
        }
        assert!(
            parse_observation(br#"{"ip":"2001:db8::1","country":"DE"}"#, Provider::IpInfo).is_ok()
        );
    }
}
