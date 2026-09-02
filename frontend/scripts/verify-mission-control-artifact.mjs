import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const outputRoot = resolve(process.argv[2] ?? "dist");
const html = readFileSync(join(outputRoot, "index.html"), "utf8");
const references = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(
  (match) => match[1],
);
const staticReferences = references.filter((path) =>
  /\.(?:css|js|svg)$/.test(path),
);

if (staticReferences.length === 0) {
  throw new Error("Mission Control artifact contains no static references.");
}
for (const path of staticReferences) {
  if (!path.startsWith("/mission-assets/")) {
    throw new Error(`Mission Control static path escaped its namespace: ${path}`);
  }
  const localPath = join(outputRoot, path.slice("/mission-assets/".length));
  if (!statSync(localPath).isFile()) {
    throw new Error(`Mission Control static reference is missing: ${path}`);
  }
}

const files = [];
const visit = (directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) visit(path);
    else files.push(path);
  }
};
visit(outputRoot);

if (files.some((path) => path.endsWith(".map"))) {
  throw new Error("Mission Control artifact contains source maps.");
}

const forbidden = [
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /(?:AKIA|ASIA)[0-9A-Z]{16}/,
  /gh[pousr]_[A-Za-z0-9]{20,}/,
  /sk_(?:live|prod)_[A-Za-z0-9]+/,
  /https?:\/\/(?:backend|postgres|redis)(?::|\/)/,
  /\/Users\/[A-Za-z0-9._-]+\//,
];
for (const path of files.filter((item) => /\.(?:html|css|js|json)$/.test(item))) {
  const content = readFileSync(path, "utf8");
  if (forbidden.some((pattern) => pattern.test(content))) {
    throw new Error(
      `Mission Control artifact contains a protected pattern: ${relative(outputRoot, path)}`,
    );
  }
}

const digest = createHash("sha256");
for (const path of files.sort()) {
  digest.update(relative(outputRoot, path));
  digest.update("\0");
  digest.update(readFileSync(path));
  digest.update("\0");
}

process.stdout.write(
  `${JSON.stringify({
    result: "MISSION_CONTROL_ARTIFACT_READY",
    asset_base: "/mission-assets/",
    file_count: files.length,
    artifact_sha256: digest.digest("hex"),
  })}\n`,
);
