use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, LapRecord, LapRecorded},
};

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct LapParams {
    pub circuit: u8,
    pub physics_version: u16,
    /// Lap time in microseconds, as re-driven by the server.
    pub lap_us: u32,
    /// sha256 of the lap's input log.
    pub input_hash: [u8; 32],
}

#[derive(Accounts)]
#[instruction(event_id: u64, player: [u8; 32])]
pub struct SubmitLap<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(
        init_if_needed,
        payer = authority,
        space = 8 + LapRecord::INIT_SPACE,
        seeds = [LAP_SEED, &event_id.to_le_bytes(), &player],
        bump
    )]
    pub lap_record: Account<'info, LapRecord>,
    pub system_program: Program<'info, System>,
}

pub fn handle_submit_lap(ctx: Context<SubmitLap>, event_id: u64, player: [u8; 32], params: LapParams) -> Result<()> {
    require!(params.lap_us > 0 && params.lap_us <= MAX_LAP_US, PitWallError::InvalidLapTime);

    let record = &mut ctx.accounts.lap_record;
    // A fresh record has no laps yet (laps saturates, so it never returns to 0).
    let first = record.laps == 0;
    if first {
        record.event_id = event_id;
        record.player = player;
        record.circuit = params.circuit;
        record.bump = ctx.bumps.lap_record;
    } else {
        require!(record.circuit == params.circuit, PitWallError::CircuitMismatch);
    }

    record.laps = record.laps.saturating_add(1);
    let personal_best = first || params.lap_us < record.best_lap_us;
    if personal_best {
        record.best_lap_us = params.lap_us;
        record.best_input_hash = params.input_hash;
        record.physics_version = params.physics_version;
    }
    record.updated_ts = Clock::get()?.unix_timestamp;

    emit!(LapRecorded { event_id, player, lap_us: params.lap_us, best_lap_us: record.best_lap_us, personal_best });
    Ok(())
}
