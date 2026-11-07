use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Race, RaceRevealed},
};

#[derive(Accounts)]
pub struct RevealSeed<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [RACE_SEED, &race.race_id.to_le_bytes()], bump = race.bump)]
    pub race: Account<'info, Race>,
}

pub fn handle_reveal_seed(ctx: Context<RevealSeed>, seed: [u8; 32]) -> Result<()> {
    let race = &mut ctx.accounts.race;
    require!(race.status == STATUS_OPEN, PitWallError::WrongStatus);
    require!(Clock::get()?.unix_timestamp >= race.lock_ts, PitWallError::RaceNotLocked);
    require!(race.entries >= 2, PitWallError::NotEnoughEntries);
    require!(
        solana_sha256_hasher::hash(&seed).to_bytes() == race.commitment,
        PitWallError::SeedMismatch
    );

    race.seed = seed;
    race.status = STATUS_REVEALED;
    emit!(RaceRevealed { race_id: race.race_id, seed });
    Ok(())
}
