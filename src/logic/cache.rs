//! The on-disk copy of the last API responses, so a launch can start from fresh data.

use std::fs;
use std::io;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use super::watchlist::write_atomic;

/// Saved bytes and when they were saved, as unix seconds taken from the file's mtime.
pub fn read(path: &Path) -> Option<(String, f64)> {
    let body = fs::read_to_string(path).ok()?;
    let modified = fs::metadata(path).ok()?.modified().ok()?;
    let saved = match modified.duration_since(UNIX_EPOCH) {
        Ok(elapsed) => elapsed.as_secs_f64(),
        Err(before) => -before.duration().as_secs_f64(),
    };
    Some((body, saved))
}

pub fn write(path: &Path, body: &str) -> io::Result<()> {
    write_atomic(path, body.as_bytes())
}

pub fn now_unix() -> f64 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(elapsed) => elapsed.as_secs_f64(),
        Err(before) => -before.duration().as_secs_f64(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missing_cache_reads_as_none() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(read(&dir.path().join("nope.json")), None);
    }

    #[test]
    fn writes_and_reads_the_body_with_its_mtime() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested/prices.json");
        write(&path, r#"[{"name":"A"}]"#).unwrap();
        let (body, saved) = read(&path).unwrap();
        assert_eq!(body, r#"[{"name":"A"}]"#);
        assert!((saved - now_unix()).abs() < 5.0, "mtime {saved} is not close to now");
    }

    #[test]
    fn writing_leaves_no_temporary_file_behind() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("prices.json");
        write(&path, "one").unwrap();
        write(&path, "two").unwrap();
        assert_eq!(read(&path).unwrap().0, "two");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }
}
