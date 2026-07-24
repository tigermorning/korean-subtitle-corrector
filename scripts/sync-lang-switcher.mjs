#!/usr/bin/env node
// Scans the repo root for README/PRD language variants (README.md, README.en.md, README.ja-JP.md, ...)
// and writes a synced language-switcher block into every variant found, so adding a new
// translation file is the only step needed for it to become reachable from all the others.
//
// Usage: node sync-lang-switcher.mjs [repoRoot]
//
// Naming convention:
//   README.md        -> default language (see config defaultLang, falls back to "ko")
//   README.en.md      -> English
//   README.ja-JP.md   -> Japanese
//   PRD.md, PRD.en.md, ... -> same convention, tracked independently from README
//
// Config (optional): <repoRoot>/.lang-switcher.json
//   {
//     "defaultLang": "ko",                       // fallback for any doc type not listed below
//     "docs": { "README": "en", "PRD": "ko" },    // per-doc-type override (e.g. README.md is English, PRD.md is Korean)
//     "order": ["ko", "en", "ja", "zh-CN", "zh-TW"],
//     "labels": { "ko": "한국어", "en": "English" }
//   }

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const DEFAULT_LABELS = {
  ko: "한국어",
  en: "English",
  ja: "日本語",
  "ja-JP": "日本語",
  zh: "中文",
  "zh-CN": "中文(简体)",
  "zh-TW": "中文(繁體)",
  fr: "Français",
  de: "Deutsch",
  es: "Español",
  pt: "Português",
  ru: "Русский",
  vi: "Tiếng Việt",
  id: "Bahasa Indonesia",
  th: "ไทย",
};

const START = "<!-- lang-switcher:start -->";
const END = "<!-- lang-switcher:end -->";

const FILE_RE = /^(README|PRD)(?:\.([A-Za-z]{2}(?:-[A-Za-z]{2})?))?\.md$/;

function loadConfig(root) {
  try {
    return JSON.parse(readFileSync(join(root, ".lang-switcher.json"), "utf8"));
  } catch {
    return {};
  }
}

function scan(root) {
  const groups = { README: {}, PRD: {} };
  for (const name of readdirSync(root)) {
    const m = FILE_RE.exec(name);
    if (!m) continue;
    const [, doc, langRaw] = m;
    groups[doc][langRaw ?? "__default__"] = name;
  }
  return groups;
}

function buildSwitcherBlock(files, defaultLang, order, labels) {
  const langs = Object.keys(files).map((k) => (k === "__default__" ? defaultLang : k));
  const sorted = [...new Set(langs)].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    return a.localeCompare(b);
  });

  const links = sorted.map((lang) => {
    const key = lang === defaultLang && files.__default__ ? "__default__" : lang;
    const filename = files[key];
    const label = labels[lang] ?? lang;
    return { filename, label };
  });

  return { links };
}

function renderBlockForFile(links, selfFilename) {
  const others = links.filter((l) => l.filename !== selfFilename);
  if (others.length === 0) return null;
  const anchors = others.map((l) => `  <a href="${l.filename}">${l.label}</a>`).join("\n  ·\n");
  return `${START}\n<p align="center">\n${anchors}\n</p>\n${END}`;
}

function upsertBlock(content, block) {
  const startIdx = content.indexOf(START);
  const endIdx = content.indexOf(END);
  if (startIdx !== -1 && endIdx !== -1) {
    return content.slice(0, startIdx) + block + content.slice(endIdx + END.length);
  }
  return `${block}\n\n${content}`;
}

function run(root) {
  const config = loadConfig(root);
  const fallbackDefaultLang = config.defaultLang ?? "ko";
  const docDefaults = config.docs ?? {};
  const labels = { ...DEFAULT_LABELS, ...(config.labels ?? {}) };

  const groups = scan(root);
  let changed = 0;

  for (const doc of ["README", "PRD"]) {
    const files = groups[doc];
    const count = Object.keys(files).length;
    if (count < 2) {
      console.log(`[${doc}] ${count} variant(s) found — switcher skipped (need 2+).`);
      continue;
    }
    const defaultLang = docDefaults[doc] ?? fallbackDefaultLang;
    const order = config.order ?? [defaultLang, "en", "ja", "zh-CN", "zh-TW"];
    const { links } = buildSwitcherBlock(files, defaultLang, order, labels);
    for (const filename of Object.values(files)) {
      const path = join(root, filename);
      const original = readFileSync(path, "utf8");
      const block = renderBlockForFile(links, filename);
      if (!block) continue;
      const updated = upsertBlock(original, block);
      if (updated !== original) {
        writeFileSync(path, updated, "utf8");
        changed++;
        console.log(`[${doc}] updated ${filename} (${links.length} languages)`);
      } else {
        console.log(`[${doc}] ${filename} already in sync`);
      }
    }
  }

  console.log(`Done. ${changed} file(s) updated.`);
}

run(process.argv[2] ?? process.cwd());
