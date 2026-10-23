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

// Regression guard: missing API must never be disguised as GitHub/Wikipedia-only search.
const script = match[1];
const submitStart = script.indexOf("async function submit(text){");
const submitEnd = script.indexOf('$("form").addEventListener("submit"', submitStart);
assert.ok(submitStart >= 0 && submitEnd > submitStart, "submit handler must exist");
const submitHandler = script.slice(submitStart, submitEnd);
assert.match(submitHandler, /if\(!apiBase\)/, "chat must handle an unconfigured API explicitly");
assert.match(submitHandler, /publicSearchLinks\(q\)/, "no-backend state must provide clearly labeled direct search links");
assert.match(submitHandler, /fetch\(apiBase\+"\/api\/chat"/, "chat must call the general web-search backend");
assert.match(submitHandler, /fetch\(apiBase\+"\/api\/search"/, "if model chat fails, UI must attempt the real backend search endpoint");
assert.doesNotMatch(submitHandler, /publicFallback|wikipedia\.org|api\.github\.com/,
  "chat handler must not disguise GitHub/Wikipedia-only results as general web search");
assert.match(html, /GitHub Pages وحدها لا تشغّل Python/, "UI must explain why a backend is required");
assert.match(script, /https:\/\/www\.google\.com\/search\?q=/, "fallback includes direct general-web search");
assert.match(script, /https:\/\/www\.bing\.com\/search\?q=/, "fallback includes a second general-web search engine");

new vm.Script(script, { filename: "site/index.html inline script" });
console.log("Frontend smoke checks passed: JavaScript syntax, API-backed chat, real search fallback endpoint, honest no-backend search links.");
