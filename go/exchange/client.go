// Package exchange connects the game to the MORSE telephone exchange (exchange/ at the repo
// root, deployed at exchange.regiscamimura.com) over a WebSocket. A Client is the morse.Wire
// the front ends hand the game: it keeps the connection up in the background, reconnecting
// after a drop, and never blocks the game loop.
package exchange

import (
	"context"
	"net/url"
	"os"
	"sync"
	"time"

	"github.com/coder/websocket"
	"github.com/coder/websocket/wsjson"

	"github.com/regiscamimura/morse-code-game/go/morse"
)

// Address is the exchange to call: $MORSE_EXCHANGE when set (e.g. ws://localhost:8787 for
// `npm run dev` in exchange/), else the deployed one.
func Address() string {
	if address := os.Getenv("MORSE_EXCHANGE"); address != "" {
		return address
	}
	return "wss://exchange.regiscamimura.com"
}

// Client is a game's line to the exchange.
type Client struct {
	address string
	outbox  chan morse.WireMessage

	mu        sync.Mutex
	inbox     []morse.WireMessage
	connected bool
	stop      context.CancelFunc // ends the current Open; nil when closed
}

func New(address string) *Client {
	return &Client{address: address, outbox: make(chan morse.WireMessage, 64)}
}

// Open connects as the line that secret names, under codename, and keeps reconnecting until
// Close. Each connection starts with the exchange's welcome; each drop adds an "offline".
func (c *Client) Open(secret, codename string) {
	c.Close()
	ctx, stop := context.WithCancel(context.Background())
	c.mu.Lock()
	c.stop, c.inbox = stop, nil
	c.mu.Unlock()
	query := url.Values{"secret": {secret}, "codename": {codename}}
	go c.stayConnected(ctx, c.address+"/line?"+query.Encode())
}

func (c *Client) Close() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.stop != nil {
		c.stop()
		c.stop = nil
	}
}

// Send queues m for the exchange; it's dropped while the line is down or the queue is full.
func (c *Client) Send(m morse.WireMessage) {
	c.mu.Lock()
	connected := c.connected
	c.mu.Unlock()
	if !connected {
		return
	}
	select {
	case c.outbox <- m:
	default:
	}
}

func (c *Client) Receive() []morse.WireMessage {
	c.mu.Lock()
	defer c.mu.Unlock()
	inbox := c.inbox
	c.inbox = nil
	return inbox
}

func (c *Client) deliver(m morse.WireMessage) {
	c.mu.Lock()
	c.inbox = append(c.inbox, m)
	c.mu.Unlock()
}

func (c *Client) stayConnected(ctx context.Context, address string) {
	for ctx.Err() == nil {
		dialing, cancel := context.WithTimeout(ctx, 10*time.Second)
		conn, _, err := websocket.Dial(dialing, address, nil)
		cancel()
		if err == nil {
			c.serve(ctx, conn)
		}
		if ctx.Err() != nil {
			return
		}
		c.deliver(morse.WireMessage{Type: "offline"})
		select {
		case <-ctx.Done():
			return
		case <-time.After(2 * time.Second):
		}
	}
}

// serve runs one connection until it drops or Open's context ends: it reads what the exchange
// sends, writes what the game queued, and pings so an idle line isn't cut by the network.
func (c *Client) serve(ctx context.Context, conn *websocket.Conn) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	defer conn.CloseNow()
	for len(c.outbox) > 0 { // anything queued for an earlier connection is stale
		<-c.outbox
	}
	c.mu.Lock()
	c.connected = true
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		c.connected = false
		c.mu.Unlock()
	}()

	go func() {
		ping := time.NewTicker(30 * time.Second)
		defer ping.Stop()
		for {
			var err error
			select {
			case <-ctx.Done():
				return
			case m := <-c.outbox:
				err = wsjson.Write(ctx, conn, m)
			case <-ping.C:
				err = conn.Ping(ctx)
			}
			if err != nil {
				cancel()
				return
			}
		}
	}()
	for {
		var m morse.WireMessage
		if err := wsjson.Read(ctx, conn, &m); err != nil {
			return
		}
		c.deliver(m)
	}
}
