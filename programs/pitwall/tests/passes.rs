use {
    anchor_lang::{
        prelude::{Clock, Pubkey},
        solana_program::{instruction::Instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    pitwall::{constants::*, error::PitWallError, instruction as ix, state::{PassEntry, PassPool}, PoolParams},
    solana_keypair::Keypair,
    solana_message::{Message, VersionedMessage},
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
};

const POOL: u64 = 7;
const STAKE: u64 = 50_000_000; // 0.05 SOL
const RAKE_BPS: u16 = 1_000; // 10%

struct World {
    svm: LiteSVM,
    authority: Keypair,
    config: Pubkey,
}

fn pda(seeds: &[&[u8]]) -> Pubkey {
    Pubkey::find_program_address(seeds, &pitwall::id()).0
}
fn pool_pda(id: u64) -> Pubkey {
    pda(&[POOL_SEED, &id.to_le_bytes()])
}
fn pass_pda(pool: &Pubkey, player: &Pubkey) -> Pubkey {
    pda(&[PASS_SEED, pool.as_ref(), player.as_ref()])
}
fn code(e: PitWallError) -> String {
    format!("Custom({})", u32::from(e))
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

    fn lamports(&self, key: &Pubkey) -> u64 {
        self.svm.get_account(key).map(|a| a.lamports).unwrap_or(0)
    }

    fn create_pool(&mut self, id: u64, closes_in: i64) -> Result<(), String> {
        let params = PoolParams { entry_lamports: STAKE, closes_ts: self.now() + closes_in, rake_bps: RAKE_BPS };
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::CreatePool { pool_id: id, params }.data(),
            pitwall::accounts::CreatePool {
                authority: self.authority.pubkey(),
                config: self.config,
                pool: pool_pda(id),
                system_program: system_program::ID,
            }
            .to_account_metas(None),
        );
        let auth = self.authority.insecure_clone();
        self.send(i, &auth)
    }

    fn player(&mut self) -> Keypair {
        let k = Keypair::new();
        self.svm.airdrop(&k.pubkey(), 1_000_000_000).unwrap();
        k
    }

    fn enter(&mut self, id: u64, player: &Keypair) -> Result<(), String> {
        let pool = pool_pda(id);
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::EnterPool {}.data(),
            pitwall::accounts::EnterPool {
                player: player.pubkey(),
                pool,
                entry: pass_pda(&pool, &player.pubkey()),
                system_program: system_program::ID,
            }
            .to_account_metas(None),
        );
        self.send(i, player)
    }

    fn pay(&mut self, id: u64, player: &Pubkey, amount: u64) -> Result<(), String> {
        let pool = pool_pda(id);
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::PayOut { amount }.data(),
            pitwall::accounts::PayOut {
                authority: self.authority.pubkey(),
                config: self.config,
                pool,
                entry: pass_pda(&pool, player),
                player: *player,
            }
            .to_account_metas(None),
        );
        let auth = self.authority.insecure_clone();
        self.send(i, &auth)
    }

    fn close(&mut self, id: u64, refund: bool) -> Result<(), String> {
        let i = Instruction::new_with_bytes(
            pitwall::id(),
            &ix::ClosePool { results_hash: [9; 32], refund }.data(),
            pitwall::accounts::ClosePool { authority: self.authority.pubkey(), config: self.config, pool: pool_pda(id) }
                .to_account_metas(None),
        );
        let auth = self.authority.insecure_clone();
        self.send(i, &auth)
    }
}

