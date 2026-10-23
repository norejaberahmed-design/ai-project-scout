const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("site/index.html", "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, "inline app script must exist");
assert.match(html, /id="view-components"/, "component acquisition view must exist");
assert.match(match[1], /\/api\/components\/inspect/, "UI must call component inspection API");
assert.match(match[1], /\/api\/components\/acquire/, "UI must call guarded acquisition API");
assert.match(match[1], /Authorization.*Bearer/, "acquisition token must be sent as an authorization header");
assert.doesNotMatch(match[1], /localStorage\.(?:setItem|getItem)\([^)]*component-token/i,
  "admin import token must not be persisted in localStorage");

// Regression guard: a missing API must never be disguised as a GitHub/Wikipedia search.
const script = match[1];
const submitStart = script.indexOf("async function submit(text){");
const submitEnd = script.indexOf('$("form").addEventListener("submit"', submitStart);
assert.ok(submitStart >= 0 && submitEnd > submitStart, "submit handler must exist");
const submitHandler = script.slice(submitStart, submitEnd);
assert.match(submitHandler, /if\(!apiBase\)throw new Error/, "chat must fail clearly when API is not configured");
assert.match(submitHandler, /fetch\(apiBase\+"\/api\/chat"/, "chat must call the general web-search backend");
assert.doesNotMatch(submitHandler, /publicFallback|wikipedia\.org|api\.github\.com/,
  "chat handler must not mask backend failure with limited single-source search");
assert.match(html, /GitHub Pages وحدها لا تشغّل Python/, "UI must explain why a backend is required");

new vm.Script(script, { filename: "site/index.html inline script" });
console.log("Frontend smoke checks passed: JavaScript syntax, API-backed chat, explicit missing-backend error, no misleading fallback.");
