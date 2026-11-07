use {
    anchor_lang::{
        prelude::{Clock, Pubkey},
        solana_program::{instruction::Instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    pitwall::{constants::*, error::PitWallError, instruction as ix, state::LapRecord, LapParams},
    solana_keypair::Keypair,
    solana_message::{Message, VersionedMessage},
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
};

const EVENT: u64 = 42;
const CIRCUIT: u8 = 2;

struct World {
    svm: LiteSVM,
    authority: Keypair,
    config: Pubkey,
}

fn pda(seeds: &[&[u8]]) -> Pubkey {
    Pubkey::find_program_address(seeds, &pitwall::id()).0
}
fn lap_pda(event_id: u64, player: &[u8; 32]) -> Pubkey {
    pda(&[LAP_SEED, &event_id.to_le_bytes(), player])
}
fn sha256(data: &[u8]) -> [u8; 32] {
    solana_sha256_hasher::hash(data).to_bytes()
}
/// The error string a failed transaction carries for a program error.
fn code(e: PitWallError) -> String {
    format!("Custom({})", u32::from(e))
}
fn lap(lap_us: u32, input_log: &[u8]) -> LapParams {
    LapParams { circuit: CIRCUIT, physics_version: 1, lap_us, input_hash: sha256(input_log) }
}

impl World {
    fn new() -> Self {
        let mut svm = LiteSVM::new();
        let bytes = include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../target/deploy/pitwall.so"));
        svm.add_program(pitwall::id(), bytes).unwrap();
        let authority = Keypair::new();
        svm.airdrop(&authority.pubkey(), 10_000_000_000).unwrap();
        let config = pda(&[CONFIG_SEED]);
        let mut w = World { svm, authority, config };
        let init = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::Initialize { authority: w.authority.pubkey() }.data(),
            pitwall::accounts::Initialize { payer: w.authority.pubkey(), config, system_program: system_program::ID }
                .to_account_metas(None),
        );
        let auth = w.authority.insecure_clone();
        w.send(init, &auth).unwrap();
        w
    }

    fn send(&mut self, instruction: Instruction, signer: &Keypair) -> Result<(), String> {
        self.svm.expire_blockhash();
        let msg = Message::new_with_blockhash(&[instruction], Some(&signer.pubkey()), &self.svm.latest_blockhash());
        let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[signer]).unwrap();
        self.svm.send_transaction(tx).map(|_| ()).map_err(|e| format!("{:?}", e.err))
    }

    fn now(&self) -> i64 {
        self.svm.get_sysvar::<Clock>().unix_timestamp
    }

    fn advance(&mut self, seconds: i64) {
        let mut clock = self.svm.get_sysvar::<Clock>();
        clock.unix_timestamp += seconds;
        self.svm.set_sysvar::<Clock>(&clock);
    }

    fn account<T: AccountDeserialize>(&self, key: &Pubkey) -> T {
        let acc = self.svm.get_account(key).unwrap();
        T::try_deserialize(&mut acc.data.as_slice()).unwrap()
    }

    fn submit_ix(&self, signer: &Pubkey, event_id: u64, player: [u8; 32], params: LapParams) -> Instruction {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::SubmitLap { event_id, player, params }.data(),
            pitwall::accounts::SubmitLap {
                authority: *signer,
                config: self.config,
                lap_record: lap_pda(event_id, &player),
                system_program: system_program::ID,
            }
            .to_account_metas(None),
        )
    }

    /// Submits a lap signed by the authority.
    fn submit(&mut self, player: [u8; 32], params: LapParams) -> Result<(), String> {
        let auth = self.authority.insecure_clone();
        let i = self.submit_ix(&auth.pubkey(), EVENT, player, params);
        self.send(i, &auth)
    }
}

