import { createReadStream, cpSync, copyFileSync, mkdirSync, statSync } from "node:fs";
import { extname, isAbsolute, relative, resolve, sep } from "node:path";

// Only runtime assets enter the website. Model sources, screenshots and tests stay out.
const experiences = {
  bubbles: { root: "thought-bubbles", entry: "demo.html", files: ["demo.html", "dist/"] },
  debate: { root: "debate-room", entry: "index.html", files: ["index.html", "style.css", "app.js", "engine.mjs", "motion-policy.mjs", "timing.mjs", "scene.js", "kanshan-character.js", "assets/kanshan-reference.jpg", "assets/kanshan/kanshan-runtime.glb", "assets/kanshan/asset-info.json", "vendor/"] },
};
const contentTypes = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".glb": "model/gltf-binary" };

export function resolveExperienceAsset(pathname, webRoot) {
  let decoded;
  try { decoded = decodeURIComponent(pathname); } catch { return null; }
  if (decoded.includes("\\") || decoded.includes("\0")) return null;
  const match = /^\/experiences\/(bubbles|debate)(?:\/(.*))?$/.exec(decoded);
  if (!match) return null;
  const config = experiences[match[1]];
  let file = match[2] || config.entry;
  if (file === "index.html") file = config.entry;
  if (file.split("/").some(part => part === ".." || part === "." || part.startsWith("."))) return null;
  if (!config.files.some(allowed => allowed.endsWith("/") ? file.startsWith(allowed) : file === allowed)) return null;
  const root = resolve(webRoot, "../packages", config.root), path = resolve(root, file), inside = relative(root, path);
  if (inside.startsWith(".." + sep) || isAbsolute(inside)) return null;
  return path;
}

export function publishExperiences(webRoot, outDir) {
  for (const [slug, config] of Object.entries(experiences)) {
    const root = resolve(webRoot, "../packages", config.root), target = resolve(outDir, "experiences", slug);
    mkdirSync(target, { recursive: true });
    for (const file of config.files) {
      const destination = resolve(target, file);
      mkdirSync(resolve(destination, ".."), { recursive: true });
      cpSync(resolve(root, file), destination, { recursive: true });
    }
    copyFileSync(resolve(root, config.entry), resolve(target, "index.html"));
  }
}

export function experiencesPlugin() {
  let config;
  return {
    name: "thinkspace-local-experiences",
    configResolved(resolved) { config = resolved; },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = (req.url || "").split("?")[0];
        if (!pathname.startsWith("/experiences/")) return next();
        if (!['GET', 'HEAD'].includes(req.method || 'GET')) { res.statusCode = 405; return res.end(); }
        if (/^\/experiences\/(bubbles|debate)$/.test(pathname)) { res.statusCode = 302; res.setHeader("Location", pathname + "/"); return res.end(); }
        const path = resolveExperienceAsset(pathname, config.root);
        try { if (!path || !statSync(path).isFile()) throw new Error("not a runtime asset"); }
        catch { res.statusCode = 404; return res.end("Experience asset not found"); }
        res.setHeader("Content-Type", contentTypes[extname(path)] || "application/octet-stream");
        res.setHeader("Cache-Control", "no-cache");
        if (req.method === 'HEAD') return res.end();
        const stream = createReadStream(path);
        stream.on("error", () => { if (!res.headersSent) res.statusCode = 500; res.end(); });
        stream.pipe(res);
      });
    },
    writeBundle() { publishExperiences(config.root, resolve(config.root, config.build.outDir)); },
  };
}
