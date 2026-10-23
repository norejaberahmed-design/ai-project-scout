const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("site/index.html", "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, "inline app script must exist");

class FakeElement {
  constructor() {
    this.value = "";
    this.textContent = "";
    this.dataset = {};
    this.childNodes = [];
    this.disabled = false;
    this.className = "";
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }
  addEventListener() {}
  appendChild(node) { this.childNodes.push(node); return node; }
  focus() {}
}
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement());
    return elements.get(id);
  },
  querySelectorAll() { return []; },
  createElement() { return new FakeElement(); },
};
const localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
let fetchMode = "github-search";
async function fetch(url) {
  if (fetchMode === "github-search") {
    assert.match(String(url), /api\.github\.com\/search\/repositories/);
    return { ok: true, status: 200, async json() { return { items: [{
      full_name: "demo/agent", html_url: "https://github.com/demo/agent",
      description: "Public AI agent project", language: "Python",
      stargazers_count: 12, pushed_at: "2026-10-01T00:00:00Z",
      license: { spdx_id: "MIT" },
    }] }; } };
  }
  if (fetchMode === "repo") {
    if (String(url).endsWith("/readme")) {
      return { ok: true, status: 200, async json() {
        return { content: Buffer.from("# Demo readme\nTesting instructions").toString("base64") };
      } };
    }
    return { ok: true, status: 200, async json() { return {
      full_name: "demo/agent", html_url: "https://github.com/demo/agent",
      description: "Public AI agent project", language: "Python",
      stargazers_count: 12, pushed_at: "2026-10-01T00:00:00Z",
      license: { spdx_id: "MIT" },
    }; } };
  }
  assert.match(String(url), /wikipedia\.org\/w\/api\.php/);
  return { ok: true, status: 200, async json() { return { query: { search: [{
    title: "Artificial intelligence", snippet: "A field of computer science.",
  }] } }; } };
}
const context = {
  document, localStorage, fetch, URL, console, TextDecoder, Uint8Array,
  atob: value => Buffer.from(value, "base64").toString("binary"),
};
vm.runInNewContext(match[1], context, { timeout: 2000 });

(async () => {
  let result = await context.publicFallback("find open source AI agent tools");
  assert.match(result.answer, /demo\/agent/);
  assert.equal(result.sources[0].url, "https://github.com/demo/agent");
  assert.match(result.coverage_note, /GitHub API/);

  fetchMode = "repo";
  result = await context.publicFallback("Analyze https://github.com/demo/agent");
  assert.match(result.answer, /README/);
  assert.match(result.answer, /Testing instructions/);
  assert.equal(result.sources.length, 2);

  fetchMode = "wikipedia";
  result = await context.publicFallback("What is artificial intelligence?");
  assert.match(result.answer, /Artificial intelligence/);
  assert.match(result.sources[0].url, /wikipedia\.org\/wiki/);
  console.log("Frontend fallback smoke tests passed: GitHub search, repository inspection, Wikipedia search.");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
