fn main() {
    std::fs::create_dir_all("binaries/bridle-sidecar-runtime")
        .expect("failed to create sidecar runtime directory");
    tauri_build::build()
}
