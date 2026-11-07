use anchor_lang::prelude::*;

#[constant]
pub const CONFIG_SEED: &[u8] = b"config";
#[constant]
pub const RACE_SEED: &[u8] = b"race";
#[constant]
pub const DRIVER_SEED: &[u8] = b"driver";
#[constant]
pub const ENTRY_SEED: &[u8] = b"entry";
#[constant]
pub const LAP_SEED: &[u8] = b"lap";

pub const NAME_LEN: usize = 24;
pub const MAX_ENTRIES: u8 = 12;
pub const MAX_LAPS: u16 = 80;
pub const TRACK_TYPES: u8 = 3; // street, speed, mixed
pub const DESIGNS: u8 = 3; // high downforce, balanced, low drag
pub const TYRES: u8 = 3; // soft, medium, hard

// Race status
pub const STATUS_OPEN: u8 = 0;
pub const STATUS_REVEALED: u8 = 1;
pub const STATUS_FINISHED: u8 = 2;

// Driver progression
pub const XP_PER_LEVEL: u32 = 100;
pub const XP_BY_POSITION: [u32; 6] = [50, 35, 25, 18, 12, 8];
pub const XP_OTHERWISE: u32 = 5;
pub const PEAK_ENDS_AT_RACES: u16 = 40; // after this, pace drops by 1 every AGEING_EVERY races
pub const AGEING_EVERY: u16 = 5;
pub const RETIRE_AT_RACES: u16 = 80;
pub const MIN_PACE: u8 = 20;

// Qualifying laps
pub const MAX_LAP_US: u32 = 600_000_000; // ten minutes, in microseconds
