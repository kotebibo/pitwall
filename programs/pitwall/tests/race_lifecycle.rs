use {
    anchor_lang::{
        prelude::{Clock, Pubkey},
        solana_program::{instruction::Instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    pitwall::{
        constants::*, instruction as ix, DriverParams, RaceParams, SetupParams,
        state::{Driver, Entry, Race},
    },
    solana_keypair::Keypair,
    solana_message::{Message, VersionedMessage},
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
};

const LOCK_IN: i64 = 60;

struct World {
    svm: LiteSVM,
    authority: Keypair,
    config: Pubkey,
}

fn pda(seeds: &[&[u8]]) -> Pubkey {
    Pubkey::find_program_address(seeds, &pitwall::id()).0
}
fn race_pda(race_id: u64) -> Pubkey {
    pda(&[RACE_SEED, &race_id.to_le_bytes()])
}
fn driver_pda(driver_id: u64) -> Pubkey {
    pda(&[DRIVER_SEED, &driver_id.to_le_bytes()])
}
fn entry_pda(race: &Pubkey, driver: &Pubkey) -> Pubkey {
    pda(&[ENTRY_SEED, race.as_ref(), driver.as_ref()])
}
fn name(s: &str) -> [u8; NAME_LEN] {
    let mut out = [0u8; NAME_LEN];
    out[..s.len()].copy_from_slice(s.as_bytes());
    out
}
fn sha256(data: &[u8]) -> [u8; 32] {
    solana_sha256_hasher::hash(data).to_bytes()
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

    fn create_driver(&mut self, driver_id: u64, owner: Pubkey, pace: u8, potential: u8) -> Pubkey {
        let driver = driver_pda(driver_id);
        let auth = self.authority.insecure_clone();
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::CreateDriver {
                driver_id,
                params: DriverParams {
                    owner,
                    name: name("Nino Beridze"),
                    rarity: 0,
                    pace,
                    racecraft: 70,
                    tyre_management: 60,
                    potential,
                },
            }
            .data(),
            pitwall::accounts::CreateDriver { authority: auth.pubkey(), config: self.config, driver, system_program: system_program::ID }
                .to_account_metas(None),
        );
        self.send(i, &auth).unwrap();
        driver
    }

    fn create_race(&mut self, race_id: u64, seed: &[u8; 32]) -> Pubkey {
        let race = race_pda(race_id);
        let auth = self.authority.insecure_clone();
        let lock_ts = self.now() + LOCK_IN;
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::CreateRace {
                race_id,
                params: RaceParams { track_type: 0, laps: 24, base_lap_ms: 92_000, commitment: sha256(seed), lock_ts },
            }
            .data(),
            pitwall::accounts::CreateRace { authority: auth.pubkey(), config: self.config, race, system_program: system_program::ID }
                .to_account_metas(None),
        );
        self.send(i, &auth).unwrap();
        race
    }

    fn enter_ix(&self, signer: &Pubkey, race: Pubkey, driver: Pubkey) -> Instruction {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::EnterRace {
                setup: SetupParams { team_name: name("Tbilisi Racing"), design: 0, tyre: 0, stops: 1, risk: 55 },
            }
            .data(),
            pitwall::accounts::EnterRace {
                signer: *signer,
                config: self.config,
                race,
                driver,
                entry: entry_pda(&race, &driver),
                system_program: system_program::ID,
            }
            .to_account_metas(None),
        )
    }

    fn reveal_ix(&self, race: Pubkey, seed: [u8; 32]) -> Instruction {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::RevealSeed { seed }.data(),
            pitwall::accounts::RevealSeed { authority: self.authority.pubkey(), config: self.config, race }.to_account_metas(None),
        )
    }

    fn post_result_ix(&self, race: Pubkey, result_hash: [u8; 32]) -> Instruction {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::PostResult { result_hash }.data(),
            pitwall::accounts::PostResult { authority: self.authority.pubkey(), config: self.config, race }.to_account_metas(None),
        )
    }

    fn settle_ix(&self, race: Pubkey, driver: Pubkey, position: u8) -> Instruction {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::SettleEntry { position }.data(),
            pitwall::accounts::SettleEntry {
                authority: self.authority.pubkey(),
                config: self.config,
                race,
                entry: entry_pda(&race, &driver),
                driver,
            }
            .to_account_metas(None),
        )
    }
}

fn player() -> Keypair {
    Keypair::new()
}

