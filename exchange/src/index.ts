import { DurableObject } from "cloudflare:workers";

// The MORSE telephone exchange. It hands each player a line number (MORSE 123), rings the
// player a call is for, and once they answer passes each side's key presses to the other.
// One Durable Object holds every line, so both ends of a call are always on the same machine.
//
// A game connects a WebSocket to /line?secret=<32 hex digits>&codename=<1-10 letters or
// digits>. The secret is the game's own, kept in its save, and always gets the same number.
// Messages are JSON, one per frame:
//
//   exchange → game   {"type":"welcome","number":123}
//   game → exchange   {"type":"dial","number":456}
//   exchange → caller {"type":"ringing","number":456}       or {"type":"no_answer","number":456,"reason":"offline"}
//   exchange → callee {"type":"ring","number":123,"codename":"CORUJA"}
//   callee → exchange {"type":"answer"}
//   exchange → both   {"type":"connected","number":<the other side>,"codename":"<theirs>"}
//   game → exchange   {"type":"key","down":true,"at":12.34}  passed to the other side as is
//   game → exchange   {"type":"hangup"}                       the other side gets {"type":"hung_up"}

interface Env {
	EXCHANGE: DurableObjectNamespace<Exchange>;
}

// Line is what the exchange knows about a connected player. It's kept on their socket, so it
// survives the object hibernating between messages.
interface Line {
	number: number;
	codename: string;
	state: "idle" | "calling" | "ringing" | "connected";
	peer: number; // the line being called, calling, or on the call; 0 when idle
}

const firstNumber = 100;

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const path = new URL(request.url).pathname;
		if (path === "/") return new Response("MORSE telephone exchange\n");
		if (path !== "/line") return new Response("not found\n", { status: 404 });
		if (request.headers.get("Upgrade") !== "websocket") {
			return new Response("expected a WebSocket\n", { status: 426 });
		}
		return env.EXCHANGE.get(env.EXCHANGE.idFromName("exchange")).fetch(request);
	},
};

export class Exchange extends DurableObject<Env> {
	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		ctx.storage.sql.exec(
			"CREATE TABLE IF NOT EXISTS lines (secret TEXT PRIMARY KEY, number INTEGER UNIQUE NOT NULL)",
		);
	}

	async fetch(request: Request): Promise<Response> {
		const params = new URL(request.url).searchParams;
		const secret = params.get("secret") ?? "";
		const codename = (params.get("codename") ?? "").toUpperCase();
		if (!/^[0-9a-f]{32}$/.test(secret) || !/^[A-Z0-9]{1,10}$/.test(codename)) {
			return new Response("needs ?secret=<32 hex digits>&codename=<1-10 letters or digits>\n", {
				status: 400,
			});
		}
		const number = this.numberForSecret(secret);
		// the same game connecting again (a new network, a second device) replaces its old line
		for (const old of this.ctx.getWebSockets(tagFor(number))) old.close(4000, "opened elsewhere");

		const { 0: client, 1: server } = new WebSocketPair();
		this.ctx.acceptWebSocket(server, [tagFor(number)]);
		writeLine(server, { number, codename, state: "idle", peer: 0 });
		send(server, { type: "welcome", number });
		return new Response(null, { status: 101, webSocket: client });
	}

	async webSocketMessage(ws: WebSocket, data: string | ArrayBuffer): Promise<void> {
		if (typeof data !== "string" || data.length > 256) return;
		let message: { type?: unknown; number?: unknown; down?: unknown; at?: unknown };
		try {
			message = JSON.parse(data);
		} catch {
			return;
		}
		const line = readLine(ws);
		switch (message.type) {
			case "dial":
				if (typeof message.number === "number") this.ring(ws, line, message.number);
				return;
			case "answer":
				this.putThrough(ws, line);
				return;
			case "hangup":
				this.hangUp(ws, line);
				return;
			case "key":
				if (line.state === "connected" && typeof message.down === "boolean" && typeof message.at === "number") {
					const peer = this.socketOfLine(line.peer);
					if (peer) send(peer, { type: "key", down: message.down, at: message.at });
				}
				return;
		}
	}

	async webSocketClose(ws: WebSocket): Promise<void> {
		this.hangUp(ws, readLine(ws));
	}

	async webSocketError(ws: WebSocket): Promise<void> {
		this.hangUp(ws, readLine(ws));
	}

	// ring rings line `number` for the caller, or tells the caller why it can't.
	private ring(ws: WebSocket, line: Line, number: number): void {
		if (line.state !== "idle") return;
		const callee = this.socketOfLine(number);
		let reason = "";
		if (number === line.number) reason = "self";
		else if (!callee) reason = "offline";
		else if (readLine(callee).state !== "idle") reason = "busy";
		if (reason || !callee) {
			send(ws, { type: "no_answer", number, reason });
			return;
		}
		writeLine(ws, { ...line, state: "calling", peer: number });
		writeLine(callee, { ...readLine(callee), state: "ringing", peer: line.number });
		send(callee, { type: "ring", number: line.number, codename: line.codename });
		send(ws, { type: "ringing", number });
	}

	// putThrough connects a ringing line to its caller.
	private putThrough(ws: WebSocket, line: Line): void {
		const caller = line.state === "ringing" ? this.socketOfLine(line.peer) : undefined;
		const callerLine = caller && readLine(caller);
		if (!caller || !callerLine || callerLine.state !== "calling" || callerLine.peer !== line.number) return;
		writeLine(ws, { ...line, state: "connected" });
		writeLine(caller, { ...callerLine, state: "connected" });
		send(ws, { type: "connected", number: callerLine.number, codename: callerLine.codename });
		send(caller, { type: "connected", number: line.number, codename: line.codename });
	}

	// hangUp ends whatever call the line is in: calling, ringing or connected.
	private hangUp(ws: WebSocket, line: Line): void {
		if (line.state === "idle") return;
		const peer = this.socketOfLine(line.peer);
		const peerLine = peer && readLine(peer);
		if (peer && peerLine && peerLine.peer === line.number) {
			writeLine(peer, { ...peerLine, state: "idle", peer: 0 });
			send(peer, { type: "hung_up" });
		}
		writeLine(ws, { ...line, state: "idle", peer: 0 });
	}

	private numberForSecret(secret: string): number {
		const sql = this.ctx.storage.sql;
		const linesWithSecret = sql.exec<{ number: number }>("SELECT number FROM lines WHERE secret = ?", secret).toArray();
		if (linesWithSecret.length > 0) return linesWithSecret[0].number;
		const nextNumber = sql
			.exec<{ next: number }>("SELECT COALESCE(MAX(number) + 1, ?) AS next FROM lines", firstNumber)
			.one().next;
		sql.exec("INSERT INTO lines (secret, number) VALUES (?, ?)", secret, nextNumber);
		return nextNumber;
	}

	private socketOfLine(number: number): WebSocket | undefined {
		return this.ctx.getWebSockets(tagFor(number)).find((ws) => ws.readyState === WebSocket.OPEN);
	}
}

function tagFor(number: number): string {
	return `line:${number}`;
}

function readLine(ws: WebSocket): Line {
	return ws.deserializeAttachment() as Line;
}

function writeLine(ws: WebSocket, line: Line): void {
	ws.serializeAttachment(line);
}

// send writes a message to a socket that may have just closed: a closed socket drops it.
function send(ws: WebSocket, message: object): void {
	try {
		ws.send(JSON.stringify(message));
	} catch {
		// the line went down; its close handler hangs up the call
	}
}
