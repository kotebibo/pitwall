use anchor_lang::prelude::*;

use crate::{
    constants::*,
    error::PitWallError,
    state::{Config, Driver},
};

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct DriverParams {
    pub owner: Pubkey,
    pub name: [u8; NAME_LEN],
    pub rarity: u8,
    pub pace: u8,
    pub racecraft: u8,
    pub tyre_management: u8,
    pub potential: u8,
}

#[derive(Accounts)]
#[instruction(driver_id: u64)]
pub struct CreateDriver<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority @ PitWallError::Unauthorized)]
    pub config: Account<'info, Config>,
    #[account(
        init,
        payer = authority,
        space = 8 + Driver::INIT_SPACE,
        seeds = [DRIVER_SEED, &driver_id.to_le_bytes()],
        bump
    )]
    pub driver: Account<'info, Driver>,
    pub system_program: Program<'info, System>,
}

pub fn handle_create_driver(ctx: Context<CreateDriver>, driver_id: u64, params: DriverParams) -> Result<()> {
    require!(
        params.rarity <= 2
            && params.pace <= 100
            && params.racecraft <= 100
            && params.tyre_management <= 100
            && params.potential <= 100
            && params.pace <= params.potential,
        PitWallError::InvalidDriver
    );
    let driver = &mut ctx.accounts.driver;
    driver.driver_id = driver_id;
    driver.owner = params.owner;
    driver.name = params.name;
    driver.rarity = params.rarity;
    driver.pace = params.pace;
    driver.racecraft = params.racecraft;
    driver.tyre_management = params.tyre_management;
    driver.potential = params.potential;
    driver.xp = 0;
    driver.level = 1;
    driver.races = 0;
    driver.wins = 0;
    driver.retired = false;
    driver.bump = ctx.bumps.driver;
    Ok(())
}
