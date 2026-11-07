use anchor_lang::prelude::*;

use crate::{error::PitWallError, state::Driver};

#[derive(Accounts)]
pub struct TransferDriver<'info> {
    pub owner: Signer<'info>,
    #[account(mut, has_one = owner @ PitWallError::NotDriverOwner)]
    pub driver: Account<'info, Driver>,
}

pub fn handle_transfer_driver(ctx: Context<TransferDriver>, new_owner: Pubkey) -> Result<()> {
    ctx.accounts.driver.owner = new_owner;
    Ok(())
}
