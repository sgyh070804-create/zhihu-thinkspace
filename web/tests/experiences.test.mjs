import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { publishExperiences, resolveExperienceAsset } from "../experiences.mjs";
const root = fileURLToPath(new URL("../", import.meta.url));

test("experience URLs resolve only public runtime assets", () => {
  assert.ok(existsSync(resolveExperienceAsset("/experiences/bubbles/", root)));
  assert.ok(existsSync(resolveExperienceAsset("/experiences/debate/assets/kanshan/kanshan-runtime.glb", root)));
  for (const path of ["/experiences/debate/tests/rig.test.mjs", "/experiences/debate/README.md", "/experiences/debate/../api/.env", "/experiences/bubbles/dist/%2e%2e/README.md", "/experiences/bubbles/dist/%5c..%5c.env", "/experiences/debate/%00", "/experiences/debate/%XX"]) assert.equal(resolveExperienceAsset(path, root), null, path);
});

test("built website contains both self-contained experiences but no model source/test artifacts", () => {
  const out = mkdtempSync(resolve(tmpdir(), "thinkspace-experiences-"));
  try {
    publishExperiences(root, out);
    for (const path of ["bubbles/index.html", "bubbles/dist/thought-bubbles.js", "bubbles/dist/bubble-physics.js", "debate/index.html", "debate/motion-policy.mjs", "debate/vendor/utils/SkeletonUtils.js", "debate/assets/kanshan/kanshan-runtime.glb"]) assert.ok(existsSync(resolve(out, "experiences", path)), path);
    assert.ok(readFileSync(resolve(out, "experiences/bubbles/index.html"), "utf8").includes('dist/thought-bubbles.css'));
    const files = readdirSync(out, { recursive: true });
    assert.ok(!files.some(path => /screenshots|tests|\.blend|\.env|prepare_runtime/.test(path)));
  } finally { rmSync(out, { recursive: true, force: true }); }
});
