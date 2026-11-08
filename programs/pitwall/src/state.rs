use anchor_lang::prelude::*;

use crate::constants::NAME_LEN;

/// Who may create races and drivers and settle results: the Pit Wall race server.
#[account]
#[derive(InitSpace)]
pub struct Config {
    pub authority: Pubkey,
    pub bump: u8,
}

/// One race. The seed is committed (as its sha256) before setups lock and
/// revealed after; the program checks the two match.
#[account]
#[derive(InitSpace)]
pub struct Race {
    pub race_id: u64,
    pub track_type: u8,
    pub laps: u16,
    pub base_lap_ms: u32,
    pub commitment: [u8; 32],
    pub lock_ts: i64,
    pub seed: [u8; 32],
    pub result_hash: [u8; 32],
    pub entries: u8,
    pub settled: u8,
    /// Bit n set = position n+1 already awarded (each position once).
    pub positions_taken: u16,
    pub status: u8,
    pub bump: u8,
}

/// A driver owned by a player. Levels up only by racing, ages, retires.
#[account]
#[derive(InitSpace)]
pub struct Driver {
    pub driver_id: u64,
    pub owner: Pubkey,
    pub name: [u8; NAME_LEN],
    pub rarity: u8,
    pub pace: u8,
    pub racecraft: u8,
    pub tyre_management: u8,
    /// Highest pace this driver can reach by levelling (rarity raises the ceiling).
    pub potential: u8,
    pub xp: u32,
    pub level: u8,
    pub races: u16,
    pub wins: u16,
    pub retired: bool,
    pub bump: u8,
}

/// A team's locked setup for one race. Driver stats are snapshotted at entry,
/// so the race can be re-run exactly even after the driver changes.
#[account]
#[derive(InitSpace)]
pub struct Entry {
    pub race: Pubkey,
    pub driver: Pubkey,
    pub owner: Pubkey,
    /// Order of entry; the sim takes teams in slot order.
    pub slot: u8,
    pub team_name: [u8; NAME_LEN],
    pub design: u8,
    pub tyre: u8,
    pub stops: u8,
    pub risk: u8,
    pub pace: u8,
    pub racecraft: u8,
    pub tyre_management: u8,
    /// Finishing position, 1-based; 0 until settled.
    pub position: u8,
    pub bump: u8,
}

/// A player's best verified qualifying lap at one event. The server re-drives
/// every lap from its input log before submitting; the input hash pins that log.
#[account]
#[derive(InitSpace)]
pub struct LapRecord {
    pub event_id: u64,
    /// sha256 of the player's id (players have no wallets).
    pub player: [u8; 32],
    pub circuit: u8,
    /// Physics version the best lap was driven on.
    pub physics_version: u16,
    /// Best lap time in microseconds.
    pub best_lap_us: u32,
    /// sha256 of the best lap's input log.
    pub best_input_hash: [u8; 32],
    /// Verified laps submitted.
    pub laps: u16,
    pub updated_ts: i64,
    pub bump: u8,
}

/// A race-pass prize pool. Players stake `entry_lamports` to enter a timed event and
/// are paid by where they place. Stakes sit in this account until the results are paid.
#[account]
#[derive(InitSpace)]
pub struct PassPool {
    pub pool_id: u64,
    pub entry_lamports: u64,
    pub closes_ts: i64,
    /// Pit Wall's share of the stakes, in basis points (at most MAX_RAKE_BPS).
    pub rake_bps: u16,
    pub entrants: u32,
    /// Stakes received.
    pub total_lamports: u64,
    /// Paid out to players so far.
    pub paid_lamports: u64,
    /// sha256 of the final standings the server published, set at close.
    pub results_hash: [u8; 32],
    pub closed: bool,
    pub bump: u8,
}

/// One player's race pass in one pool.
#[account]
#[derive(InitSpace)]
pub struct PassEntry {
    pub pool: Pubkey,
    pub player: Pubkey,
    pub entered_ts: i64,
    /// Lamports paid to the player (0 until paid).
    pub payout: u64,
    pub paid: bool,
    pub bump: u8,
}

#[event]
pub struct PassBought {
    pub pool_id: u64,
    pub player: Pubkey,
    pub entrants: u32,
    pub total_lamports: u64,
}

#[event]
pub struct PassPaid {
    pub pool_id: u64,
    pub player: Pubkey,
    pub amount: u64,
}

#[event]
pub struct PoolSettled {
    pub pool_id: u64,
    pub results_hash: [u8; 32],
    pub rake: u64,
    pub refunded: bool,
}

#[event]
pub struct RaceRevealed {
    pub race_id: u64,
    pub seed: [u8; 32],
}

#[event]
pub struct RaceFinished {
    pub race_id: u64,
    pub result_hash: [u8; 32],
}

#[event]
pub struct LapRecorded {
    pub event_id: u64,
    pub player: [u8; 32],
    pub lap_us: u32,
    pub best_lap_us: u32,
    pub personal_best: bool,
}
