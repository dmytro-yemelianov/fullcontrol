/**
 * Generate the committed IR fixtures consumed by the Python proof test
 * (tests/unit/test_ts_ir_binding.py). Run with: `npm run fixtures`.
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { square, spiralVase } from './designs.ts';

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, '..', 'fixtures');
mkdirSync(fixturesDir, { recursive: true });

const squareIR = square().toIR({
  printSpeed: 1000,
  travelSpeed: 8000,
  provenance: { design: 'square', params: { size: 20, origin: [50, 50], z: 0.2 } },
  invariants: ['non_negative_extrusion', 'monotonic_layer_z'],
});

// a small spiral keeps the committed fixture tiny while still proving the IR round-trips
const spiralIR = spiralVase(15, 3, 0.24, 24).toIR({
  printSpeed: 1000,
  travelSpeed: 8000,
  provenance: { design: 'spiral_vase', params: { radius: 15, height: 3, layer_height: 0.24 } },
  invariants: ['non_negative_extrusion', 'monotonic_layer_z'],
});

writeFileSync(join(fixturesDir, 'square.ir.json'), JSON.stringify(squareIR, null, 2) + '\n');
writeFileSync(join(fixturesDir, 'spiral.ir.json'), JSON.stringify(spiralIR, null, 2) + '\n');

console.log(`wrote square.ir.json (${squareIR.events.length} events)`);
console.log(`wrote spiral.ir.json (${spiralIR.events.length} events)`);
