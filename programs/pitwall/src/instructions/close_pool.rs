use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, PassPool, PoolSettled},
};

#[derive(Accounts)]
pub struct ClosePool<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [POOL_SEED, &pool.pool_id.to_le_bytes()], bump = pool.bump)]
    pub pool: Account<'info, PassPool>,
}

/// Closes a pool once every payout is made. Players must have received exactly the
/// stakes minus Pit Wall's share (or every stake back, for a refunded pool); only
/// then does the share go to the authority.
pub fn handle_close_pool(ctx: Context<ClosePool>, results_hash: [u8; 32], refund: bool) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;
    let pool = &ctx.accounts.pool;
    require!(!pool.closed, PitWallError::PoolClosed);
    require!(now >= pool.closes_ts, PitWallError::PoolStillOpen);
    let rake = if refund { 0 } else { (pool.total_lamports as u128 * pool.rake_bps as u128 / 10_000) as u64 };
    require!(pool.paid_lamports.checked_add(rake) == Some(pool.total_lamports), PitWallError::PayoutMismatch);
    if rake > 0 {
        **ctx.accounts.pool.to_account_info().try_borrow_mut_lamports()? -= rake;
        **ctx.accounts.authority.to_account_info().try_borrow_mut_lamports()? += rake;
    }
    let pool = &mut ctx.accounts.pool;
    pool.closed = true;
    pool.results_hash = results_hash;
    emit!(PoolSettled { pool_id: pool.pool_id, results_hash, rake, refunded: refund });
    Ok(())
}