#[test]
fn first_lap_creates_the_record() {
    let mut w = World::new();
    let player = sha256(b"player:nino");
    w.submit(player, lap(83_412_500, b"lap one")).unwrap();

    let r: LapRecord = w.account(&lap_pda(EVENT, &player));
    assert_eq!((r.event_id, r.player, r.circuit, r.physics_version), (EVENT, player, CIRCUIT, 1));
    assert_eq!((r.best_lap_us, r.best_input_hash, r.laps), (83_412_500, sha256(b"lap one"), 1));
    assert_eq!(r.updated_ts, w.now());
}

#[test]
fn a_slower_lap_counts_but_keeps_the_best() {
    let mut w = World::new();
    let player = sha256(b"player:nino");
    w.submit(player, lap(83_000_000, b"quick")).unwrap();
    w.advance(30);
    w.submit(player, LapParams { physics_version: 2, ..lap(85_000_000, b"slow") }).unwrap();

    let r: LapRecord = w.account(&lap_pda(EVENT, &player));
    assert_eq!(r.laps, 2);
    assert_eq!((r.best_lap_us, r.best_input_hash, r.physics_version), (83_000_000, sha256(b"quick"), 1));
    assert_eq!(r.updated_ts, w.now(), "every lap refreshes updated_ts");
}

#[test]
fn a_faster_lap_replaces_the_best_and_its_hash() {
    let mut w = World::new();
    let player = sha256(b"player:nino");
    w.submit(player, lap(85_000_000, b"slow")).unwrap();
    w.advance(30);
    w.submit(player, LapParams { physics_version: 2, ..lap(82_500_000, b"faster") }).unwrap();

    let r: LapRecord = w.account(&lap_pda(EVENT, &player));
    assert_eq!(r.laps, 2);
    assert_eq!((r.best_lap_us, r.best_input_hash, r.physics_version), (82_500_000, sha256(b"faster"), 2));
    assert_eq!(r.updated_ts, w.now());

    // Records are per player and per event.
    let other = sha256(b"player:giorgi");
    w.submit(other, lap(90_000_000, b"other")).unwrap();
    let r: LapRecord = w.account(&lap_pda(EVENT, &player));
    assert_eq!((r.best_lap_us, r.laps), (82_500_000, 2));
}

#[test]
fn only_the_authority_records_laps() {
    let mut w = World::new();
    let mallory = Keypair::new();
    w.svm.airdrop(&mallory.pubkey(), 1_000_000_000).unwrap();
    let player = sha256(b"player:nino");
    let i = w.submit_ix(&mallory.pubkey(), EVENT, player, lap(60_000_000, b"forged"));
    let err = w.send(i, &mallory).unwrap_err();
    assert!(err.contains(&code(PitWallError::Unauthorized)), "non-authority must fail, got {err}");
    assert!(w.svm.get_account(&lap_pda(EVENT, &player)).is_none_or(|a| a.data.is_empty()), "no record is created");
}

#[test]
fn out_of_range_lap_times_are_rejected() {
    let mut w = World::new();
    let player = sha256(b"player:nino");
    let err = w.submit(player, lap(0, b"zero")).unwrap_err();
    assert!(err.contains(&code(PitWallError::InvalidLapTime)), "zero lap time must fail, got {err}");
    let err = w.submit(player, lap(MAX_LAP_US + 1, b"too long")).unwrap_err();
    assert!(err.contains(&code(PitWallError::InvalidLapTime)), "over ten minutes must fail, got {err}");
    w.submit(player, lap(MAX_LAP_US, b"just in")).unwrap();
}

#[test]
fn a_record_keeps_its_circuit() {
    let mut w = World::new();
    let player = sha256(b"player:nino");
    w.submit(player, lap(83_000_000, b"first")).unwrap();
    let err = w.submit(player, LapParams { circuit: CIRCUIT + 1, ..lap(80_000_000, b"elsewhere") }).unwrap_err();
    assert!(err.contains(&code(PitWallError::CircuitMismatch)), "circuit change must fail, got {err}");
    let r: LapRecord = w.account(&lap_pda(EVENT, &player));
    assert_eq!((r.best_lap_us, r.laps), (83_000_000, 1));
}
