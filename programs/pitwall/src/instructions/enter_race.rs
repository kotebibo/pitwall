use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Driver, Entry, Race},
};

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct SetupParams {
    pub team_name: [u8; NAME_LEN],
    pub design: u8,
    pub tyre: u8,
    pub stops: u8,
    pub risk: u8,
}

#[derive(Accounts)]
pub struct EnterRace<'info> {
    /// The driver's owner, or the race authority entering on a player's behalf.
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [RACE_SEED, &race.race_id.to_le_bytes()], bump = race.bump)]
    pub race: Account<'info, Race>,
    #[account(seeds = [DRIVER_SEED, &driver.driver_id.to_le_bytes()], bump = driver.bump)]
    pub driver: Account<'info, Driver>,
    #[account(
        init,
        payer = signer,
        space = 8 + Entry::INIT_SPACE,
        seeds = [ENTRY_SEED, race.key().as_ref(), driver.key().as_ref()],
        bump
    )]
    pub entry: Account<'info, Entry>,
    pub system_program: Program<'info, System>,
}

pub fn handle_enter_race(ctx: Context<EnterRace>, setup: SetupParams) -> Result<()> {
    let signer = ctx.accounts.signer.key();
    let driver = &ctx.accounts.driver;
    require!(
        signer == driver.owner || signer == ctx.accounts.config.authority,
        PitWallError::NotDriverOwner
    );
    require!(!driver.retired, PitWallError::DriverRetired);

    let race = &mut ctx.accounts.race;
    require!(race.status == STATUS_OPEN, PitWallError::WrongStatus);
    require!(Clock::get()?.unix_timestamp < race.lock_ts, PitWallError::RaceLocked);
    require!(race.entries < MAX_ENTRIES, PitWallError::RaceFull);
    require!(
        setup.design < DESIGNS && setup.tyre < TYRES && (setup.stops == 1 || setup.stops == 2) && setup.risk <= 100,
        PitWallError::InvalidSetup
    );

    let entry = &mut ctx.accounts.entry;
    entry.race = race.key();
    entry.driver = driver.key();
    entry.owner = driver.owner;
    entry.slot = race.entries;
    entry.team_name = setup.team_name;
    entry.design = setup.design;
    entry.tyre = setup.tyre;
    entry.stops = setup.stops;
    entry.risk = setup.risk;
    entry.pace = driver.pace;
    entry.racecraft = driver.racecraft;
    entry.tyre_management = driver.tyre_management;
    entry.position = 0;
    entry.bump = ctx.bumps.entry;

    race.entries += 1;
    Ok(())
}
