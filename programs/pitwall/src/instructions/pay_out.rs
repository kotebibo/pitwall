use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, PassEntry, PassPaid, PassPool},
};

#[derive(Accounts)]
pub struct PayOut<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [POOL_SEED, &pool.pool_id.to_le_bytes()], bump = pool.bump)]
    pub pool: Account<'info, PassPool>,
    #[account(
        mut,
        seeds = [PASS_SEED, pool.key().as_ref(), entry.player.as_ref()],
        bump = entry.bump,
        has_one = pool
    )]
    pub entry: Account<'info, PassEntry>,
    /// CHECK: the wallet that bought the pass; it can only receive lamports here.
    #[account(mut, address = entry.player)]
    pub player: UncheckedAccount<'info>,
}

/// Pays one entrant after the pool has closed for entries. Each pass is paid at most once,
/// and the total can never exceed the stakes.
pub fn handle_pay_out(ctx: Context<PayOut>, amount: u64) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;
    let pool = &ctx.accounts.pool;
    require!(!pool.closed, PitWallError::PoolClosed);
    require!(now >= pool.closes_ts, PitWallError::PoolStillOpen);
    require!(!ctx.accounts.entry.paid, PitWallError::AlreadySettled);
    require!(amount > 0, PitWallError::InvalidPool);
    let paid = pool.paid_lamports.checked_add(amount).ok_or(PitWallError::Overpaid)?;
    require!(paid <= pool.total_lamports, PitWallError::Overpaid);

    **ctx.accounts.pool.to_account_info().try_borrow_mut_lamports()? -= amount;
    **ctx.accounts.player.to_account_info().try_borrow_mut_lamports()? += amount;

    let pool = &mut ctx.accounts.pool;
    pool.paid_lamports = paid;
    let entry = &mut ctx.accounts.entry;
    entry.paid = true;
    entry.payout = amount;
    emit!(PassPaid { pool_id: pool.pool_id, player: entry.player, amount });
    Ok(())
}
