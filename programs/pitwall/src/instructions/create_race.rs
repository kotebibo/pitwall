use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Race},
};

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct RaceParams {
    pub track_type: u8,
    pub laps: u16,
    pub base_lap_ms: u32,
    /// sha256 of the 32-byte seed, which stays secret until the race locks.
    pub commitment: [u8; 32],
    /// Unix time after which no setups are accepted and the seed may be revealed.
    pub lock_ts: i64,
}

#[derive(Accounts)]
#[instruction(race_id: u64)]
pub struct CreateRace<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(
        init,
        payer = authority,
        space = 8 + Race::INIT_SPACE,
        seeds = [RACE_SEED, &race_id.to_le_bytes()],
        bump
    )]
    pub race: Account<'info, Race>,
    pub system_program: Program<'info, System>,
}

pub fn handle_create_race(ctx: Context<CreateRace>, race_id: u64, params: RaceParams) -> Result<()> {
    require!(
        params.track_type < TRACK_TYPES
            && params.laps >= 1
            && params.laps <= MAX_LAPS
            && (30_000..=300_000).contains(&params.base_lap_ms),
        PitWallError::InvalidRace
    );
    let now = Clock::get()?.unix_timestamp;
    require!(params.lock_ts > now, PitWallError::LockInPast);

    let race = &mut ctx.accounts.race;
    race.race_id = race_id;
    race.track_type = params.track_type;
    race.laps = params.laps;
    race.base_lap_ms = params.base_lap_ms;
    race.commitment = params.commitment;
    race.lock_ts = params.lock_ts;
    race.seed = [0; 32];
    race.result_hash = [0; 32];
    race.entries = 0;
    race.settled = 0;
    race.positions_taken = 0;
    race.status = STATUS_OPEN;
    race.bump = ctx.bumps.race;
    Ok(())
}
