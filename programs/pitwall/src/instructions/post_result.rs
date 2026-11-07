use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Race, RaceFinished},
};

#[derive(Accounts)]
pub struct PostResult<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [RACE_SEED, &race.race_id.to_le_bytes()], bump = race.bump)]
    pub race: Account<'info, Race>,
}

pub fn handle_post_result(ctx: Context<PostResult>, result_hash: [u8; 32]) -> Result<()> {
    let race = &mut ctx.accounts.race;
    require!(race.status == STATUS_REVEALED, PitWallError::WrongStatus);
    race.result_hash = result_hash;
    race.status = STATUS_FINISHED;
    emit!(RaceFinished { race_id: race.race_id, result_hash });
    Ok(())
}
