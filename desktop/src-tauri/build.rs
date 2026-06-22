fn main() {
    std::fs::create_dir_all("binaries/bridle-sidecar-runtime")
        .expect("failed to create sidecar runtime directory");
    std::fs::create_dir_all("binaries/bridle-daemon-runtime")
        .expect("failed to create daemon runtime directory");
    tauri_build::build()
}
