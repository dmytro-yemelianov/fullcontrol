#!/usr/bin/env bash
# Rebuild the WebAssembly kernel and its JS glue into web/pkg/.
# Requires: rustup target add wasm32-unknown-unknown, and wasm-bindgen-cli == the pinned
# wasm-bindgen crate version (currently 0.2.123): cargo install wasm-bindgen-cli --version 0.2.123
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
crate="$here/../rust_kernel"

cargo build --release --manifest-path "$crate/Cargo.toml" \
  --target wasm32-unknown-unknown --no-default-features --features wasm

wasm-bindgen --target web --no-typescript \
  --out-dir "$here/pkg" \
  "$crate/target/wasm32-unknown-unknown/release/fullcontrol_kernel.wasm"

echo "built web/pkg/  ($(ls -1 "$here/pkg" | tr '\n' ' '))"
