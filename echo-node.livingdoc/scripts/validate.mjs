#!/usr/bin/env node

/**
 * Validate the Echo-Node living document structure.
 * Checks:
 *  - All required files exist
 *  - index.json is valid JSON
 *  - All referenced sections exist
 *  - All backlinks target valid sections
 *  - All proposal targetIds reference valid sections
 */

import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PUBLIC = resolve(ROOT, 'public');

let errors = 0;

function check(condition, message) {
  if (!condition) {
    console.error(`  ✗ ${message}`);
    errors++;
  } else {
    console.log(`  ✓ ${message}`);
  }
}

function checkFile(path) {
  const full = resolve(PUBLIC, path);
  check(existsSync(full), `File exists: public/${path}`);
  return full;
}

// 1. Check required files
console.log('\n📋 Required files...');
checkFile('index.html');
checkFile('app.js');
checkFile('styles.css');
checkFile('content/index.json');
checkFile('data/annotations.json');
checkFile('../RAISON_DETRE.md');
checkFile('../MODEL_START_HERE.md');
checkFile('../package.json');

// 2. Validate index.json
console.log('\n📋 Manifest validation...');
const manifestPath = resolve(PUBLIC, 'content/index.json');
check(existsSync(manifestPath), 'manifest exists');

let manifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  check(true, 'manifest is valid JSON');
} catch (e) {
  check(false, `manifest is valid JSON: ${e.message}`);
  process.exit(1);
}

// 3. Check section IDs are unique
const sectionIds = manifest.sections.map(s => s.id);
const uniqueIds = new Set(sectionIds);
check(uniqueIds.size === sectionIds.length, 'all section IDs are unique');

// 4. Check all referenced sections exist
console.log('\n📋 Section references...');
for (const section of manifest.sections) {
  check(existsSync(resolve(PUBLIC, section.source)), `section source: ${section.source}`);
  
  for (const bl of section.backlinks) {
    check(sectionIds.includes(bl), `  backlink "${bl}" → valid section in "${section.id}"`);
  }
}

// 5. Check all proposal targetIds
console.log('\n📋 Proposal references...');
for (const prop of (manifest.proposals || [])) {
  for (const tid of prop.targetIds) {
    check(sectionIds.includes(tid) || tid === 'document', 
      `proposal ${prop.id} targetId "${tid}" is valid`);
  }
}

// 6. Check proposal IDs are unique
const propIds = new Set((manifest.proposals || []).map(p => p.id));
check(propIds.size === (manifest.proposals || []).length, 'all proposal IDs are unique');

// 7. Check history IDs are unique
const histIds = new Set((manifest.history || []).map(h => h.id));
check(histIds.size === (manifest.history || []).length, 'all history IDs are unique');

// 8. Check worklog IDs are unique
const wlIds = new Set((manifest.worklogs || []).map(w => w.id));
check(wlIds.size === (manifest.worklogs || []).length, 'all worklog IDs are unique');

// Summary
console.log(`\n${'─'.repeat(40)}`);
if (errors === 0) {
  console.log(`✅ All checks passed!\n`);
} else {
  console.log(`❌ ${errors} check(s) failed.\n`);
  process.exit(1);
}