#[test]
fn full_race_lifecycle_is_enforced_on_chain() {
    let mut w = World::new();
    let alice = player();
    let bob = player();
    w.svm.airdrop(&alice.pubkey(), 1_000_000_000).unwrap();
    let d1 = w.create_driver(1, alice.pubkey(), 60, 75);
    let d2 = w.create_driver(2, bob.pubkey(), 70, 70);

    let seed = [7u8; 32];
    let race = w.create_race(100, &seed);

    // A player enters with their own key; the authority enters for a custodial player.
    let i = w.enter_ix(&alice.pubkey(), race, d1);
    w.send(i, &alice).unwrap();
    let auth = w.authority.insecure_clone();
    let i = w.enter_ix(&auth.pubkey(), race, d2);
    w.send(i, &auth).unwrap();
    let entry: Entry = w.account(&entry_pda(&race, &d1));
    assert_eq!((entry.slot, entry.design, entry.risk, entry.pace), (0, 0, 55, 60));

    // No reveal before the lock.
    let i = w.reveal_ix(race, seed);
    assert!(w.send(i, &auth).unwrap_err().contains("Custom"), "reveal before lock must fail");

    w.advance(LOCK_IN);

    // No entries after the lock.
    let d3 = w.create_driver(3, alice.pubkey(), 50, 60);
    let i = w.enter_ix(&alice.pubkey(), race, d3);
    assert!(w.send(i, &alice).is_err(), "entry after lock must fail");

    // The seed must match the commitment.
    let i = w.reveal_ix(race, [8u8; 32]);
    assert!(w.send(i, &auth).is_err(), "wrong seed must fail");
    let i = w.reveal_ix(race, seed);
    w.send(i, &auth).unwrap();
    let r: Race = w.account(&race);
    assert_eq!((r.status, r.seed), (STATUS_REVEALED, seed));

    let i = w.post_result_ix(race, [9u8; 32]);
    w.send(i, &auth).unwrap();

    // Results update drivers; each position once; each entry once.
    let i = w.settle_ix(race, d1, 1);
    w.send(i, &auth).unwrap();
    let i = w.settle_ix(race, d2, 1);
    assert!(w.send(i, &auth).is_err(), "position 1 twice must fail");
    let i = w.settle_ix(race, d2, 2);
    w.send(i, &auth).unwrap();
    let i = w.settle_ix(race, d1, 2);
    assert!(w.send(i, &auth).is_err(), "settling twice must fail");

    let winner: Driver = w.account(&d1);
    assert_eq!((winner.xp, winner.races, winner.wins, winner.level), (50, 1, 1, 1));
    let r: Race = w.account(&race);
    assert_eq!((r.status, r.settled, r.result_hash), (STATUS_FINISHED, 2, [9u8; 32]));
}

#[test]
fn only_the_authority_runs_races() {
    let mut w = World::new();
    let mallory = player();
    w.svm.airdrop(&mallory.pubkey(), 1_000_000_000).unwrap();
    let race = race_pda(5);
    let lock_ts = w.now() + LOCK_IN;
    let i = Instruction::new_with_bytes(
        pitwall::id(),
        &ix::CreateRace {
            race_id: 5,
            params: RaceParams { track_type: 0, laps: 24, base_lap_ms: 92_000, commitment: [0; 32], lock_ts },
        }
        .data(),
        pitwall::accounts::CreateRace { authority: mallory.pubkey(), config: w.config, race, system_program: system_program::ID }
            .to_account_metas(None),
    );
    assert!(w.send(i, &mallory).is_err());
}

#[test]
fn owners_can_transfer_drivers_and_others_cannot() {
    let mut w = World::new();
    let alice = player();
    let bob = player();
    w.svm.airdrop(&alice.pubkey(), 1_000_000_000).unwrap();
    w.svm.airdrop(&bob.pubkey(), 1_000_000_000).unwrap();
    let d = w.create_driver(9, alice.pubkey(), 60, 80);
    let transfer = |from: &Keypair, to: Pubkey| {
        Instruction::new_with_bytes(
            pitwall::id(),
            &ix::TransferDriver { new_owner: to }.data(),
            pitwall::accounts::TransferDriver { owner: from.pubkey(), driver: d }.to_account_metas(None),
        )
    };
    assert!(w.send(transfer(&bob, bob.pubkey()), &bob).is_err(), "non-owner transfer must fail");
    w.send(transfer(&alice, bob.pubkey()), &alice).unwrap();
    let driver: Driver = w.account(&d);
    assert_eq!(driver.owner, bob.pubkey());
}

#[test]
fn drivers_level_up_then_age_and_retire() {
    let mut w = World::new();
    let alice = player();
    let d = w.create_driver(11, alice.pubkey(), 60, 62);
    let auth = w.authority.insecure_clone();
    let mut peak_pace = 0;
    for race_id in 0..RETIRE_AT_RACES as u64 {
        let seed = [race_id as u8; 32];
        let race = w.create_race(1_000 + race_id, &seed);
        let filler = w.create_driver(10_000 + race_id, auth.pubkey(), 50, 50);
        for driver in [d, filler] {
            let i = w.enter_ix(&auth.pubkey(), race, driver);
            w.send(i, &auth).unwrap();
        }
        w.advance(LOCK_IN);
        let i = w.reveal_ix(race, seed);
        w.send(i, &auth).unwrap();
        let i = w.post_result_ix(race, [1; 32]);
        w.send(i, &auth).unwrap();
        let i = w.settle_ix(race, d, 1);
        w.send(i, &auth).unwrap();
        let driver: Driver = w.account(&d);
        peak_pace = peak_pace.max(driver.pace);
    }
    let driver: Driver = w.account(&d);
    assert_eq!(peak_pace, 62, "levelling stops at potential");
    assert!(driver.pace < peak_pace, "pace declines after the peak");
    assert!(driver.retired, "driver retires after {} races", RETIRE_AT_RACES);
}
