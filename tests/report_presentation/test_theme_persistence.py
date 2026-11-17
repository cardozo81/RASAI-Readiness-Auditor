"""Regression: report-presentation theme survives offline multi-page navigation.

Node executes the production JS with an intentionally restricted file:// DOM:
storage can fail, history can fail, and only local presentation links may carry
the preference. No browser HTTP, AI, audit source changes or external services.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


_JS = Path(__file__).parents[2] / "src" / "rasai" / "parallel_report" / "assets" / "app.js"


def test_theme_survives_file_navigation_and_keeps_other_report_links_untouched():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable for lightweight JS integration")
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync(process.argv[1], 'utf8');

function page(url, storageBlocked, replaceStateBlocked = false, saved = null) {
  const links = [
    'plano.html#acao-1', 'ia-custos.html', '#indice',
    '../report-catalog/index.html', 'assets/app.js',
    'https://example.org/elsewhere.html',
  ].map(raw => ({
    raw, href: raw,
    getAttribute(name) { return name === 'href' ? this.href : null; },
    setAttribute(name, value) { if (name === 'href') this.href = value; },
  }));
  const classes = new Set();
  const listeners = {};
  const doc = {
    body: { classList: {
      contains: name => classes.has(name),
      toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
    }},
    querySelectorAll(selector) { return selector === 'a[href]' ? links : []; },
    querySelector(selector) {
      return selector === '#theme'
        ? { addEventListener: (event, cb) => { listeners[event] = cb; } }
        : null;
    },
    getElementById() { return null; },
  };
  const location = new URL(url);
  const storage = {
    value: saved,
    getItem() { if (storageBlocked) throw new Error('Storage denied'); return this.value; },
    setItem(_key, value) { if (storageBlocked) throw new Error('Storage denied'); this.value = value; },
  };
  const history = { state: null, replaceState(_state,_title,href) {
    if (replaceStateBlocked) throw new Error('File history denied');
    const updated = new URL(href);
    location.href = updated.href;
  }};
  const win = {
    addEventListener(){}, matchMedia: () => ({matches:true}),
  };
  const context = { document:doc, window:win, location, history,
    URL, localStorage:storage, console, Map,
  };
  vm.runInNewContext(code,context,{filename:'app.js'});
  return {location,links,classes,listeners,storage};
}

const base='file:///C:/IA-PROJETOS/github/RASAI-Readiness-Auditor/audits/AUD-TEST/report-presentation/';
const first=page(base+'index.html',true);
assert.equal(first.classes.size,0,'Default theme should still honor system preference');
first.listeners.click();
assert(first.classes.has('light'),'OS dark must toggle to light');
assert.equal(first.location.searchParams.get('rasai_theme'),'light');
const plan=first.links[0].href;
assert(plan.endsWith('plano.html?rasai_theme=light#acao-1'));
assert(first.links[1].href.endsWith('ia-custos.html?rasai_theme=light'));
for (const i of [2,3,4,5]) assert.equal(first.links[i].href,first.links[i].raw);

const second=page(plan,true,true);
assert(second.classes.has('light'),'Theme must be restored even with storage and history disabled');
assert(second.links[0].href.includes('rasai_theme=light'));
second.listeners.click();
assert(second.classes.has('dark'));
assert(!second.classes.has('light'));
assert(second.links[1].href.includes('rasai_theme=dark'));
assert(!second.links[1].href.includes('rasai_theme=light'));

const direct=page(base+'rede.html',false,false,'dark');
assert(direct.classes.has('dark'),'Direct open should use saved preference when storage works');
assert(direct.links[1].href.includes('rasai_theme=dark'));

const explicit=page(base+'performance.html?rasai_theme=light',false,false,'dark');
assert(explicit.classes.has('light'),'Navigation parameter takes precedence over stale storage');
assert.equal(explicit.storage.value,'light');
process.stdout.write('THEME_OFFLINE_NAVIGATION=PASS\n');
"""
    result = subprocess.run(
        [node, "-e", script, str(_JS)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "THEME_OFFLINE_NAVIGATION=PASS" in result.stdout
