// Calls one line from another through a running exchange and checks every step of the call.
//
//   node scripts/smoke.mjs                                  # against `npm run dev`
//   node scripts/smoke.mjs --url wss://exchange.regiscamimura.com
//
// Prints each step and exits 1 at the first one that fails.

import { randomBytes } from "node:crypto";

const urlArgIndex = process.argv.indexOf("--url");
const base = urlArgIndex > 0 ? process.argv[urlArgIndex + 1] : "ws://localhost:8787";

// openLine connects a game with a fresh secret and resolves with its socket, its number and a
// function that waits for the next message of a given type.
async function openLine(codename) {
	const secret = randomBytes(16).toString("hex");
	const ws = new WebSocket(`${base}/line?secret=${secret}&codename=${codename}`);
	const inbox = [];
	const pendingWaiters = [];
	ws.addEventListener("message", (event) => {
		inbox.push(JSON.parse(event.data));
		for (const wake of pendingWaiters.splice(0)) wake();
	});
	const nextMessage = async (type) => {
		const deadline = Date.now() + 5000;
		for (;;) {
			const i = inbox.findIndex((m) => m.type === type);
			if (i >= 0) return inbox.splice(i, 1)[0];
			if (Date.now() > deadline) throw new Error(`${codename}: no "${type}" within 5 s; got ${JSON.stringify(inbox)}`);
			await new Promise((wake) => {
				pendingWaiters.push(wake);
				setTimeout(wake, 200);
			});
		}
	};
	const welcome = await nextMessage("welcome");
	return { ws, number: welcome.number, nextMessage, send: (m) => ws.send(JSON.stringify(m)) };
}

function expectOk(ok, what) {
	console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
	if (!ok) process.exit(1);
}

const caller = await openLine("CORUJA");
const callee = await openLine("AGUIA");
expectOk(caller.number >= 100 && callee.number !== caller.number, `numbers MORSE ${caller.number} and MORSE ${callee.number}`);

caller.send({ type: "dial", number: 99999 });
const noAnswerMessage = await caller.nextMessage("no_answer");
expectOk(noAnswerMessage.reason === "offline", `dialling a line nobody has: ${JSON.stringify(noAnswerMessage)}`);

caller.send({ type: "dial", number: callee.number });
const ring = await callee.nextMessage("ring");
expectOk(ring.number === caller.number && ring.codename === "CORUJA", `callee hears the bell: ${JSON.stringify(ring)}`);
await caller.nextMessage("ringing");

callee.send({ type: "answer" });
const callerSees = await caller.nextMessage("connected");
const calleeSees = await callee.nextMessage("connected");
expectOk(callerSees.codename === "AGUIA" && calleeSees.codename === "CORUJA", "both ends connected");

caller.send({ type: "key", down: true, at: 12.34 });
caller.send({ type: "key", down: false, at: 12.45 });
const keyDownMessage = await callee.nextMessage("key");
const keyUpMessage = await callee.nextMessage("key");
expectOk(keyDownMessage.down === true && keyDownMessage.at === 12.34 && keyUpMessage.down === false, `a dit crosses the line: ${JSON.stringify([keyDownMessage, keyUpMessage])}`);

caller.send({ type: "hangup" });
await callee.nextMessage("hung_up");
expectOk(true, "hanging up reaches the other end");

caller.ws.close();
callee.ws.close();
