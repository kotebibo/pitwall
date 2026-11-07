pub mod constants;
pub mod error;
pub mod instructions;
pub mod state;

use anchor_lang::prelude::*;

pub use constants::*;
pub use instructions::*;
pub use state::*;

declare_id!("FRMukL3ubSZcGHxAFjK1ywSqfY3bWod2ro1ySoULwH4r");

/// Pit Wall: races whose fairness and timeline are enforced on-chain,
/// and drivers that players own, level up by racing, age and retire.
#[program]
pub mod pitwall {
    use super::*;

    /// One-time setup: records which key runs races (the Pit Wall server).
    pub fn initialize(ctx: Context<Initialize>, authority: Pubkey) -> Result<()> {
        instructions::initialize::handle_initialize(ctx, authority)
    }

    pub fn create_driver(ctx: Context<CreateDriver>, driver_id: u64, params: DriverParams) -> Result<()> {
        instructions::create_driver::handle_create_driver(ctx, driver_id, params)
    }

    pub fn transfer_driver(ctx: Context<TransferDriver>, new_owner: Pubkey) -> Result<()> {
        instructions::transfer_driver::handle_transfer_driver(ctx, new_owner)
    }

    /// Opens a race with the seed's commitment (sha256 of the seed) and the lock time.
    pub fn create_race(ctx: Context<CreateRace>, race_id: u64, params: RaceParams) -> Result<()> {
        instructions::create_race::handle_create_race(ctx, race_id, params)
    }

    /// Locks in a setup. Rejected once the race has locked.
    pub fn enter_race(ctx: Context<EnterRace>, setup: SetupParams) -> Result<()> {
        instructions::enter_race::handle_enter_race(ctx, setup)
    }

    /// Reveals the seed after the lock; the program checks it against the commitment.
    pub fn reveal_seed(ctx: Context<RevealSeed>, seed: [u8; 32]) -> Result<()> {
        instructions::reveal_seed::handle_reveal_seed(ctx, seed)
    }

    /// Records the hash of the simulated result, re-runnable by anyone from on-chain data.
    pub fn post_result(ctx: Context<PostResult>, result_hash: [u8; 32]) -> Result<()> {
        instructions::post_result::handle_post_result(ctx, result_hash)
    }

    /// Awards a finishing position and applies XP, levelling and ageing to the driver.
    pub fn settle_entry(ctx: Context<SettleEntry>, position: u8) -> Result<()> {
        instructions::settle_entry::handle_settle_entry(ctx, position)
    }

    /// Records a lap the server has re-driven and verified; keeps the player's best.
    pub fn submit_lap(ctx: Context<SubmitLap>, event_id: u64, player: [u8; 32], params: LapParams) -> Result<()> {
        instructions::submit_lap::handle_submit_lap(ctx, event_id, player, params)
    }
}
