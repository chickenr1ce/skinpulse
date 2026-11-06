//! The PriceEmpire HTTP client. It returns raw bodies; parsing and caching belong to the caller.

use std::time::Duration;

use ureq::Agent;

pub const BASE_URL: &str = "https://api.pricempire.com/v4/trader";

/// The whole-market prices body is far above ureq's 10 MB default read limit.
const MAX_BODY: u64 = 200 * 1024 * 1024;

pub struct Client {
    api_key: String,
    agent: Agent,
}

impl Client {
    pub fn new(api_key: &str) -> Client {
        let agent: Agent = Agent::config_builder().timeout_global(Some(Duration::from_secs(60))).build().into();
        Client { api_key: api_key.to_string(), agent }
    }

    /// Raw response body, to be parsed and cached by the caller.
    pub fn prices(&self) -> Result<String, String> {
        let url = format!("{BASE_URL}/items/prices?app_id=730&currency=EUR&sources=buff163,skins&avg=true");
        let mut response = self.authorized(&url).call().map_err(network_error)?;
        read_body(&mut response)
    }

    pub fn portfolio(&self, slug: &str) -> Result<String, String> {
        let url = format!("{BASE_URL}/portfolios/{}", encode_slug(slug));
        let mut response = self.authorized(&url).call().map_err(network_error)?;
        read_body(&mut response)
    }

    fn authorized(&self, url: &str) -> ureq::RequestBuilder<ureq::typestate::WithoutBody> {
        self.agent.get(url).header("Authorization", format!("Bearer {}", self.api_key))
    }
}

fn read_body(response: &mut ureq::http::Response<ureq::Body>) -> Result<String, String> {
    response.body_mut().with_config().limit(MAX_BODY).read_to_string().map_err(|e| e.to_string())
}

fn network_error(error: ureq::Error) -> String {
    match error {
        ureq::Error::StatusCode(status) => format!("API status {status}"),
        other => other.to_string(),
    }
}

/// Percent-encodes every slug byte other than ASCII alphanumerics, `-`, `_`, `.` and `~`.
fn encode_slug(slug: &str) -> String {
    let mut encoded = String::with_capacity(slug.len());
    for byte in slug.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
            encoded.push(byte as char);
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slug_encoding_keeps_the_unreserved_characters() {
        assert_eq!(encode_slug("my-Portfolio_1.2~3"), "my-Portfolio_1.2~3");
        assert_eq!(encode_slug(""), "");
    }

    #[test]
    fn slug_encoding_escapes_everything_else() {
        assert_eq!(encode_slug("a b/c"), "a%20b%2Fc");
        assert_eq!(encode_slug("café"), "caf%C3%A9");
        assert_eq!(encode_slug("?&=#%"), "%3F%26%3D%23%25");
    }

    // Compile-time assertion: if Client ever gains a Debug impl, both blanket impls below apply
    // and `probe::<_, Client>()` can no longer infer the marker type, so the build fails.
    trait AmbiguousIfImpl<A> {}
    impl<T: ?Sized> AmbiguousIfImpl<()> for T {}
    impl<T: ?Sized + std::fmt::Debug> AmbiguousIfImpl<u8> for T {}
    fn probe<A, T: ?Sized + AmbiguousIfImpl<A>>() {}

    #[test]
    fn the_client_does_not_debug_print_its_key() {
        probe::<_, Client>();
    }
}
