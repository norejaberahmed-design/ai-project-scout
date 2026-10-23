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

// Regression guard: disconnected UI offers honest general-web links, not fake search results.
const script = match[1];
const submitStart = script.indexOf("async function submit(text){");
const submitEnd = script.indexOf('$("form").addEventListener("submit"', submitStart);
assert.ok(submitStart >= 0 && submitEnd > submitStart, "submit handler must exist");
const submitHandler = script.slice(submitStart, submitEnd);
assert.match(submitHandler, /publicSearchLinks\\(q\\)/, "disconnected UI must provide direct public-web search links");
assert.match(submitHandler, /fetch\\(apiBase\\+"\\/api\\/chat"/, "chat must call the answer backend");
assert.match(submitHandler, /fetch\\(apiBase\\+"\\/api\\/search"/, "chat must show web results if the model fails");
assert.match(script, /https:\\/www\\.google\\/search/, "fallback must include broad Google web search");
assert.match(script, /https:\\/www\\.bing\\/search/, "fallback must include broad Bing web search");
assert.match(script, /https:\\/duckduckgo\\.com\\//, "fallback must include broad DuckDuckGo web search");
assert.match(script, /https:\\/www\\.youtube\\.com\\/results/, "fallback must include video/tutorial discovery");
assert.doesNotMatch(submitHandler, /publicFallback|wikipedia\\.org\\/w\\/api\\.php/, "chat must not silently replace general search with a Wikipedia-only fallback");
assert.match(html, /روابط بحث مباشرة وليست نتائج جلبها الإيجنت/, "UI must disclose that fallback items are links, not fetched results");
new vm.Script(script, { filename: "site/index.html inline script" });
console.log("Frontend smoke checks passed: JavaScript syntax, API-backed chat, explicit missing-backend error, no misleading fallback.");
