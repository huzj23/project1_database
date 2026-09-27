import fs from "node:fs";
import path from "node:path";
import { WASI } from "node:wasi";

const workspace = path.resolve("D:/workspace/project1_database/blender_previews/replica_texture_work");
const wasmPath = path.resolve("D:/workspace/project1_database/tools/vendor/basisu_st.wasm");
const inputName = "Baked_sc0_Image_0.basis";

const wasi = new WASI({
  version: "preview1",
  args: ["basisu", "-unpack", "-file", inputName],
  env: {},
  preopens: { ".": workspace },
  returnOnExit: true,
});

const moduleBytes = fs.readFileSync(wasmPath);
const module = await WebAssembly.compile(moduleBytes);
const instance = await WebAssembly.instantiate(module, {
  wasi_snapshot_preview1: wasi.wasiImport,
});
const exitCode = wasi.start(instance);
console.log("BASISU_EXIT", exitCode);
