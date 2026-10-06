/** Public commit and the export receipt: identities, never private repository paths. */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { ROOT } from './data';

export function provenance() {
  let siteCommit: string | null = null;
  try {
    const value = execFileSync('git', ['-C', ROOT, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    if (/^[0-9a-f]{40}$/.test(value)) siteCommit = value;
  } catch { /* A source archive may have no Git metadata. */ }
  let receipt: { source_commit: string; source_tree: { sha256: string; files: number }; g1: { passed: boolean; block_hits: number }; full_export: boolean } | null = null;
  try {
    const value = JSON.parse(fs.readFileSync(path.join(ROOT, 'export-receipt.json'), 'utf8'));
    if (/^[0-9a-f]{40}$/.test(value.source_commit) && /^[0-9a-f]{64}$/.test(value.source_tree?.sha256)) receipt = value;
  } catch { /* The mandatory repository gate rejects a missing or invalid receipt. */ }
  return { siteCommit, receipt };
}