#[test]
fn stakes_are_paid_out_by_placing_and_pit_wall_takes_exactly_its_share() {
    let mut w = World::new();
    w.create_pool(POOL, 3600).unwrap();
    let players: Vec<Keypair> = (0..4).map(|_| w.player()).collect();
    for p in &players {
        let before = w.lamports(&p.pubkey());
        w.enter(POOL, p).unwrap();
        assert!(before - w.lamports(&p.pubkey()) >= STAKE, "the stake left the wallet");
    }
    let pool: PassPool = w.account(&pool_pda(POOL));
    assert_eq!(pool.entrants, 4);
    assert_eq!(pool.total_lamports, 4 * STAKE);

    // a second pass for the same player is refused
    assert!(w.enter(POOL, &players[0]).is_err());

    // no payouts while entries are open
    assert!(w.pay(POOL, &players[0].pubkey(), STAKE).unwrap_err().contains(&code(PitWallError::PoolStillOpen)));

    w.advance(3600);
    // entries are closed now
    let late = w.player();
    assert!(w.enter(POOL, &late).unwrap_err().contains(&code(PitWallError::PoolClosed)));

    // 90% of 0.2 SOL = 0.18 SOL to players: 1st 0.11, 2nd 0.07
    let first = 110_000_000;
    let second = 70_000_000;
    let w0 = w.lamports(&players[0].pubkey());
    w.pay(POOL, &players[0].pubkey(), first).unwrap();
    assert_eq!(w.lamports(&players[0].pubkey()) - w0, first);
    // a pass is paid once
    assert!(w.pay(POOL, &players[0].pubkey(), 1).unwrap_err().contains(&code(PitWallError::AlreadySettled)));
    // closing before every payout is made is refused
    assert!(w.close(POOL, false).unwrap_err().contains(&code(PitWallError::PayoutMismatch)));
    w.pay(POOL, &players[1].pubkey(), second).unwrap();

    let auth_before = w.lamports(&w.authority.pubkey());
    w.close(POOL, false).unwrap();
    let pool: PassPool = w.account(&pool_pda(POOL));
    assert!(pool.closed);
    assert_eq!(pool.paid_lamports, first + second);
    // the authority gained Pit Wall's 10% share minus the transaction fee
    let gained = w.lamports(&w.authority.pubkey()) as i64 - auth_before as i64;
    assert!(gained > 19_990_000 && gained <= 20_000_000, "rake {gained}");
    let entry: PassEntry = w.account(&pass_pda(&pool_pda(POOL), &players[0].pubkey()));
    assert!(entry.paid && entry.payout == first);
    assert!(w.close(POOL, false).is_err(), "a pool closes once");
}

#[test]
fn payouts_can_never_exceed_the_stakes() {
    let mut w = World::new();
    w.create_pool(POOL, 60).unwrap();
    let a = w.player();
    let b = w.player();
    w.enter(POOL, &a).unwrap();
    w.enter(POOL, &b).unwrap();
    w.advance(60);
    assert!(w.pay(POOL, &a.pubkey(), 2 * STAKE + 1).unwrap_err().contains(&code(PitWallError::Overpaid)));
    w.pay(POOL, &a.pubkey(), 2 * STAKE).unwrap();
    assert!(w.pay(POOL, &b.pubkey(), 1).unwrap_err().contains(&code(PitWallError::Overpaid)));
    // paying everything to players leaves no share: only a refund-style close balances it
    assert!(w.close(POOL, false).unwrap_err().contains(&code(PitWallError::PayoutMismatch)));
}

#[test]
fn a_small_pool_is_refunded_in_full() {
    let mut w = World::new();
    w.create_pool(POOL, 60).unwrap();
    let a = w.player();
    let b = w.player();
    w.enter(POOL, &a).unwrap();
    w.enter(POOL, &b).unwrap();
    w.advance(60);
    w.pay(POOL, &a.pubkey(), STAKE).unwrap();
    w.pay(POOL, &b.pubkey(), STAKE).unwrap();
    w.close(POOL, true).unwrap();
    let pool: PassPool = w.account(&pool_pda(POOL));
    assert!(pool.closed && pool.paid_lamports == 2 * STAKE);
}

#[test]
fn only_the_authority_runs_pools() {
    let mut w = World::new();
    let stranger = w.player();
    let params = PoolParams { entry_lamports: STAKE, closes_ts: w.now() + 60, rake_bps: RAKE_BPS };
    let i = Instruction::new_with_bytes(
        pitwall::id(),
        &ix::CreatePool { pool_id: 99, params }.data(),
        pitwall::accounts::CreatePool {
            authority: stranger.pubkey(),
            config: w.config,
            pool: pool_pda(99),
            system_program: system_program::ID,
        }
        .to_account_metas(None),
    );
    assert!(w.send(i, &stranger).unwrap_err().contains(&code(PitWallError::Unauthorized)));
    // the program caps Pit Wall's share
    let params = PoolParams { entry_lamports: STAKE, closes_ts: w.now() + 60, rake_bps: MAX_RAKE_BPS + 1 };
    let i = Instruction::new_with_bytes(
        pitwall::id(),
        &ix::CreatePool { pool_id: 98, params }.data(),
        pitwall::accounts::CreatePool {
            authority: w.authority.pubkey(),
            config: w.config,
            pool: pool_pda(98),
            system_program: system_program::ID,
        }
        .to_account_metas(None),
    );
    let auth = w.authority.insecure_clone();
    assert!(w.send(i, &auth).unwrap_err().contains(&code(PitWallError::InvalidPool)));
}
