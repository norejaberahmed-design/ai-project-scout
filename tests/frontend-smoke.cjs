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
assert.ok(submitHandler.includes("publicSearchLinks(q)"), "no-backend state must provide direct public-web search links");
assert.ok(submitHandler.includes('fetch(apiBase+"/api/chat"'), "chat must call the answer backend");
assert.ok(submitHandler.includes('fetch(apiBase+"/api/search"'), "chat must show web results if model chat fails");
assert.ok(script.includes("https://www.google.com/search?q="), "fallback must include broad Google web search");
assert.ok(script.includes("https://www.bing.com/search?q="), "fallback must include broad Bing web search");
assert.ok(script.includes("https://duckduckgo.com/?q="), "fallback must include broad DuckDuckGo web search");
assert.ok(!script.includes("https://www.youtube.com/results?search_query="), "skill discovery must not add unrelated video search");
assert.ok(!submitHandler.includes("publicFallback") && !submitHandler.includes("wikipedia.org/w/api.php"), "chat must not disguise Wikipedia-only results as general search");
assert.ok(html.includes("روابط بحث مباشرة وليست نتائج جلبها الإيجنت"), "UI must disclose direct links are not fetched results");
assert.ok(html.includes("تغطية البحث في هذه الإجابة"), "UI must show an Arabic source coverage summary");
assert.ok(html.includes("مصادر معروضة:"), "UI must count sources and distinguish general web and GitHub");
assert.ok(html.includes("ليس قياسًا لتغطية الإنترنت كله"), "UI must not claim complete internet coverage");
new vm.Script(script, { filename: "site/index.html inline script" });
console.log("Frontend smoke checks passed: JavaScript syntax, API-backed chat, real search fallback endpoint, honest no-backend search links.");
