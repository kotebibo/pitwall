use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, PassPool},
};

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct PoolParams {
    pub entry_lamports: u64,
    pub closes_ts: i64,
    pub rake_bps: u16,
}

#[derive(Accounts)]
#[instruction(pool_id: u64)]
pub struct CreatePool<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(
        init,
        payer = authority,
        space = 8 + PassPool::INIT_SPACE,
        seeds = [POOL_SEED, &pool_id.to_le_bytes()],
        bump
    )]
    pub pool: Account<'info, PassPool>,
    pub system_program: Program<'info, System>,
}

pub fn handle_create_pool(ctx: Context<CreatePool>, pool_id: u64, params: PoolParams) -> Result<()> {
    require!(params.entry_lamports > 0, PitWallError::InvalidPool);
    require!(params.rake_bps <= MAX_RAKE_BPS, PitWallError::InvalidPool);
    require!(params.closes_ts > Clock::get()?.unix_timestamp, PitWallError::LockInPast);
    let pool = &mut ctx.accounts.pool;
    pool.pool_id = pool_id;
    pool.entry_lamports = params.entry_lamports;
    pool.closes_ts = params.closes_ts;
    pool.rake_bps = params.rake_bps;
    pool.bump = ctx.bumps.pool;
    Ok(())
}
