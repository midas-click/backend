import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const candidates = [
  join(".venv", "Scripts", "python.exe"),
  join(".venv", "bin", "python"),
  "python",
];

const python = candidates.find((candidate) => {
  return candidate === "python" || existsSync(candidate);
});

const result = spawnSync(python, ["-m", "pytest"], {
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(result.status ?? 1);
