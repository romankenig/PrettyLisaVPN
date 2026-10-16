// Export deterministic formatting through CI when the local proxy is unavailable.
import fs from "node:fs/promises";
import prettier from "prettier";
const paths = ["src/main.tsx","src/ui/WindowFrame.tsx","src/ui/Home.tsx","src/ui/styles.css","src/test/windowFrame.test.tsx","src-tauri/tauri.conf.json","src-tauri/capabilities/main.json","scripts/ci/capture-windows-ui.cjs"];
for (const path of paths) {
  const source = await fs.readFile(path, "utf8");
  const content = await prettier.format(source, { filepath: path });
  if (source !== content) {
    console.log("FORMATTED_SOURCE " + JSON.stringify({ path: "apps/windows/" + path, content }));
  }
}
for (const path of ["src-tauri/src/main.rs", "src-tauri/src/window_frame.rs"]) {
  console.log("FORMATTED_SOURCE " + JSON.stringify({
    path: "apps/windows/" + path,
    content: await fs.readFile(path, "utf8"),
  }));
}
