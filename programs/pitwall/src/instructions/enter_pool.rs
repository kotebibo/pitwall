use anchor_lang::{
    prelude::*,
    system_program::{transfer, Transfer},
};

use crate::{
    constants::*,
    error::PitWallError,
    state::{PassBought, PassEntry, PassPool},
};

#[derive(Accounts)]
pub struct EnterPool<'info> {
    #[account(mut)]
    pub player: Signer<'info>,
    #[account(mut, seeds = [POOL_SEED, &pool.pool_id.to_le_bytes()], bump = pool.bump)]
    pub pool: Account<'info, PassPool>,
    #[account(
        init,
        payer = player,
        space = 8 + PassEntry::INIT_SPACE,
        seeds = [PASS_SEED, pool.key().as_ref(), player.key().as_ref()],
        bump
    )]
    pub entry: Account<'info, PassEntry>,
    pub system_program: Program<'info, System>,
}

/// Buys a race pass: the stake moves from the player's wallet into the pool.
pub fn handle_enter_pool(ctx: Context<EnterPool>) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;
    let pool = &ctx.accounts.pool;
    require!(!pool.closed && now < pool.closes_ts, PitWallError::PoolClosed);
    let stake = pool.entry_lamports;
    transfer(
        CpiContext::new(
            ctx.accounts.system_program.key(),
            Transfer { from: ctx.accounts.player.to_account_info(), to: ctx.accounts.pool.to_account_info() },
        ),
        stake,
    )?;
    let pool = &mut ctx.accounts.pool;
    pool.entrants = pool.entrants.checked_add(1).ok_or(PitWallError::InvalidPool)?;
    pool.total_lamports = pool.total_lamports.checked_add(stake).ok_or(PitWallError::InvalidPool)?;
    let entry = &mut ctx.accounts.entry;
    entry.pool = pool.key();
    entry.player = ctx.accounts.player.key();
    entry.entered_ts = now;
    entry.bump = ctx.bumps.entry;
    emit!(PassBought { pool_id: pool.pool_id, player: entry.player, entrants: pool.entrants, total_lamports: pool.total_lamports });
    Ok(())
}
