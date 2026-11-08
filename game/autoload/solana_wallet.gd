class_name SolanaWallet
extends RefCounted
## Talks to a browser Solana wallet (Phantom, Backpack, Solflare) from the web
## build: connect for the public key, then sign a message to prove ownership.
## Only works in the web export; elsewhere `available()` is false.

const JS := """
window.pitwallWallet = {
  provider() {
    return (window.phantom && window.phantom.solana) || window.backpack || window.solflare || window.solana || null;
  },
  async connect() {
    window.__pw = {state: 'pending'};
    try {
      const p = this.provider();
      if (!p) { window.__pw = {state: 'error', error: 'No Solana wallet found. Install Phantom or Backpack and reload.'}; return; }
      const r = await p.connect();
      const pk = (r && r.publicKey) || p.publicKey;
      window.__pw = {state: 'ok', pubkey: pk.toString()};
    } catch (e) { window.__pw = {state: 'error', error: String((e && e.message) || e)}; }
  },
  async sign(msg) {
    window.__pw = {state: 'pending'};
    try {
      const p = this.provider();
      const r = await p.signMessage(new TextEncoder().encode(msg), 'utf8');
      const sig = (r && r.signature) || r;
      let s = '';
      for (const b of sig) s += String.fromCharCode(b);
      window.__pw = {state: 'ok', signature: btoa(s)};
    } catch (e) { window.__pw = {state: 'error', error: String((e && e.message) || e)}; }
  },
  async loadWeb3() {
    if (window.solanaWeb3) return;
    await new Promise((ok, fail) => {
      const el = document.createElement('script');
      el.src = 'https://cdn.jsdelivr.net/npm/@solana/web3.js@1/lib/index.iife.min.js';
      el.onload = ok;
      el.onerror = () => fail(new Error('Could not load the Solana library.'));
      document.head.appendChild(el);
    });
  },
  async signTx(b64) {
    window.__pw = {state: 'pending'};
    try {
      await this.loadWeb3();
      const p = this.provider();
      if (!p) throw new Error('No Solana wallet found. Install Phantom or Backpack and reload.');
      const tx = window.solanaWeb3.Transaction.from(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)));
      const signed = await p.signTransaction(tx);
      let s = '';
      for (const b of signed.serialize()) s += String.fromCharCode(b);
      window.__pw = {state: 'ok', tx: btoa(s)};
    } catch (e) { window.__pw = {state: 'error', error: String((e && e.message) || e)}; }
  }
};
"""

static var _installed := false
static var last_error := ""


static func available() -> bool:
	return OS.has_feature("web")


static func _install() -> void:
	if not _installed and available():
		JavaScriptBridge.eval(JS, true)
		_installed = true


## Waits for the pending wallet call; returns its result object (or {} on timeout).
static func _wait(tree: SceneTree, seconds: float = 90.0) -> Dictionary:
	var t := 0.0
	while t < seconds:
		await tree.process_frame
		t += tree.root.get_process_delta_time()
		var raw: Variant = JavaScriptBridge.eval("JSON.stringify(window.__pw || {})", true)
		var res: Variant = JSON.parse_string(String(raw))
		if res is Dictionary and String((res as Dictionary).get("state", "")) != "pending":
			return res
	return {"state": "error", "error": "The wallet didn't answer."}


## The connected wallet's public key (base58), or "" with `last_error` set.
static func connect_wallet(tree: SceneTree) -> String:
	if not available():
		last_error = "Wallets work in the web version of the game."
		return ""
	_install()
	JavaScriptBridge.eval("window.pitwallWallet.connect()", true)
	var r := await _wait(tree)
	last_error = String(r.get("error", ""))
	return String(r.get("pubkey", ""))


## A base64 ed25519 signature of `message`, or "" with `last_error` set.
static func sign(tree: SceneTree, message: String) -> String:
	if not available():
		last_error = "Wallets work in the web version of the game."
		return ""
	_install()
	JavaScriptBridge.eval("window.pitwallWallet.sign(%s)" % JSON.stringify(message), true)
	var r := await _wait(tree)
	last_error = String(r.get("error", ""))
	return String(r.get("signature", ""))


## The wallet-signed transaction (base64) for an unsigned one the server built, or "" with
## `last_error` set. The server sends it, so it works whatever network the wallet is set to.
static func sign_transaction(tree: SceneTree, tx_b64: String) -> String:
	if not available():
		last_error = "Wallets work in the web version of the game."
		return ""
	_install()
	JavaScriptBridge.eval("window.pitwallWallet.signTx(%s)" % JSON.stringify(tx_b64), true)
	var r := await _wait(tree)
	last_error = String(r.get("error", ""))
	return String(r.get("tx", ""))
