# Deploying Pit Wall to Fly.io

One Fly machine serves everything at `https://<app>.fly.dev`: the web game
(`build/web`), the JSON API (`/api/...`) and the headless Godot that re-drives
every lap and race. Files: `Dockerfile`, `.dockerignore`, `fly.toml`,
`deploy/start.sh` (entrypoint).

Run every command from the repo root (`D:\pitwall`). Bash lines work in Git Bash.
PowerShell versions are given where they differ.

## One-time setup

1. **Log in.** Fly needs a payment method on the account.
   ```sh
   fly auth login
   ```

2. **Pick a globally unique app name** and put it in `fly.toml` (`app = "..."`),
   e.g. `pitwall-nino`. Then create the app:
   ```sh
   fly apps create pitwall-nino
   ```
   (Alternative: `fly launch --no-deploy --copy-config --name pitwall-nino`. It
   keeps this fly.toml. Say no if it offers databases or Redis.)

3. **Create the data volume.** It must be in the same region as `primary_region`.
   Fly warns that a single volume has no redundancy. Answer yes: this app runs
   on exactly one machine.
   ```sh
   fly volumes create pitwall_data --size 1 --region fra
   ```

4. **Set the secrets.** Fly stores them encrypted and never shows them again.
   - `SEED_SECRET`: all race seeds, pack rolls and sign-in tokens derive from
     it. **Never commit it, and never reuse the dev default**: the container
     refuses to start on a missing, default or short (<16 chars) secret.
   - `AUTHORITY_KEYPAIR_JSON`: the contents of the Solana keypair that signs as
     the race authority. This is a **devnet** key
     (`J74oyju9PPASQRhUA6zMwRRdrHjLt8M4Fmva4dpHorTg`). Do not reuse it on
     mainnet.

   Bash:
   ```sh
   fly secrets set SEED_SECRET=$(openssl rand -hex 32) AUTHORITY_KEYPAIR_JSON="$(cat ~/.config/solana/id.json)"
   ```
   PowerShell:
   ```powershell
   $b = New-Object byte[] 32
   [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
   $seed = -join ($b | ForEach-Object { $_.ToString('x2') })
   $key = (Get-Content -Raw "$env:USERPROFILE\.config\solana\id.json").Trim()
   fly secrets set "SEED_SECRET=$seed" "AUTHORITY_KEYPAIR_JSON=$key"
   Remove-Variable b, seed, key
   ```
   Changing `SEED_SECRET` later signs everyone out and breaks races that are in
   progress. Do it between race days, not during one.

## Every deploy

1. **Export the web build.** The image copies `build/web` as is and does not
   rebuild it:
   ```bat
   tools\build-web.cmd
   ```
2. **Deploy.** Fly builds the image on its remote builder and uploads about
   60 MB of build context. Add `--local-only` to build with local Docker instead.
   ```sh
   fly deploy
   ```
   The first deploy creates one machine attached to `pitwall_data`. If
   `fly status` ever shows two machines, run `fly scale count 1`. All state
   (qualifying, garages, packs, replays) is JSON on that one volume.

3. **Check it.**
   ```sh
   fly status
   fly logs                                   # look for "Pit Wall server on http://localhost:8080"
   curl https://pitwall-nino.fly.dev/api/health   # {"ok":true,"programId":...,"rpc":"https://api.devnet.solana.com"}
   fly open                                   # opens the game in the browser
   ```
   Share `https://<app>.fly.dev` in the group chat or the MLH submission.

## Good to know

- **Scale to zero.** The machine stops a few minutes after the last request,
  and the next visitor wakes it in a few seconds. The first API call after a
  wake also waits for a few devnet RPC calls (startup checks the Config and
  driver accounts).
- **Cost.** shared-cpu-1x with 1 GB costs about $5.70/month if it runs nonstop
  and is billed per second. Idle, you pay for the 1 GB volume (~$0.15/month)
  plus the stopped machine's disk (~$0.10/month). Traffic is ~44 MB per first
  game load ($0.02/GB in Europe).
- **SOL.** The authority pays for every on-chain action: a submitted lap
  (~0.0016 SOL) and each race (~0.01 SOL, capped by `CHAIN_RACES_PER_DAY`).
  Check the balance with `solana balance J74oyju9PPASQRhUA6zMwRRdrHjLt8M4Fmva4dpHorTg -u devnet`,
  and top up at https://faucet.solana.com.
- **Re-drives run one at a time.** A lap takes ~0.5 s and a race ~7 s of CPU.
  If many players finish races at the same moment they queue. If races feel
  slow, try `fly scale vm performance-1x` (dedicated CPU, costs more).
- **Tuning** without a rebuild: `fly secrets set` or `[env]` in fly.toml, e.g.
  `LOCK_SECONDS`, `CHAIN_RACES_PER_DAY`, `POSTS_PER_MINUTE` (see
  `server/src/config.ts`). Never set `REALTIME_CHECK=0` in production: it is
  for automated tests only.
- **Debugging:** `fly ssh console` (the data is in `/data`), and
  `fly machine restart`.
- **Local run of the same image:**
  ```sh
  docker build -t pitwall .
  docker run --rm -p 8790:8080 -e SEED_SECRET=$(openssl rand -hex 16) \
    -e AUTHORITY_KEYPAIR_JSON="$(cat ~/.config/solana/id.json)" -v pitwall_local:/data pitwall
  # http://localhost:8790
  ```
