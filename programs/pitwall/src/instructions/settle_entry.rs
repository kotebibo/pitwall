use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Driver, Entry, Race},
};

#[derive(Accounts)]
pub struct SettleEntry<'info> {
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [RACE_SEED, &race.race_id.to_le_bytes()], bump = race.bump)]
    pub race: Account<'info, Race>,
    #[account(
        mut,
        seeds = [ENTRY_SEED, race.key().as_ref(), driver.key().as_ref()],
        bump = entry.bump,
        has_one = race,
        has_one = driver
    )]
    pub entry: Account<'info, Entry>,
    #[account(mut, seeds = [DRIVER_SEED, &driver.driver_id.to_le_bytes()], bump = driver.bump)]
    pub driver: Account<'info, Driver>,
}

pub fn handle_settle_entry(ctx: Context<SettleEntry>, position: u8) -> Result<()> {
    let race = &mut ctx.accounts.race;
    let entry = &mut ctx.accounts.entry;
    require!(race.status == STATUS_FINISHED, PitWallError::WrongStatus);
    require!(entry.position == 0, PitWallError::AlreadySettled);
    require!(position >= 1 && position <= race.entries, PitWallError::InvalidPosition);
    let bit = 1u16 << (position - 1);
    require!(race.positions_taken & bit == 0, PitWallError::InvalidPosition);

    entry.position = position;
    race.positions_taken |= bit;
    race.settled += 1;

    let driver = &mut ctx.accounts.driver;
    let xp = XP_BY_POSITION
        .get(usize::from(position - 1))
        .copied()
        .unwrap_or(XP_OTHERWISE);
    driver.xp = driver.xp.saturating_add(xp);
    driver.races = driver.races.saturating_add(1);
    if position == 1 {
        driver.wins = driver.wins.saturating_add(1);
    }

    // Levelling: every XP_PER_LEVEL grows pace by one, up to the driver's potential.
    let target_level = u8::try_from(1 + driver.xp / XP_PER_LEVEL).unwrap_or(u8::MAX);
    while driver.level < target_level {
        driver.level += 1;
        if driver.pace < driver.potential {
            driver.pace += 1;
        }
    }

    // Ageing: past their peak, drivers slowly lose pace, then retire.
    if driver.races > PEAK_ENDS_AT_RACES
        && (driver.races - PEAK_ENDS_AT_RACES) % AGEING_EVERY == 0
        && driver.pace > MIN_PACE
    {
        driver.pace -= 1;
    }
    if driver.races >= RETIRE_AT_RACES {
        driver.retired = true;
    }
    Ok(())
}
