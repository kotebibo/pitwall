use anchor_lang::prelude::*;

#[error_code]
pub enum PitWallError {
    #[msg("Only the race authority can do this")]
    Unauthorized,
    #[msg("Only the driver's owner can do this")]
    NotDriverOwner,
    #[msg("Setups are locked for this race")]
    RaceLocked,
    #[msg("The race has not locked yet")]
    RaceNotLocked,
    #[msg("The race is not in the right state for this")]
    WrongStatus,
    #[msg("Revealed seed does not match the commitment")]
    SeedMismatch,
    #[msg("Lock time must be in the future")]
    LockInPast,
    #[msg("Race is full")]
    RaceFull,
    #[msg("A race needs at least two entries")]
    NotEnoughEntries,
    #[msg("Invalid setup")]
    InvalidSetup,
    #[msg("Invalid race parameters")]
    InvalidRace,
    #[msg("Invalid driver stats")]
    InvalidDriver,
    #[msg("This driver has retired")]
    DriverRetired,
    #[msg("Entry already settled")]
    AlreadySettled,
    #[msg("Invalid finishing position")]
    InvalidPosition,
    #[msg("Lap time is out of range")]
    InvalidLapTime,
    #[msg("Lap is on a different circuit than this record")]
    CircuitMismatch,
}
