fn main() {
    let target = std::env::var("TARGET").expect("Cargo TARGET is unavailable");
    let extension = if target.contains("-windows-") {
        ".exe"
    } else {
        ""
    };
    let sidecar =
        std::path::Path::new("binaries").join(format!("bridle-sidecar-{target}{extension}"));
    let profile = std::env::var("PROFILE").unwrap_or_default();
    if profile == "debug" && !sidecar.exists() {
        std::fs::create_dir_all("binaries").expect("failed to create sidecar directory");
        #[cfg(windows)]
        std::fs::write(&sidecar, []).expect("failed to create development sidecar placeholder");
        #[cfg(not(windows))]
        std::fs::write(
            &sidecar,
            "#!/usr/bin/env bash\nexec uv run bridle sidecar \"$@\"\n",
        )
        .expect("failed to create development sidecar shim");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&sidecar, std::fs::Permissions::from_mode(0o755))
                .expect("failed to make development sidecar executable");
        }
    }
    tauri_build::build()
}
