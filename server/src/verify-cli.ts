// Verify any race from on-chain data alone:
//   RPC_URL=https://api.devnet.solana.com node src/verify-cli.ts <raceId>

import { verifyRace } from "./races.ts";

const raceId = Number(process.argv[2]);
if (!raceId) {
  console.error("usage: node src/verify-cli.ts <raceId>");
  process.exit(2);
}
const v = await verifyRace(raceId);
console.log(`race ${v.raceId} (sim ${v.simVersion})`);
console.log(`seed matches on-chain commitment: ${v.seedMatchesCommitment}`);
console.log(`result hash on-chain:  ${v.onChainResultHash}`);
console.log(`result hash re-run:    ${v.recomputedResultHash}`);
console.log(v.verified ? "VERIFIED: same setups + same seed = same result" : "MISMATCH");
process.exit(v.verified ? 0 : 1);
